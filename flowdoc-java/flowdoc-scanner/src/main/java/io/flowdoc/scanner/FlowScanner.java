package io.flowdoc.scanner;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NormalAnnotationExpr;
import com.github.javaparser.ast.expr.SingleMemberAnnotationExpr;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import com.github.javaparser.utils.SourceRoot;
import io.flowdoc.core.spec.AnnotationInfo;
import io.flowdoc.core.spec.Auto;
import io.flowdoc.core.spec.Declared;
import io.flowdoc.core.spec.Edge;
import io.flowdoc.core.spec.FlowDocSpec;
import io.flowdoc.core.spec.Guard;
import io.flowdoc.core.spec.Location;
import io.flowdoc.core.spec.Markers;
import io.flowdoc.core.spec.Node;
import io.flowdoc.core.spec.Param;
import io.flowdoc.core.spec.Returns;
import io.flowdoc.core.spec.Sequence;
import io.flowdoc.core.spec.Site;
import io.flowdoc.core.spec.Source;
import io.flowdoc.core.spec.TransactionMarker;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * v0.1 static scanner. Parses a source root with JavaParser + SymbolSolver and
 * builds the shared spec: one {@link Node} per method, one {@link Edge} per
 * resolvable internal call, plus {@code @FlowEntry} sequences, {@code @Guarded}
 * guards, and {@code @Transactional} markers.
 *
 * <p>Principle (기획안 §11): never guess. A call that cannot be resolved to a
 * scanned method is dropped rather than fabricated.
 */
public final class FlowScanner {

    public FlowDocSpec scan(Path sourceRoot) throws IOException {
        SourceRoot root = new SourceRoot(sourceRoot.toAbsolutePath().normalize());
        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver());
        typeSolver.add(new JavaParserTypeSolver(sourceRoot.toAbsolutePath().normalize()));
        root.setParserConfiguration(
                new ParserConfiguration().setSymbolResolver(new JavaSymbolSolver(typeSolver)));

        root.tryToParse();
        List<CompilationUnit> units = root.getCompilationUnits();

        List<Node> nodes = new ArrayList<>();
        List<Edge> edges = new ArrayList<>();
        List<Guard> guards = new ArrayList<>();
        List<Sequence> sequences = new ArrayList<>();
        Set<String> nodeIds = new LinkedHashSet<>();

        // First pass: nodes, guards, sequences.
        for (CompilationUnit cu : units) {
            String file = relativeFile(sourceRoot, cu);
            for (MethodDeclaration method : cu.findAll(MethodDeclaration.class)) {
                if (hasAnnotation(method, "FlowIgnore")) {
                    continue;
                }
                String id = Ids.of(method);
                if (id == null || !nodeIds.add(id)) {
                    continue;
                }
                nodes.add(toNode(method, id, file));

                guardFor(method, id).ifPresent(guards::add);
                sequenceFor(method, id).ifPresent(sequences::add);
            }
        }

        // Second pass: edges — only between methods we actually scanned.
        for (CompilationUnit cu : units) {
            String file = relativeFile(sourceRoot, cu);
            for (MethodDeclaration method : cu.findAll(MethodDeclaration.class)) {
                if (hasAnnotation(method, "FlowIgnore")) {
                    continue;
                }
                String from = Ids.of(method);
                if (from == null || !nodeIds.contains(from)) {
                    continue;
                }
                for (MethodCallExpr call : method.findAll(MethodCallExpr.class)) {
                    String to = resolveTarget(call);
                    if (to == null || !nodeIds.contains(to)) {
                        continue; // unresolved or external — no guessing
                    }
                    int line = call.getBegin().map(p -> p.line).orElse(-1);
                    edges.add(new Edge(from, to, "sync", new Site(file, line), null, "concrete"));
                }
            }
        }

        Source source = new Source("java", "spring-boot", "static");
        return new FlowDocSpec(FlowDocSpec.VERSION, source, nodes, edges, guards, sequences, List.of());
    }

    private Node toNode(MethodDeclaration method, String id, String file) {
        List<Param> params = new ArrayList<>();
        for (Parameter p : method.getParameters()) {
            params.add(new Param(p.getNameAsString(), Ids.simpleType(p.getType().asString())));
        }
        Returns returns = method.getType().isVoidType()
                ? null
                : new Returns(Ids.simpleType(method.getType().asString()));

        List<AnnotationInfo> annotations = new ArrayList<>();
        for (AnnotationExpr a : method.getAnnotations()) {
            annotations.add(new AnnotationInfo(a.getNameAsString(), attributes(a)));
        }

        Auto auto = new Auto(params, returns, annotations);
        Declared declared = null; // Javadoc → declared lands in v0.2
        Markers markers = transactionMarker(method).map(Markers::new).orElse(null);

        String owner = method.findAncestor(TypeDeclaration.class)
                .map(TypeDeclaration::getNameAsString)
                .orElse(null);
        int line = method.getBegin().map(p -> p.line).orElse(-1);

        return new Node(id, method.getNameAsString(), owner, "method",
                new Location(file, line, null), auto, declared, markers);
    }

    private Optional<Guard> guardFor(MethodDeclaration method, String id) {
        return method.getAnnotationByName("Guarded").map(a -> {
            Map<String, String> attrs = attributes(a);
            String resource = strip(attrs.getOrDefault("resource", "unknown"));
            int permits = parseIntOr(attrs.get("permits"), 1);
            String type = attrs.getOrDefault("type", "SEMAPHORE").toUpperCase().contains("LOCK")
                    ? "lock" : "semaphore";
            return new Guard(id, type, resource, permits, "declared");
        });
    }

    private Optional<Sequence> sequenceFor(MethodDeclaration method, String id) {
        return method.getAnnotationByName("FlowEntry").map(a -> {
            String tag = strip(attributes(a).getOrDefault("value", "entry"));
            return new Sequence(tag, null, id, null, List.of());
        });
    }

    private Optional<TransactionMarker> transactionMarker(MethodDeclaration method) {
        return method.getAnnotationByName("Transactional").map(a -> {
            String propagation = attributes(a).get("propagation");
            return new TransactionMarker("open", propagation == null ? null : strip(propagation));
        });
    }

    private static String resolveTarget(MethodCallExpr call) {
        try {
            return Ids.of(call.resolve());
        } catch (RuntimeException e) {
            return null; // UnsolvedSymbolException and friends — drop the edge
        }
    }

    private static Map<String, String> attributes(AnnotationExpr a) {
        Map<String, String> attrs = new LinkedHashMap<>();
        if (a instanceof NormalAnnotationExpr normal) {
            normal.getPairs().forEach(p -> attrs.put(p.getNameAsString(), p.getValue().toString()));
        } else if (a instanceof SingleMemberAnnotationExpr single) {
            attrs.put("value", single.getMemberValue().toString());
        }
        return attrs;
    }

    private static boolean hasAnnotation(MethodDeclaration method, String name) {
        return method.getAnnotationByName(name).isPresent();
    }

    private static String relativeFile(Path sourceRoot, CompilationUnit cu) {
        return cu.getStorage()
                .map(s -> sourceRoot.toAbsolutePath().normalize()
                        .relativize(s.getPath().toAbsolutePath().normalize()).toString())
                .orElse("unknown");
    }

    private static String strip(String literal) {
        String s = literal.trim();
        if (s.length() >= 2 && s.startsWith("\"") && s.endsWith("\"")) {
            s = s.substring(1, s.length() - 1);
        }
        int dot = s.lastIndexOf('.');
        return dot >= 0 ? s.substring(dot + 1) : s; // Propagation.REQUIRED -> REQUIRED
    }

    private static int parseIntOr(String s, int fallback) {
        if (s == null) {
            return fallback;
        }
        try {
            return Integer.parseInt(s.trim());
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
