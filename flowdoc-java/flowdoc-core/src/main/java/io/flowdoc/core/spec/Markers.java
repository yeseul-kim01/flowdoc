package io.flowdoc.core.spec;

/**
 * Semantic markers derived from recognized annotations / boundary classification.
 *
 * @param transaction {@code @Transactional} boundary, if any
 * @param dataAccess  for data-boundary nodes: {@code "read"} or {@code "write"} (e.g. a
 *                    repository {@code save}/{@code delete} is a write); {@code null} otherwise
 */
public record Markers(TransactionMarker transaction, String dataAccess) {

    /** Convenience for the common case of only a transaction marker. */
    public Markers(TransactionMarker transaction) {
        this(transaction, null);
    }
}
