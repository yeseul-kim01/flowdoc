package io.flowdoc.runtime;

import org.springframework.core.task.TaskDecorator;

/**
 * Carries a trace across an {@code @Async} thread hop so the async method's span joins
 * the caller's trace instead of splitting into its own (or vanishing).
 *
 * <p>Spring Boot's {@code TaskExecutionAutoConfiguration} applies a single
 * {@link TaskDecorator} bean to the auto-configured {@code applicationTaskExecutor} —
 * the executor {@code @Async} uses by default — so registering this bean is all the
 * wiring an app on the default executor needs. Apps that define their own executor must
 * set this decorator on it themselves.
 *
 * <p>Spring's {@code @Async} advice runs outside the {@link FlowDocTraceAspect}, so
 * {@link #decorate} runs on the submitting thread while its live trace is still open: it
 * snapshots the caller frame and holds the trace open. The returned task, on the worker
 * thread, installs that link so the aspect's first span there continues the caller's
 * trace, then closes the scope. A task submitted with no active caller trace is returned
 * untouched.
 */
public final class FlowDocTraceTaskDecorator implements TaskDecorator {

    private final TraceRecorder recorder;

    public FlowDocTraceTaskDecorator(TraceRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public Runnable decorate(Runnable runnable) {
        TraceRecorder.AsyncLink link = recorder.captureAsyncParent();
        if (link == null) {
            return runnable;
        }
        // Defer the caller trace's flush until this child has run (settled below).
        recorder.armAsync(link);
        return () -> {
            recorder.beginAsyncScope(link);
            try {
                runnable.run();
            } finally {
                recorder.endAsyncScope();
                // If the async method wasn't advised, no span consumed the scope — release
                // the arm so the deferred trace can still flush.
                if (!link.consumed()) {
                    recorder.cancelAsync(link);
                }
            }
        };
    }
}
