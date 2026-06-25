package com.example.coupon;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Minimal real Spring Boot app used to exercise the FlowDoc static scanner end-to-end. */
@SpringBootApplication
@EnableAsync
@EnableScheduling
public class CouponRushApplication {

    public static void main(String[] args) {
        SpringApplication.run(CouponRushApplication.class, args);
    }
}
