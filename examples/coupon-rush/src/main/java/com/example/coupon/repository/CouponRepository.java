package com.example.coupon.repository;

import com.example.coupon.domain.Coupon;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface CouponRepository extends JpaRepository<Coupon, Long> {

    @Modifying
    @Query("delete from Coupon c where c.campaign.remaining = 0")
    int deleteSoldOut();
}
