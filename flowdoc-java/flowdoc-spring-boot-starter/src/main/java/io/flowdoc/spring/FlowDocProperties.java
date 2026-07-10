package io.flowdoc.spring;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Configuration for the live FlowDoc viewer endpoint. */
@ConfigurationProperties(prefix = "flowdoc")
public class FlowDocProperties {

    /** Whether the {@code /flowdoc} endpoint is registered. */
    private boolean enabled = true;

    /** Base path the viewer is served under. */
    private String path = "/flowdoc";

    /** Where the prebuilt spec lives. Any Spring resource location works. */
    private String specLocation = "classpath:flowdoc.json";

    /** Whether the runtime overlay (AOP trace agent) is active. */
    private boolean tracing = true;

    /** How many recent traces the in-memory ring buffer keeps. */
    private int maxTraces = 50;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getSpecLocation() {
        return specLocation;
    }

    public void setSpecLocation(String specLocation) {
        this.specLocation = specLocation;
    }

    public boolean isTracing() {
        return tracing;
    }

    public void setTracing(boolean tracing) {
        this.tracing = tracing;
    }

    public int getMaxTraces() {
        return maxTraces;
    }

    public void setMaxTraces(int maxTraces) {
        this.maxTraces = maxTraces;
    }
}
