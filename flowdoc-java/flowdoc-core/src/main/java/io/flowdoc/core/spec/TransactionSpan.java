package io.flowdoc.core.spec;

import java.util.List;

/** A transaction within a sequence: the owning node and the calls it covers. */
public record TransactionSpan(String owner, List<String> covers) {
}
