package io.flowdoc.core.io;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.flowdoc.core.spec.FlowDocSpec;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Serializes a {@link FlowDocSpec} to the shared JSON format. */
public final class SpecWriter {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .setSerializationInclusion(JsonInclude.Include.NON_NULL)
            .enable(SerializationFeature.INDENT_OUTPUT);

    private SpecWriter() {
    }

    public static String toJson(FlowDocSpec spec) {
        try {
            return MAPPER.writeValueAsString(spec);
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to serialize FlowDoc spec", e);
        }
    }

    public static void write(FlowDocSpec spec, Path out) throws IOException {
        Path parent = out.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(out, toJson(spec));
    }
}
