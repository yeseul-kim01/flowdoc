package io.flowdoc.core.spec;

import java.util.List;

/** Optional runtime overlay: one recorded execution path over the structure graph. */
public record Trace(String traceId, String sequenceTag, List<Span> spans) {
}
