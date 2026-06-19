package com.example.coupon.repository;

import com.example.coupon.domain.Campaign;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CampaignRepository extends JpaRepository<Campaign, Long> {
}
