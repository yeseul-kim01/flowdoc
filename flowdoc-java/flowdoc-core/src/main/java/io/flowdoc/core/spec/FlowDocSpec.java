package io.flowdoc.core.spec;

import java.util.List;

/**
 * Root of the FlowDoc shared spec — the single source of truth produced by any
 * collector (static scanner, runtime agent, future Python scanner) and consumed
 * by the UI. See docs/flowdoc-기획안.md §8.
 */
public record FlowDocSpec(
        String flowdoc,
        Source source,
        List<Node> nodes,
        List<Edge> edges,
        List<Guard> guards,
        List<Sequence> sequences,
        List<Trace> traces
) {
    /** Spec format version emitted by this build. */
    public static final String VERSION = "0.1";
}
