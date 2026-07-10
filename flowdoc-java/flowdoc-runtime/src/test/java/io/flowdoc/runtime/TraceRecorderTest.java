package io.flowdoc.runtime;

import io.flowdoc.core.spec.Span;
import io.flowdoc.core.spec.Trace;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
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
