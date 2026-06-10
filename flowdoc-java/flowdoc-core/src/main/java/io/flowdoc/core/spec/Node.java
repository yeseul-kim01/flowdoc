package io.flowdoc.core.spec;

/**
 * One function in a flow. Its information is split by provenance: {@code auto}
 * (extracted from code structure) vs {@code declared} (written by the developer).
 */
public record Node(
        String id,
        String simpleName,
        String owner,
        String kind,
        Location location,
        Auto auto,
        Declared declared,
        Markers markers
) {
}
