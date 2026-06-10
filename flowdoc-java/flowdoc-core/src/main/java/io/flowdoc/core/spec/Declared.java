package io.flowdoc.core.spec;

import java.util.Map;

/** Developer-authored meaning: description and per-parameter docs. */
public record Declared(String description, Map<String, String> paramDocs) {
}
