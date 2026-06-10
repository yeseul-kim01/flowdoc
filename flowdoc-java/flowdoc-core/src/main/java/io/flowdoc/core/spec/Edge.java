package io.flowdoc.core.spec;

/**
 * A call relationship "from calls to". {@code resolution} carries confidence:
 * {@code concrete}, {@code single-impl}, {@code ambiguous}, {@code runtime-confirmed}.
 */
public record Edge(
        String from,
        String to,
        String callType,
        Site site,
        String condition,
        String resolution
) {
}
