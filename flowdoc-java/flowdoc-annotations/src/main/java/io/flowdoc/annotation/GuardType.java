package io.flowdoc.annotation;

/** The kind of concurrency guard a {@link Guarded} method represents. */
public enum GuardType {
    SEMAPHORE,
    LOCK
}
