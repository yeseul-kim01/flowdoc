package io.flowdoc.core.spec;

import java.util.List;

/** A single flow starting at a {@code @FlowEntry} method. One screen in the UI. */
public record Sequence(
        String tag,
        String title,
        String entry,
        String description,
        List<TransactionSpan> transactions
) {
}
