package io.flowdoc.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Hints the concrete target of an interface call when several implementations
 * exist and static resolution would be {@code ambiguous}. FlowDoc never guesses;
 * it asks for this hint instead.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface FlowResolves {

    /** The implementation the call resolves to. */
    Class<?> value();
}
