package io.flowdoc.core.spec;

import java.util.Map;

/** A standard annotation read off a node, with its attributes as raw strings. */
public record AnnotationInfo(String name, Map<String, String> attributes) {
}
