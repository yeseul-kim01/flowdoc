package io.flowdoc.core.spec;

/** One node activation within a {@link Trace}. Times are relative millis. */
public record Span(
        String id,
        String nodeId,
        String parent,
        Long tEnter,
        Long tExit,
        String thread
) {
}
