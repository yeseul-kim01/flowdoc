package io.flowdoc.annotation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a method as a sequence entry point and names the flow.
 * One {@code @FlowEntry} is one screen in the FlowDoc UI.
 *
 * <p>This is the single thing the static parser cannot infer: which of the many
 * possible entry points (controllers, listeners, schedulers) starts a flow the
 * author cares about.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface FlowEntry {

    /** Stable tag for this sequence, e.g. {@code "place-order"}. */
    String value();
}
