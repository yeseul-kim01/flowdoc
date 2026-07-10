package io.flowdoc.core.spec;

import java.util.List;

/**
 * Optional runtime overlay: one recorded execution path over the structure graph.
 *
 * <p>{@code error} is the type (and short message) of the exception that aborted
 * the call chain, or {@code null} if it completed normally — it lets the viewer
 * tell a failed request from a successful one in the trace list. {@code errorSpanId}
 * points at the deepest <em>observed</em> span the exception propagated through (the
 * actual throw may be deeper, below the agent's visibility), letting the viewer
 * localize the failure on the graph.
 */
public record Trace(String traceId, String sequenceTag, List<Span> spans,
                    String error, String errorSpanId) {
}
