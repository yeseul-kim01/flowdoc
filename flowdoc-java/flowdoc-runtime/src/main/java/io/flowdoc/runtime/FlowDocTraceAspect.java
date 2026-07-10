package io.flowdoc.runtime;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.core.Ordered;

import java.lang.reflect.Method;

/**
 * Records an enter/exit span around every method of a stereotyped Spring bean
 * (controller, service, repository) and hands it to the {@link TraceRecorder}. The
 * span's node id is reproduced via {@link RuntimeIds} so it matches the static
 * scanner — the trace lands on the structure graph the UI already draws.
 *
 * <p>Runs at {@link Ordered#HIGHEST_PRECEDENCE} so a span wraps the transaction
 * boundary (and everything else) rather than nesting inside it. This also places the
 * advice <em>inside</em> Spring's {@code @Async} interceptor, so an {@code @Async}
 * method is observed here on its worker thread — the {@link FlowDocTraceTaskDecorator}
 * carries the caller's trace across the hop so the span still lands in it.
 *
 * <p><b>Known blind spot:</b> Spring AOP only advises calls that cross the proxy,
 * so a bean calling its own method ({@code this.foo()}) is invisible here. The
 * static graph still shows that edge — the gap between "declared" and "observed"
 * is itself the signal (Phase 3 surfaces it explicitly).
 */
@Aspect
public class FlowDocTraceAspect implements Ordered {

    private final TraceRecorder recorder;

    public FlowDocTraceAspect(TraceRecorder recorder) {
        this.recorder = recorder;
    }

    @Pointcut("@within(org.springframework.web.bind.annotation.RestController)"
            + " || @within(org.springframework.stereotype.Controller)"
            + " || @within(org.springframework.stereotype.Service)"
            + " || @within(org.springframework.stereotype.Repository)")
    void stereotypedBean() {
    }

    // Application beans only — the static graph never models framework or FlowDoc
    // internals, so tracing them (e.g. Spring's BasicErrorController) is pure noise.
    @Pointcut("!within(org.springframework..*) && !within(io.flowdoc..*)")
    void applicationCode() {
    }

    @Around("stereotypedBean() && applicationCode()")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        Object handle = null;
        try {
            handle = recorder.enter(nodeId(pjp));
        } catch (RuntimeException ignored) {
            // Tracing must never break the request it observes.
        }
        try {
            return pjp.proceed();
        } catch (Throwable t) {
            recorder.markError(t);
            throw t;
        } finally {
            if (handle != null) {
                recorder.exit(handle);
            }
        }
    }

    private static String nodeId(ProceedingJoinPoint pjp) {
        MethodSignature sig = (MethodSignature) pjp.getSignature();
        Method method = sig.getMethod();
        Object target = pjp.getTarget();
        Class<?> targetClass = (target != null) ? target.getClass() : sig.getDeclaringType();
        return RuntimeIds.nodeId(method, targetClass);
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
