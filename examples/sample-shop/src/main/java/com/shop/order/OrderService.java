package com.shop.order;

import io.flowdoc.annotation.Guarded;

public class OrderService {

    private final InventoryService inventory = new InventoryService();

    @Transactional
    public Order createOrder(PlaceOrderRequest request) {
        inventory.reserve(request);
        return save(request);
    }

    @Guarded(resource = "inventory", permits = 1)
    public void reserveSeat(PlaceOrderRequest request) {
        inventory.reserve(request);
    }

    private Order save(PlaceOrderRequest request) {
        return new Order();
    }

    // Stand-in for org.springframework.transaction.annotation.Transactional.
    @interface Transactional {
        String propagation() default "REQUIRED";
    }
}
