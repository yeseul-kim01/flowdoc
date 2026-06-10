package io.flowdoc.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Declares the <em>meaning</em> of a concurrency guard. The parser can see that
 * {@code semaphore.acquire()} is called, but not which logical resource it
 * protects or with how many permits — that intent is declared here.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Guarded {

    /** Logical resource protected by the guard, e.g. {@code "inventory"}. */
    String resource();

    GuardType type() default GuardType.SEMAPHORE;

    int permits() default 1;
}
