package com.example.coupon.service;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

/** Post-commit notification — fires asynchronously, outside the issuance transaction. */
@Service
public class NotificationService {

    @Async
    public void notifyIssued(Long userId, String couponCode) {
        String message = render(userId, couponCode);
        dispatch(message);
    }

    private String render(Long userId, String couponCode) {
        return "user " + userId + " received coupon " + couponCode;
    }

    private void dispatch(String message) {
        // Stand-in for a real push/email gateway.
        System.out.println("[notify] " + message);
    }
}
