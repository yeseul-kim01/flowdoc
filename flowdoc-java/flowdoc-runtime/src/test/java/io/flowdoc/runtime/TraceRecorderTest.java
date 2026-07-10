package io.flowdoc.runtime;

import io.flowdoc.core.spec.Span;
import io.flowdoc.core.spec.Trace;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TraceRecorderTest {

    @Test
    void nestedCallsBuildAParentChildSpanTree() {
        TraceRecorder recorder = new TraceRecorder(10);

        Object root = recorder.enter("A#root()");
        Object child = recorder.enter("B#child()");
        recorder.exit(child);
        recorder.exit(root);

        List<Trace> traces = recorder.traces();
        assertEquals(1, traces.size());

        Trace trace = traces.get(0);
        assertEquals("A#root()", trace.sequenceTag(), "root node id becomes the sequence tag");
        assertEquals(2, trace.spans().size());

        Span rootSpan = trace.spans().get(0);
        Span childSpan = trace.spans().get(1);
        assertNull(rootSpan.parent(), "root span has no parent");
        assertEquals(rootSpan.id(), childSpan.parent(), "child points at the root span");
        assertEquals("B#child()", childSpan.nodeId());
        assertTrue(childSpan.tEnter() >= rootSpan.tEnter());
    }

    @Test
    void traceFlushesOnlyWhenTheRootUnwinds() {
        TraceRecorder recorder = new TraceRecorder(10);

        Object root = recorder.enter("A#root()");
        assertTrue(recorder.traces().isEmpty(), "nothing flushes while the chain is open");
        recorder.exit(root);

        assertEquals(1, recorder.traces().size());
    }

    @Test
    void asyncChildJoinsTheCallerTraceWhenItRunsAfterTheOriginUnwinds() throws Exception {
        TraceRecorder recorder = new TraceRecorder(10);

        // origin thread: root frame dispatches an @Async call, then unwinds
        Object root = recorder.enter("A#root()");
        TraceRecorder.AsyncLink link = recorder.captureAsyncParent();
        recorder.armAsync(link);            // decorator arms on the submitting thread
        recorder.exit(root);
        assertTrue(recorder.traces().isEmpty(),
                "flush is held open while an async child is outstanding");

        runAsyncChildOnWorker(recorder, link, "W#work()");   // aspect fires on the worker

        List<Trace> traces = recorder.traces();
        assertEquals(1, traces.size(), "the child flushes the caller's trace, not a new one");
        Trace trace = traces.get(0);
        assertEquals(2, trace.spans().size());

        Span rootSpan = trace.spans().get(0);
        Span workSpan = trace.spans().get(1);
        assertEquals("W#work()", workSpan.nodeId());
        assertEquals(rootSpan.id(), workSpan.parent(),
                "the async span hangs off the frame that dispatched it");
        assertNotEquals(rootSpan.thread(), workSpan.thread(),
                "the async span is timed on its own worker thread");
    }

    @Test
    void asyncChildThatFinishesBeforeTheOriginUnwindsStillFlushesOnce() throws Exception {
        TraceRecorder recorder = new TraceRecorder(10);

        Object root = recorder.enter("A#root()");
        TraceRecorder.AsyncLink link = recorder.captureAsyncParent();
        recorder.armAsync(link);

        // worker completes first, while the origin is still open
        runAsyncChildOnWorker(recorder, link, "W#work()");
        assertTrue(recorder.traces().isEmpty(), "nothing flushes while the origin is still open");

        recorder.exit(root);
        assertEquals(1, recorder.traces().size(), "the origin unwind flushes exactly once");
        assertEquals(2, recorder.traces().get(0).spans().size());
    }

    @Test
    void armedAsyncChildThatNeverOpensASpanDoesNotStrandTheTrace() {
        TraceRecorder recorder = new TraceRecorder(10);

        Object root = recorder.enter("A#root()");
        TraceRecorder.AsyncLink link = recorder.captureAsyncParent();
        recorder.armAsync(link);
        recorder.exit(root);
        assertTrue(recorder.traces().isEmpty(), "held open by the outstanding child");

        // The dispatched method was never advised → the decorator releases the arm.
        recorder.cancelAsync(link);

        assertEquals(1, recorder.traces().size(), "cancel lets the deferred trace flush");
        assertEquals(1, recorder.traces().get(0).spans().size(), "only the origin span");
    }

    /** Mimics the aspect firing on a worker thread inside an async scope, as at runtime. */
    private static void runAsyncChildOnWorker(TraceRecorder recorder, TraceRecorder.AsyncLink link,
                                              String nodeId) throws InterruptedException {
        Thread worker = new Thread(() -> {
            recorder.beginAsyncScope(link);
            try {
                Object h = recorder.enter(nodeId);
                recorder.exit(h);
            } finally {
                recorder.endAsyncScope();
            }
        }, "flowdoc-test-worker");
        worker.start();
        worker.join();
    }

    @Test
    void ringBufferKeepsOnlyTheMostRecentTraces() {
        TraceRecorder recorder = new TraceRecorder(2);

        for (int i = 0; i < 5; i++) {
            Object h = recorder.enter("N#m" + i + "()");
            recorder.exit(h);
        }

        List<Trace> traces = recorder.traces();
        assertEquals(2, traces.size(), "bounded to maxTraces");
        assertEquals("N#m4()", traces.get(0).sequenceTag(), "newest first");
        assertEquals("N#m3()", traces.get(1).sequenceTag());
    }
}
