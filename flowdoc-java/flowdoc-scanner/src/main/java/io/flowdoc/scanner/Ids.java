package io.flowdoc.scanner;

import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;

import java.util.StringJoiner;

/**
 * Builds stable node ids of the form
 * {@code com.shop.order.OrderService#createOrder(CreateOrderCommand)}.
 *
 * <p>Both the declaration side and the resolved-call side reduce types to their
 * simple name so that a method and the calls targeting it produce the same id.
 */
final class Ids {

    private Ids() {
    }

    /** Id for a parsed method declaration, or {@code null} if its owner is unknown. */
    static String of(MethodDeclaration method) {
        // findAncestor returns a raw TypeDeclaration, so resolve the FQN as Object.
        Object fqn = method.findAncestor(TypeDeclaration.class)
                .flatMap(t -> t.getFullyQualifiedName())
                .orElse(null);
        if (fqn == null) {
            return null;
        }
        String owner = fqn.toString();
        StringJoiner params = new StringJoiner(",");
        method.getParameters().forEach(p -> params.add(simpleType(p.getType().asString())));
        return owner + "#" + method.getNameAsString() + "(" + params + ")";
    }

    /** Id for a resolved method call target. */
    static String of(ResolvedMethodDeclaration method) {
        StringJoiner params = new StringJoiner(",");
        for (int i = 0; i < method.getNumberOfParams(); i++) {
            params.add(simpleType(method.getParam(i).describeType()));
        }
        return method.declaringType().getQualifiedName() + "#" + method.getName() + "(" + params + ")";
    }

    /** Reduces {@code java.util.List<Foo>[]} to {@code List[]}. */
    static String simpleType(String type) {
        String t = type.trim();
        int generic = t.indexOf('<');
        if (generic >= 0) {
            t = t.substring(0, generic);
        }
        StringBuilder arraySuffix = new StringBuilder();
        while (t.endsWith("[]")) {
            arraySuffix.append("[]");
            t = t.substring(0, t.length() - 2).trim();
        }
        int dot = t.lastIndexOf('.');
        if (dot >= 0) {
            t = t.substring(dot + 1);
        }
        return t + arraySuffix;
    }
}
