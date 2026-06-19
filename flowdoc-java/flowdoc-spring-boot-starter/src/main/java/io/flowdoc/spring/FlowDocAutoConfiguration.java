package io.flowdoc.spring;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;

/**
 * Registers the live FlowDoc viewer, Swagger-style. Add this starter to a Spring
 * Boot app and three routes appear under {@code flowdoc.path} (default {@code /flowdoc}):
 *
 * <ul>
 *   <li>{@code GET /flowdoc}        → redirect to {@code /flowdoc/}</li>
 *   <li>{@code GET /flowdoc/}       → the shared HTML viewer</li>
 *   <li>{@code GET /flowdoc/flowdoc.json} → the prebuilt spec the viewer fetches</li>
 * </ul>
 *
 * <p>The spec is <em>prebuilt</em>: the static scanner emits {@code flowdoc.json}
 * into the app's resources at build time; this endpoint only serves it. (A running
 * jar has no source to scan — runtime self-collection is the later AOP agent.)
 */
@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnProperty(prefix = "flowdoc", name = "enabled", havingValue = "true", matchIfMissing = true)
@EnableConfigurationProperties(FlowDocProperties.class)
public class FlowDocAutoConfiguration {

    private static final String VIEWER = "classpath:flowdoc/index.html";

    @Bean
    public RouterFunction<ServerResponse> flowDocRouter(FlowDocProperties props, ResourceLoader loader) {
        String base = props.getPath();
        byte[] viewer = read(loader.getResource(VIEWER));

        return RouterFunctions.route()
                .GET(base, req -> ServerResponse.temporaryRedirect(URI.create(base + "/")).build())
                .GET(base + "/", req -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_HTML)
                        .body(viewer))
                .GET(base + "/flowdoc.json", req -> serveSpec(loader, props.getSpecLocation()))
                .build();
    }

    private static ServerResponse serveSpec(ResourceLoader loader, String location) {
        Resource spec = loader.getResource(location);
        if (!spec.exists()) {
            return ServerResponse.status(404)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("FlowDoc: no spec at '" + location + "'. Run the scanner to emit "
                            + "flowdoc.json into the app's resources.");
        }
        return ServerResponse.ok().contentType(MediaType.APPLICATION_JSON).body(read(spec));
    }

    private static byte[] read(Resource resource) {
        try {
            return resource.getInputStream().readAllBytes();
        } catch (IOException e) {
            throw new UncheckedIOException("FlowDoc: cannot read " + resource, e);
        }
    }
}
