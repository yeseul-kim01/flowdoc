package io.flowdoc.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Connects an event publication to its handler when type matching alone cannot
 * infer the link. Rendered as a decoupled (dashed) {@code event} edge.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface FlowLink {

    /** The published event type. */
    Class<?> event();

    /** Handler reference, e.g. {@code "OrderPlacedHandler#on"}. */
    String to();
}
