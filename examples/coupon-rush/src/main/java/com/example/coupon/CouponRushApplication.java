package com.example.coupon;

import com.example.coupon.domain.Campaign;
import com.example.coupon.repository.CampaignRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
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

    /**
     * Seeds one in-stock campaign so a POST to {@code /api/campaigns/1/coupons} takes the
     * success path — issuance commits, then fires the {@code @Async} notification whose
     * span the runtime overlay stitches back into the request trace (Phase 2). A plain
     * config bean, so the trace aspect (stereotyped beans only) never records it.
     */
    @Bean
    CommandLineRunner seedCampaign(CampaignRepository campaigns) {
        return args -> campaigns.save(new Campaign(1L, "launch-day", 100));
    }
}
