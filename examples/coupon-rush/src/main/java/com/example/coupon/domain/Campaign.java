package com.example.coupon.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

/** A coupon campaign with a limited remaining stock. */
@Entity
public class Campaign {

    @Id
    private Long id;
    private String name;
    private int remaining;

    protected Campaign() {
    }

    public Campaign(Long id, String name, int remaining) {
        this.id = id;
        this.name = name;
        this.remaining = remaining;
    }

    public void decrementRemaining() {
        if (remaining <= 0) {
            throw new IllegalStateException("sold out");
        }
        remaining--;
    }

    public Long getId() {
        return id;
    }

    public int getRemaining() {
        return remaining;
    }
}
