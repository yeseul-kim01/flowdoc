package io.flowdoc.scanner;

import io.flowdoc.core.io.SpecWriter;
import io.flowdoc.core.spec.FlowDocSpec;

import java.nio.file.Path;

/** CLI entry point: scan a source root and write {@code flowdoc.json}. */
public final class Main {

    private Main() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: flowdoc-scanner <source-root> [output.json]");
            System.exit(2);
            return;
        }
        Path sourceRoot = Path.of(args[0]);
        Path out = Path.of(args.length >= 2 ? args[1] : "flowdoc.json");

        FlowDocSpec spec = new FlowScanner().scan(sourceRoot);
        SpecWriter.write(spec, out);

        System.out.printf("FlowDoc: %d nodes, %d edges, %d guards, %d sequences -> %s%n",
                spec.nodes().size(), spec.edges().size(), spec.guards().size(),
                spec.sequences().size(), out.toAbsolutePath());
    }
}
