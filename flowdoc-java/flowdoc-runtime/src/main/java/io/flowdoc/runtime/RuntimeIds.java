package io.flowdoc.runtime;

import org.springframework.aop.support.AopUtils;
import org.springframework.core.BridgeMethodResolver;
import org.springframework.util.ClassUtils;

import java.lang.reflect.Method;
import java.util.StringJoiner;

/**
 * Reproduces, from reflection at runtime, the exact node id the static scanner
 * emits from source ({@code io.flowdoc.scanner.Ids}). The format is
 * {@code com.shop.order.OrderService#createOrder(CreateOrderCommand)} — the
 * owner's fully-qualified name, the method name, and parameter <em>simple</em>
 * type names (generics erased, arrays kept).
 *
 * <p>If these two ids disagree by a single character the runtime trace will not
 * land on the static node, so the correlation rules here mirror the scanner's
 * {@code simpleType} byte-for-byte, plus three runtime-only concerns the source
 * side never sees:
 *
 * <ul>
 *   <li><b>CGLIB proxies</b> — a Spring bean is advised through a
 *       {@code Foo$$SpringCGLIB$$...} subclass; {@link ClassUtils#getUserClass}
 *       recovers the user class so the owner matches the source class.</li>
 *   <li><b>Bridge / most-specific methods</b> — generic overrides compile to
 *       synthetic bridge methods; we resolve to the real declared method so the
 *       owner and signature match what the scanner parsed.</li>
 *   <li><b>Nested classes</b> — reflection names them {@code Outer$Inner} while
 *       JavaParser's fully-qualified name uses {@code Outer.Inner}; we normalise
 *       {@code '$'} to {@code '.'}.</li>
 * </ul>
 */
public final class RuntimeIds {

    private RuntimeIds() {
    }

    /**
     * Node id for a method invoked on a Spring bean of {@code targetClass}.
     * Resolves the most-specific, un-bridged declaration before formatting.
     */
    public static String nodeId(Method method, Class<?> targetClass) {
        Method specific = (targetClass != null)
                ? AopUtils.getMostSpecificMethod(method, targetClass)
                : method;
        Method bridged = BridgeMethodResolver.findBridgedMethod(specific);
        Class<?> owner = ClassUtils.getUserClass(bridged.getDeclaringClass());
        return format(fqn(owner), bridged);
    }

    /** Node id for a plain method/owner pair (used by tests and non-AOP callers). */
    public static String nodeId(Class<?> owner, Method method) {
        Method bridged = BridgeMethodResolver.findBridgedMethod(method);
        return format(fqn(ClassUtils.getUserClass(owner)), bridged);
    }

    /** JavaParser renders nested types with dots; reflection uses {@code '$'}. */
    private static String fqn(Class<?> owner) {
        return owner.getName().replace('$', '.');
    }

    private static String format(String ownerFqn, Method method) {
        Class<?>[] params = method.getParameterTypes();
        boolean varargs = method.isVarArgs();
        StringJoiner joiner = new StringJoiner(",");
        for (int i = 0; i < params.length; i++) {
            Class<?> type = params[i];
            // The scanner sees a varargs parameter as its element type (`String`),
            // not the array reflection reports (`String[]`); strip the array layer.
            if (varargs && i == params.length - 1 && type.isArray()) {
                type = type.getComponentType();
            }
            joiner.add(type.getSimpleName());
        }
        return ownerFqn + "#" + method.getName() + "(" + joiner + ")";
    }
}
