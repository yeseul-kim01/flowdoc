package io.flowdoc.scanner;

import io.flowdoc.core.spec.Edge;
import io.flowdoc.core.spec.FlowDocSpec;
import io.flowdoc.core.spec.Guard;
import io.flowdoc.core.spec.Node;
import io.flowdoc.core.spec.Sequence;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FlowScannerTest {

    @TempDir
    Path sourceRoot;

    @Test
    void scansNodesEdgesGuardAndSequence() throws IOException {
        write("com/shop/OrderController.java", """
                package com.shop;

                public class OrderController {
                    private final OrderService service = new OrderService();

                    @FlowEntry("place-order")
                    @PostMapping
                    public Order placeOrder(PlaceOrderRequest request) {
                        return service.createOrder(request);
                    }
                }
                """);
        write("com/shop/OrderService.java", """
                package com.shop;

                public class OrderService {
                    @Transactional
                    public Order createOrder(PlaceOrderRequest request) {
                        return reserve(request);
                    }

                    @Guarded(resource = "inventory", permits = 1)
                    public Order reserve(PlaceOrderRequest request) {
                        return new Order();
                    }
                }
                """);
        write("com/shop/Order.java", "package com.shop; public class Order {}");
        write("com/shop/PlaceOrderRequest.java", "package com.shop; public class PlaceOrderRequest {}");

        FlowDocSpec spec = new FlowScanner().scan(sourceRoot);

        // Sequence from @FlowEntry
        assertEquals(1, spec.sequences().size());
        Sequence seq = spec.sequences().get(0);
        assertEquals("place-order", seq.tag());
        assertEquals("com.shop.OrderController#placeOrder(PlaceOrderRequest)", seq.entry());

        // Node for the entry, with the standard annotation captured as auto
        Node entry = node(spec, "com.shop.OrderController#placeOrder(PlaceOrderRequest)");
        assertEquals("placeOrder", entry.simpleName());
        assertEquals("OrderController", entry.owner());
        assertTrue(entry.auto().annotations().stream().anyMatch(a -> a.name().equals("PostMapping")));

        // Transactional marker on createOrder
        Node create = node(spec, "com.shop.OrderService#createOrder(PlaceOrderRequest)");
        assertNotNull(create.markers());
        assertEquals("open", create.markers().transaction().boundary());

        // Guard from @Guarded
        assertEquals(1, spec.guards().size());
        Guard guard = spec.guards().get(0);
        assertEquals("inventory", guard.resource());
        assertEquals(1, guard.permits());
        assertEquals("semaphore", guard.type());

        // Internal edge controller -> service resolved and kept
        assertTrue(spec.edges().stream().anyMatch(this::isControllerToService),
                "expected resolved edge placeOrder -> createOrder");
    }

    private boolean isControllerToService(Edge e) {
        return e.from().equals("com.shop.OrderController#placeOrder(PlaceOrderRequest)")
                && e.to().equals("com.shop.OrderService#createOrder(PlaceOrderRequest)");
    }

    private Node node(FlowDocSpec spec, String id) {
        return spec.nodes().stream()
                .filter(n -> n.id().equals(id))
                .findFirst()
                .orElseThrow(() -> new AssertionError("node not found: " + id));
    }

    private void write(String relPath, String content) throws IOException {
        Path file = sourceRoot.resolve(relPath);
        Files.createDirectories(file.getParent());
        Files.writeString(file, content);
    }
}
