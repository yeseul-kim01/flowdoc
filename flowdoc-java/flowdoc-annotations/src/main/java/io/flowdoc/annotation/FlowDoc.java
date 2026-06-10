package io.flowdoc.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Optional structured description, used when Javadoc is not the right home for
 * the explanation. Purely {@code declared} information.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface FlowDoc {

    String summary() default "";

    Param[] params() default {};
}
