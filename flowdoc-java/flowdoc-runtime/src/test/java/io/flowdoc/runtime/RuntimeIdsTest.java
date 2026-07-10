package io.flowdoc.runtime;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Pins the runtime node-id format to the static scanner's {@code Ids.of}: owner
 * fully-qualified name, method name, simple parameter types (generics erased,
 * arrays kept, varargs reduced to the element type). These literals are the same
 * shape the scanner writes into {@code flowdoc.json}.
 */
class RuntimeIdsTest {

    private static final String OWNER = "io.flowdoc.runtime.RuntimeIdsTest.Sample";

    @Test
    void noArgs() {
        assertEquals(OWNER + "#noArgs()", id("noArgs"));
    }

    @Test
    void referenceParam() {
        assertEquals(OWNER + "#one(String)", id("one", String.class));
    }

    @Test
    void genericsAreErasedToSimpleName() {
        assertEquals(OWNER + "#gen(List)", id("gen", List.class));
        assertEquals(OWNER + "#map(Map)", id("map", Map.class));
    }

    @Test
    void arraysAreKept() {
        assertEquals(OWNER + "#arr(String[])", id("arr", String[].class));
    }

    @Test
    void primitivesKeepTheirName() {
        assertEquals(OWNER + "#prim(int,long)", id("prim", int.class, long.class));
    }

    @Test
    void varargsReduceToElementType() {
        // A varargs param is `String[]` in reflection but `String` in source — the
        // scanner sees the element type, so the runtime id must too.
        assertEquals(OWNER + "#vararg(int,String)", id("vararg", int.class, String[].class));
    }

    @Test
    void nestedTypeParamUsesSimpleName() {
        assertEquals(OWNER + "#nested(Inner)", id("nested", Sample.Inner.class));
    }

    private static String id(String method, Class<?>... params) {
        try {
            Method m = Sample.class.getDeclaredMethod(method, params);
            return RuntimeIds.nodeId(Sample.class, m);
        } catch (NoSuchMethodException e) {
            throw new AssertionError(e);
        }
    }

    @SuppressWarnings("unused")
    static class Sample {
        void noArgs() {
        }

        void one(String a) {
        }

        void gen(List<String> a) {
        }

        void map(Map<String, Integer> a) {
        }

        void arr(String[] a) {
        }

        void prim(int a, long b) {
        }

        void vararg(int x, String... rest) {
        }

        void nested(Inner i) {
        }

        static class Inner {
        }
    }
}
