package com.example.coupon.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;

/** An issued coupon, tied to the campaign it was drawn from. */
@Entity
public class Coupon {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne
    private Campaign campaign;

    private Long userId;
    private String code;

    protected Coupon() {
    }

    public Coupon(Campaign campaign, Long userId) {
        this.campaign = campaign;
        this.userId = userId;
        this.code = "CPN-" + campaign.getId() + "-" + userId;
    }

    public String getCode() {
        return code;
    }
}
