package io.flowdoc.runtime;

import io.flowdoc.core.spec.Span;
import io.flowdoc.core.spec.Trace;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Builds one {@link Trace} per top-level call chain on a thread and keeps the most
 * recent traces in a bounded ring buffer for the {@code /flowdoc/traces.json} route.
 *
 * <p>Each thread carries its own in-progress trace in a {@link ThreadLocal}: the
 * first intercepted call opens it, nested calls push child spans, and unwinding back
 * to the root flushes the finished trace to the shared buffer. Spans reference nodes
 * by the same id the static scanner emits (see {@link RuntimeIds}), so the UI lands
 * them on the structure graph.
 *
 * <p><b>Phase 1 limitation:</b> an {@code @Async} hop runs on another thread and so
 * records as its own separate trace — cross-thread stitching is Phase 2.
 */
public final class TraceRecorder {

    /** Mutable span while its call is on the stack; frozen into a {@link Span} on flush. */
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

    private static final class Context {
        final String traceId;
        final long startMillis;
        final List<Building> spans = new ArrayList<>();
        final Deque<Building> stack = new ArrayDeque<>();
        int spanSeq = 0;
        String rootNodeId;
        String error;
        String errorSpanId;

        Context(String traceId, long startMillis) {
            this.traceId = traceId;
            this.startMillis = startMillis;
        }
    }

    private final int maxTraces;
    private final AtomicLong traceSeq = new AtomicLong();
    private final ThreadLocal<Context> current = new ThreadLocal<>();
    private final Deque<Trace> completed = new ArrayDeque<>();

    public TraceRecorder(int maxTraces) {
        this.maxTraces = Math.max(1, maxTraces);
    }

    /**
     * Opens a span for {@code nodeId}, starting a trace if this is the first call on
     * the thread. Returns an opaque handle to pass back to {@link #exit}.
     */
    public Object enter(String nodeId) {
        Context ctx = current.get();
        if (ctx == null) {
            ctx = new Context("t" + traceSeq.incrementAndGet(), now());
            current.set(ctx);
        }
        String parent = ctx.stack.isEmpty() ? null : ctx.stack.peek().id;
        Building span = new Building(
                "s" + (++ctx.spanSeq), nodeId, parent, now() - ctx.startMillis,
                Thread.currentThread().getName());
        if (ctx.stack.isEmpty()) {
            ctx.rootNodeId = nodeId;
        }
        ctx.spans.add(span);
        ctx.stack.push(span);
        return span;
    }

    /**
     * Records the cause that aborted the current trace. Keeps the first (innermost)
     * cause — the origin of the failure rather than whatever it was rethrown as.
     */
    public void markError(Throwable cause) {
        Context ctx = current.get();
        if (ctx == null || ctx.error != null || cause == null) {
            return;
        }
        String message = cause.getMessage();
        String label = cause.getClass().getSimpleName();
        if (message != null && !message.isBlank()) {
            label += ": " + (message.length() > 120 ? message.substring(0, 120) + "…" : message);
        }
        ctx.error = label;
        // The first catch to fire is the innermost observed frame still on the stack —
        // the deepest the exception is visible. The true throw may be deeper (unobserved).
        if (!ctx.stack.isEmpty()) {
            ctx.errorSpanId = ctx.stack.peek().id;
        }
    }

    /** Closes the span; when the stack empties, flushes the finished trace. */
    public void exit(Object handle) {
        Context ctx = current.get();
        if (ctx == null || !(handle instanceof Building span)) {
            return;
        }
        span.tExit = now() - ctx.startMillis;
        // Defensive: unwind to the closing span even if an exception skipped a frame.
        while (!ctx.stack.isEmpty() && ctx.stack.peek() != span) {
            ctx.stack.pop();
        }
        if (!ctx.stack.isEmpty()) {
            ctx.stack.pop();
        }
        if (ctx.stack.isEmpty()) {
            flush(ctx);
            current.remove();
        }
    }

    private void flush(Context ctx) {
        List<Span> spans = new ArrayList<>(ctx.spans.size());
        for (Building b : ctx.spans) {
            spans.add(new Span(b.id, b.nodeId, b.parent, b.tEnter,
                    b.tExit < 0 ? null : b.tExit, b.thread));
        }
        Trace trace = new Trace(ctx.traceId, ctx.rootNodeId, spans, ctx.error, ctx.errorSpanId);
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
