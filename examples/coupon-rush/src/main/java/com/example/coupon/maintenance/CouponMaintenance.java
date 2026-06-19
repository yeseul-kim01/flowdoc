package com.example.coupon.maintenance;

import com.example.coupon.repository.CampaignRepository;
import com.example.coupon.repository.CouponRepository;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 주기적 점검 작업. {@code @FlowEntry} 없이 {@code @Scheduled} 트리거만으로
 * 진입점(source=auto)이 잡히는지 + 트랜잭션 밖 쓰기(원자성 스멜)가 표시되는지 보여주는 데모.
 */
@Component
public class CouponMaintenance {

    private final CampaignRepository campaignRepository;
    private final CouponRepository couponRepository;

    public CouponMaintenance(CampaignRepository campaignRepository, CouponRepository couponRepository) {
        this.campaignRepository = campaignRepository;
        this.couponRepository = couponRepository;
    }

    // @Transactional 없음 — 아래 삭제 쓰기는 트랜잭션 밖에서 일어난다 (FlowDoc이 ⚠로 표시).
    @Scheduled(cron = "0 0 3 * * *")
    public void reportStock() {
        long campaigns = campaignRepository.count();   // read
        couponRepository.deleteSoldOut();              // write — outside any @Transactional
        log(campaigns);
    }

    private void log(long campaigns) {
        System.out.println("[maintenance] active campaigns: " + campaigns);
    }
}
