package io.flowdoc.core.spec;

import java.util.Map;

/**
 * How a flow is entered, in language-neutral terms. Each collector maps its own
 * framework (Spring {@code @GetMapping}/{@code @Scheduled}/…, FastAPI route decorators,
 * …) onto the same shape, so the shared UI renders triggers identically without knowing
 * any framework. {@code kind} drives the badge; {@code detail} carries the specifics.
 *
 * @param kind   one of {@code http}, {@code scheduled}, {@code messaging}, {@code event}, {@code websocket}
 * @param label  short human-facing string, e.g. {@code "GET /orders"} or {@code "Scheduled · 0 0 3 * * *"}
 * @param detail structured specifics, e.g. {@code {verb, path}} / {@code {cron}} / {@code {broker, destination}}
 */
public record Trigger(String kind, String label, Map<String, String> detail) {
}
