package io.flowdoc.spring;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.flowdoc.runtime.FlowDocTraceAspect;
import io.flowdoc.runtime.FlowDocTraceTaskDecorator;
import io.flowdoc.runtime.TraceRecorder;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

/**
 * Wires the v0.3 runtime overlay into a Spring Boot app: the {@link TraceRecorder}
 * and the {@link FlowDocTraceAspect} that feeds it, plus two routes under
 * {@code flowdoc.path}:
 *
 * <ul>
 *   <li>{@code GET /flowdoc/traces.json}  → the recent recorded traces</li>
 *   <li>{@code DELETE /flowdoc/traces}    → clear the buffer (handy while demoing)</li>
 * </ul>
 *
 * <p>Active only when AspectJ is on the classpath (it is, via the starter's
 * {@code flowdoc-runtime} dependency) and {@code flowdoc.tracing} is not turned off.
 * The presence of aspectjweaver is also what makes Spring Boot's AOP autoconfig
 * switch on @AspectJ proxying, so the aspect actually takes effect.
 */
@AutoConfiguration(after = FlowDocAutoConfiguration.class)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass(Aspect.class)
@ConditionalOnProperty(prefix = "flowdoc", name = "tracing", havingValue = "true", matchIfMissing = true)
public class FlowDocRuntimeAutoConfiguration {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .setSerializationInclusion(JsonInclude.Include.NON_NULL);

    @Bean
    @ConditionalOnMissingBean
    public TraceRecorder flowDocTraceRecorder(FlowDocProperties props) {
        return new TraceRecorder(props.getMaxTraces());
    }

    @Bean
    @ConditionalOnMissingBean
    public FlowDocTraceAspect flowDocTraceAspect(TraceRecorder recorder) {
        return new FlowDocTraceAspect(recorder);
    }

    /**
     * Stitches {@code @Async} calls into their caller's trace. Spring Boot's
     * {@code TaskExecutionAutoConfiguration} applies a single {@link org.springframework.core.task.TaskDecorator}
     * bean to the auto-configured {@code applicationTaskExecutor} that {@code @Async} uses
     * by default — so this bean is the whole wiring for apps on the default executor.
     */
    @Bean
    @ConditionalOnMissingBean
    public FlowDocTraceTaskDecorator flowDocTraceTaskDecorator(TraceRecorder recorder) {
        return new FlowDocTraceTaskDecorator(recorder);
    }

    @Bean
    public RouterFunction<ServerResponse> flowDocTraceRouter(FlowDocProperties props, TraceRecorder recorder) {
        String base = props.getPath();
        return RouterFunctions.route()
                .GET(base + "/traces.json", req -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(toJson(recorder)))
                .DELETE(base + "/traces", req -> {
                    recorder.clear();
                    return ServerResponse.noContent().build();
                })
                .build();
    }

    private static String toJson(TraceRecorder recorder) {
        try {
            return MAPPER.writeValueAsString(recorder.traces());
        } catch (JsonProcessingException e) {
            return "[]";
        }
    }
}
