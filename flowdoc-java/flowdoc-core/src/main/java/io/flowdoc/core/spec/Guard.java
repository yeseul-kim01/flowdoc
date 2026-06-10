package io.flowdoc.core.spec;

/** A concurrency guard protecting a node. {@code source} is {@code declared} or {@code auto}. */
public record Guard(
        String nodeId,
        String type,
        String resource,
        int permits,
        String source
) {
}
