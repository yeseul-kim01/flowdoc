package io.flowdoc.runtime;

import io.flowdoc.core.spec.Span;
import io.flowdoc.core.spec.Trace;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Builds one {@link Trace} per top-level call chain and keeps the most recent traces in
 * a bounded ring buffer for the {@code /flowdoc/traces.json} route. Spans reference nodes
 * by the same id the static scanner emits (see {@link RuntimeIds}), so the UI lands them
 * on the structure graph.
 *
 * <p>A trace is an {@code Accumulator} (its spans + flush accounting) shared by every
 * thread that contributes to it, plus a per-thread {@code ThreadState} (that thread's live
 * call stack). The first intercepted call opens the accumulator; nested calls push child
 * spans; unwinding back to the root flushes the finished trace.
 *
 * <p><b>Async stitching (Phase 2):</b> Spring's {@code @Async} advice sits <em>outside</em>
 * this aspect, so the async method is intercepted here on its worker thread — not the
 * caller's. The {@link FlowDocTraceTaskDecorator}, running on the submitting thread, snaps
 * the caller frame ({@link #captureAsyncParent}), holds the trace open ({@link #armAsync}),
 * and installs that link on the worker ({@link #beginAsyncScope}). The worker's first
 * {@link #enter} then continues the caller's trace instead of starting a new one, timed on
 * the worker thread it actually ran on. The trace flushes only once the origin chain has
 * unwound <em>and</em> every armed async child has finished.
 *
 * <p>An {@code Accumulator} can be touched by the origin thread and its async workers at
 * once, so every mutation of one is guarded by its monitor.
 */
public final class TraceRecorder {

    /** Mutable span while its call is on a stack; frozen into a {@link Span} on flush. */
    private static final class Building {
        final String id;
        final String nodeId;
        final String parent;
        final long tEnter;
        final String thread;
        long tExit = -1;

        Building(String id, String nodeId, String parent, long tEnter, String thread) {
            this.id = id;
            this.nodeId = nodeId;
            this.parent = parent;
            this.tEnter = tEnter;
            this.thread = thread;
        }
    }

    /** The shared trace under construction: its spans and cross-thread flush accounting. */
    private static final class Accumulator {
        final String traceId;
        final long start;
        final List<Building> spans = new ArrayList<>();
        int spanSeq = 0;
        String rootNodeId;
        String error;
        String errorSpanId;
        int outstanding = 0;      // armed async children not yet finished
        boolean originDone = false;

        Accumulator(String traceId, long start) {
            this.traceId = traceId;
            this.start = start;
        }
    }

    /** One thread's live call stack within a trace. */
    private static final class ThreadState {
        final Accumulator acc;
        final Deque<Building> stack = new ArrayDeque<>();
        final boolean worker;
        final String inheritedParent;   // parent id for this worker's first span (async continuation)

        ThreadState(Accumulator acc, boolean worker, String inheritedParent) {
            this.acc = acc;
            this.worker = worker;
            this.inheritedParent = inheritedParent;
        }
    }

    /**
     * Caller-thread snapshot handed to an async worker so its span joins the caller's
     * trace: the target accumulator and the frame that dispatched the async call.
     */
    public static final class AsyncLink {
        private final Accumulator acc;
        private final String parentSpanId;
        private final AtomicBoolean consumed = new AtomicBoolean(false);

        private AsyncLink(Accumulator acc, String parentSpanId) {
            this.acc = acc;
            this.parentSpanId = parentSpanId;
        }

        boolean consumed() {
            return consumed.get();
        }
    }

    private final int maxTraces;
    private final AtomicLong traceSeq = new AtomicLong();
    private final ThreadLocal<ThreadState> current = new ThreadLocal<>();
    private final ThreadLocal<AsyncLink> asyncScope = new ThreadLocal<>();
    private final Deque<Trace> completed = new ArrayDeque<>();

    public TraceRecorder(int maxTraces) {
        this.maxTraces = Math.max(1, maxTraces);
    }

    /**
     * Opens a span for {@code nodeId}, starting a trace if this thread has none. If an
     * async scope is active (a worker running a dispatched task), the first call here
     * continues the caller's trace instead. Returns an opaque handle for {@link #exit}.
     */
    public Object enter(String nodeId) {
        ThreadState ts = current.get();
        if (ts == null) {
            AsyncLink scope = asyncScope.get();
            if (scope != null && scope.consumed.compareAndSet(false, true)) {
                ts = new ThreadState(scope.acc, true, scope.parentSpanId);
            } else {
                ts = new ThreadState(new Accumulator("t" + traceSeq.incrementAndGet(), now()), false, null);
            }
            current.set(ts);
        }
        Accumulator acc = ts.acc;
        synchronized (acc) {
            String parent = ts.stack.isEmpty() ? ts.inheritedParent : ts.stack.peek().id;
            Building span = new Building(
                    "s" + (++acc.spanSeq), nodeId, parent, now() - acc.start,
                    Thread.currentThread().getName());
            if (parent == null && acc.rootNodeId == null) {
                acc.rootNodeId = nodeId;
            }
            acc.spans.add(span);
            ts.stack.push(span);
            return span;
        }
    }

    /**
     * Records the cause that aborted the current trace. Keeps the first (innermost)
     * cause — the origin of the failure rather than whatever it was rethrown as.
     */
    public void markError(Throwable cause) {
        ThreadState ts = current.get();
        if (ts == null || cause == null) {
            return;
        }
        Accumulator acc = ts.acc;
        synchronized (acc) {
            if (acc.error != null) {
                return;
            }
            String message = cause.getMessage();
            String label = cause.getClass().getSimpleName();
            if (message != null && !message.isBlank()) {
                label += ": " + (message.length() > 120 ? message.substring(0, 120) + "…" : message);
            }
            acc.error = label;
            // The first catch to fire is the innermost observed frame still on the stack —
            // the deepest the exception is visible. The true throw may be deeper (unobserved).
            if (!ts.stack.isEmpty()) {
                acc.errorSpanId = ts.stack.peek().id;
            }
        }
    }

    /** Closes the span; when this thread's stack empties, settles the trace. */
    public void exit(Object handle) {
        ThreadState ts = current.get();
        if (ts == null || !(handle instanceof Building span)) {
            return;
        }
        Accumulator acc = ts.acc;
        boolean flush = false;
        synchronized (acc) {
            span.tExit = now() - acc.start;
            // Defensive: unwind to the closing span even if an exception skipped a frame.
            while (!ts.stack.isEmpty() && ts.stack.peek() != span) {
                ts.stack.pop();
            }
            if (!ts.stack.isEmpty()) {
                ts.stack.pop();
            }
            if (ts.stack.isEmpty()) {
                current.remove();
                if (ts.worker) {
                    // An async child finished; flush if the origin is done and it was the last.
                    acc.outstanding--;
                    flush = acc.originDone && acc.outstanding == 0;
                } else {
                    // The origin chain unwound; hold open while async children remain.
                    acc.originDone = true;
                    flush = acc.outstanding == 0;
                }
            }
        }
        if (flush) {
            flush(acc);
        }
    }

    /**
     * Caller thread: snapshot the current frame so an async worker can attach its span to
     * this trace. Returns {@code null} when there is no active trace to attach to.
     */
    public AsyncLink captureAsyncParent() {
        ThreadState ts = current.get();
        if (ts == null) {
            return null;
        }
        Accumulator acc = ts.acc;
        synchronized (acc) {
            String parent = ts.stack.isEmpty() ? ts.inheritedParent : ts.stack.peek().id;
            return new AsyncLink(acc, parent);
        }
    }

    /**
     * Caller thread: mark that an async child was dispatched, so the trace defers its
     * flush until the child finishes. Balanced by exactly one worker {@link #exit} (once
     * the scope is consumed) or one {@link #cancelAsync} (if it never is).
     */
    public void armAsync(AsyncLink link) {
        if (link == null) {
            return;
        }
        synchronized (link.acc) {
            link.acc.outstanding++;
        }
    }

    /** Worker thread: install the caller's link so the first {@link #enter} continues its trace. */
    public void beginAsyncScope(AsyncLink link) {
        if (link != null) {
            asyncScope.set(link);
        }
    }

    /** Worker thread: remove the async scope once the dispatched task has run. */
    public void endAsyncScope() {
        asyncScope.remove();
    }

    /**
     * Release an armed async child that never opened a span (its method wasn't advised),
     * so a dispatch onto a decorated executor can't strand the trace open. Flushes if the
     * origin is done and this was the last outstanding child.
     */
    public void cancelAsync(AsyncLink link) {
        if (link == null) {
            return;
        }
        Accumulator acc = link.acc;
        boolean flush;
        synchronized (acc) {
            acc.outstanding--;
            flush = acc.originDone && acc.outstanding == 0;
        }
        if (flush) {
            flush(acc);
        }
    }

    private void flush(Accumulator acc) {
        Trace trace;
        synchronized (acc) {
            List<Span> spans = new ArrayList<>(acc.spans.size());
            for (Building b : acc.spans) {
                spans.add(new Span(b.id, b.nodeId, b.parent, b.tEnter,
                        b.tExit < 0 ? null : b.tExit, b.thread));
            }
            trace = new Trace(acc.traceId, acc.rootNodeId, spans, acc.error, acc.errorSpanId);
        }
        synchronized (completed) {
            completed.addFirst(trace);
            while (completed.size() > maxTraces) {
                completed.removeLast();
            }
        }
    }

    /** Most-recent-first snapshot of the recorded traces. */
    public List<Trace> traces() {
        synchronized (completed) {
            return new ArrayList<>(completed);
        }
    }

    /** Clears all recorded traces (used by the {@code DELETE} route and tests). */
    public void clear() {
        synchronized (completed) {
            completed.clear();
        }
    }

    private static long now() {
        return System.currentTimeMillis();
    }
}
