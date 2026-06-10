package io.flowdoc.annotation;

/** A single parameter description used inside {@link FlowDoc}. */
public @interface Param {

    String name();

    String desc();
}
