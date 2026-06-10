package io.flowdoc.core.spec;

/** Provenance of a spec: which language/framework, produced by which collector. */
public record Source(String language, String framework, String collector) {
}
