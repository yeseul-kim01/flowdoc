package com.example.coupon.api;

import com.example.coupon.dto.IssueRequest;
import com.example.coupon.dto.IssueResult;
import com.example.coupon.service.CouponService;
import io.flowdoc.annotation.FlowDoc;
import io.flowdoc.annotation.FlowEntry;
import io.flowdoc.annotation.Param;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** HTTP entry point for the "first-come coupon" flow. */
@RestController
@RequestMapping("/api/campaigns")
public class CouponController {

    private final CouponService couponService;

    public CouponController(CouponService couponService) {
        this.couponService = couponService;
    }

    @FlowDoc(
            summary = "선착순 쿠폰 발급 진입점. 요청을 받아 발급 트랜잭션을 시작한다.",
            params = {
                    @Param(name = "campaignId", desc = "발급 대상 캠페인 ID (URL path)"),
                    @Param(name = "request", desc = "발급 요청 본문 — 수령할 사용자 식별자를 담는다")
            })
    @PostMapping("/{campaignId}/coupons")
    @FlowEntry("issue-coupon")
    public IssueResult issue(@PathVariable Long campaignId, @RequestBody IssueRequest request) {
        return couponService.issue(campaignId, request.userId());
    }
}
