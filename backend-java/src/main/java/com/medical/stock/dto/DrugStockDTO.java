package com.medical.stock.dto;

import java.math.BigDecimal;
import java.util.Objects;

public final class DrugStockDTO {
    private final int type;
    private final String name;
    private final String batchNo;

    private final String packSpecification;
    private final BigDecimal packPrice;
    private final int inboundQuantity;

    private final boolean retailEnabled;
    private final String minSaleUnit;
    private final BigDecimal minSalePrice;

    private DrugStockDTO(Builder b) {
        this.type = b.type;
        this.name = b.name;
        this.batchNo = b.batchNo;
        this.packSpecification = b.packSpecification;
        this.packPrice = b.packPrice;
        this.inboundQuantity = b.inboundQuantity;
        this.retailEnabled = b.retailEnabled;
        this.minSaleUnit = b.minSaleUnit;
        this.minSalePrice = b.minSalePrice;
    }

    public int getType() {
        return type;
    }

    public String getName() {
        return name;
    }

    public String getBatchNo() {
        return batchNo;
    }

    public String getPackSpecification() {
        return packSpecification;
    }

    public BigDecimal getPackPrice() {
        return packPrice;
    }

    public int getInboundQuantity() {
        return inboundQuantity;
    }

    public boolean isRetailEnabled() {
        return retailEnabled;
    }

    public String getMinSaleUnit() {
        return minSaleUnit;
    }

    public BigDecimal getMinSalePrice() {
        return minSalePrice;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private int type = 1;
        private String name;
        private String batchNo;
        private String packSpecification;
        private BigDecimal packPrice;
        private int inboundQuantity = 1;
        private boolean retailEnabled;
        private String minSaleUnit;
        private BigDecimal minSalePrice;

        public Builder type(int type) {
            this.type = type;
            return this;
        }

        public Builder name(String name) {
            this.name = name;
            return this;
        }

        public Builder batchNo(String batchNo) {
            this.batchNo = batchNo;
            return this;
        }

        public Builder packSpecification(String packSpecification) {
            this.packSpecification = packSpecification;
            return this;
        }

        public Builder packPrice(BigDecimal packPrice) {
            this.packPrice = packPrice;
            return this;
        }

        public Builder inboundQuantity(int inboundQuantity) {
            this.inboundQuantity = inboundQuantity;
            return this;
        }

        public Builder retailEnabled(boolean retailEnabled) {
            this.retailEnabled = retailEnabled;
            return this;
        }

        public Builder minSaleUnit(String minSaleUnit) {
            this.minSaleUnit = minSaleUnit;
            return this;
        }

        public Builder minSalePrice(BigDecimal minSalePrice) {
            this.minSalePrice = minSalePrice;
            return this;
        }

        public DrugStockDTO build() {
            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(batchNo, "batchNo");
            if (type == 1) {
                Objects.requireNonNull(packSpecification, "packSpecification");
                Objects.requireNonNull(packPrice, "packPrice");
            }
            return new DrugStockDTO(this);
        }
    }
}

