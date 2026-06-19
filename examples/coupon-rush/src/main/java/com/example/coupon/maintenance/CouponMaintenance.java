package com.example.coupon.maintenance;

import com.example.coupon.repository.CampaignRepository;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 주기적 점검 작업. {@code @FlowEntry} 없이 {@code @Scheduled} 트리거만으로
 * 진입점(source=auto)이 잡히는지 보여주는 데모.
 */
@Component
public class CouponMaintenance {

    private final CampaignRepository campaignRepository;

    public CouponMaintenance(CampaignRepository campaignRepository) {
        this.campaignRepository = campaignRepository;
    }

    @Scheduled(cron = "0 0 3 * * *")
    public void reportStock() {
        long campaigns = campaignRepository.count();
        log(campaigns);
    }

    private void log(long campaigns) {
        System.out.println("[maintenance] active campaigns: " + campaigns);
    }
}
