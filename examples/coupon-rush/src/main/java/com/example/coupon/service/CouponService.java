package com.example.coupon.service;

import com.example.coupon.domain.Campaign;
import com.example.coupon.domain.Coupon;
import com.example.coupon.dto.IssueResult;
import com.example.coupon.repository.CampaignRepository;
import com.example.coupon.repository.CouponRepository;
import io.flowdoc.annotation.Guarded;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Core issuance logic: one transaction, a concurrency guard on the limited stock. */
@Service
public class CouponService {

    private final CouponRepository couponRepository;
    private final CampaignRepository campaignRepository;
    private final NotificationService notificationService;

    public CouponService(CouponRepository couponRepository,
                         CampaignRepository campaignRepository,
                         NotificationService notificationService) {
        this.couponRepository = couponRepository;
        this.campaignRepository = campaignRepository;
        this.notificationService = notificationService;
    }

    /**
     * 쿠폰 한 건 발급을 하나의 트랜잭션으로 처리한다: 재고 예약 → 저장 → 발급 알림.
     * 재고 차감이 실패하면 전체가 롤백된다.
     *
     * @param campaignId 발급 대상 캠페인 식별자
     * @param userId     쿠폰을 수령할 사용자 식별자
     */
    @Transactional
    public IssueResult issue(Long campaignId, Long userId) {
        Campaign campaign = reserveStock(campaignId);
        Coupon coupon = couponRepository.save(new Coupon(campaign, userId));
        notificationService.notifyIssued(userId, coupon.getCode());
        return new IssueResult(coupon.getCode(), campaign.getRemaining());
    }

    /**
     * 캠페인의 남은 재고를 한 번에 한 발급자만 만지도록 보호하며 차감한다.
     *
     * @param campaignId 재고를 차감할 캠페인 식별자
     */
    @Guarded(resource = "coupon-stock", permits = 1)
    public Campaign reserveStock(Long campaignId) {
        Campaign campaign = campaignRepository.findById(campaignId)
                .orElseThrow(() -> new IllegalArgumentException("no such campaign: " + campaignId));
        decrement(campaign);
        return campaign;
    }

    private void decrement(Campaign campaign) {
        campaign.decrementRemaining();
    }

    /** 캠페인의 현재 남은 재고 수량 (조회 전용). */
    public int remaining(Long campaignId) {
        return campaignRepository.findById(campaignId)
                .map(Campaign::getRemaining)
                .orElse(0);
    }
}
