package com.shop.order;

import io.flowdoc.annotation.FlowEntry;

/** Demo controller. Run the scanner against examples/sample-shop/src/main/java. */
public class OrderController {

    private final OrderService orderService = new OrderService();

    @FlowEntry("place-order")
    @PostMapping
    public Order placeOrder(PlaceOrderRequest request) {
        return orderService.createOrder(request);
    }

    // Stand-in for org.springframework.web.bind.annotation.PostMapping so the
    // sample is self-contained without pulling in Spring.
    @interface PostMapping {
    }
}
