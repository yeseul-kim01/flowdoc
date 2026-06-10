package io.flowdoc.core.spec;

/**
 * Transaction boundary opened by a node. {@code boundary} is {@code "open"} when
 * the node carries {@code @Transactional}; {@code propagation} is read from the
 * annotation (the <em>actual</em> new-vs-join behavior is confirmed at runtime).
 */
public record TransactionMarker(String boundary, String propagation) {
}
