package io.flowdoc.core.spec;

/** The source location of a call site (where the edge originates). */
public record Site(String file, int line) {
}
