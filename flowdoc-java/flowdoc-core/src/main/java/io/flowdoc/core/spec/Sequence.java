package io.flowdoc.core.spec;

import java.util.List;

/**
 * A single flow starting at an entry method. One screen in the UI.
 *
 * <p>{@code source} records how the entry was found: {@code "declared"} for an explicit
 * {@code @FlowEntry}, {@code "auto"} for one detected from a standard trigger annotation
 * (HTTP mapping, {@code @Scheduled}, {@code @KafkaListener}, {@code @EventListener}, …).
 */
public record Sequence(
        String tag,
        String title,
        String entry,
        String description,
        String source,
        Trigger trigger,
        List<TransactionSpan> transactions
) {
}
