package io.flowdoc.core.spec;

/** Where a node lives in source. {@code module} may be null for single-module builds. */
public record Location(String file, int line, String module) {
}
