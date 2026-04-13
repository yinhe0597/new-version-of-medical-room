package com.medical.stock.service;

import com.medical.stock.dto.DrugStockDTO;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class DrugStockService {
    private static final Pattern PACK_SPEC_PATTERN = Pattern.compile("^\\s*.+[xX×]\\s*\\d+\\s*[^\\d/]+\\s*/\\s*\\S+\\s*$");
    private static final Pattern PACK_AMOUNT_PATTERN = Pattern.compile("[xX×]\\s*(?<count>\\d+)\\s*(?<unit>[^\\d/\\s]+)\\s*/\\s*(?<packUnit>\\S+)\\s*$");
    private static final Pattern MIN_UNIT_PATTERN = Pattern.compile("^\\s*(?<count>\\d+)\\s*(?<unit>[^\\d\\s]+)\\s*$");

    public record ParsedPackSpec(int packAmount, String unitName, String packUnit) {}
    public record ParsedMinUnit(int minSaleAmount, String unitName) {}

    public record StockRecord(
            String recordType,
            String name,
            String specification,
            String unit,
            BigDecimal unitPrice,
            int quantity,
            String batchNo,
            String groupCode,
            int unitAmount
    ) {}

    public record GeneratedResult(StockRecord packRecord, StockRecord retailRecord) {}

    public ParsedPackSpec parseAndValidatePackSpec(String packSpecification) {
        if (packSpecification == null || packSpecification.trim().isEmpty()) {
            throw new IllegalArgumentException("packSpecification is required");
        }
        String spec = packSpecification.trim();
        if (!PACK_SPEC_PATTERN.matcher(spec).matches()) {
            throw new IllegalArgumentException("packSpecification format invalid");
        }
        Matcher m = PACK_AMOUNT_PATTERN.matcher(spec);
        if (!m.find()) {
            throw new IllegalArgumentException("packSpecification cannot parse amount");
        }
        int amount = Integer.parseInt(m.group("count"));
        String unit = m.group("unit").trim();
        String packUnit = m.group("packUnit").trim();
        if (amount <= 0) {
            throw new IllegalArgumentException("packAmount must be > 0");
        }
        if (unit.isEmpty() || packUnit.isEmpty()) {
            throw new IllegalArgumentException("packSpecification unit invalid");
        }
        return new ParsedPackSpec(amount, unit, packUnit);
    }

    public ParsedMinUnit parseAndValidateMinUnit(String minSaleUnit, String expectedUnitName) {
        if (minSaleUnit == null || minSaleUnit.trim().isEmpty()) {
            throw new IllegalArgumentException("minSaleUnit is required");
        }
        Matcher m = MIN_UNIT_PATTERN.matcher(minSaleUnit.trim());
        if (!m.matches()) {
            throw new IllegalArgumentException("minSaleUnit format invalid");
        }
        int count = Integer.parseInt(m.group("count"));
        String unit = m.group("unit").trim();
        if (count <= 0 || unit.isEmpty()) {
            throw new IllegalArgumentException("minSaleUnit invalid");
        }
        if (expectedUnitName != null && !expectedUnitName.isBlank() && !unit.equals(expectedUnitName.trim())) {
            throw new IllegalArgumentException("minSaleUnit unit mismatch");
        }
        return new ParsedMinUnit(count, unit);
    }

    public BigDecimal computeMinPriceThreshold(BigDecimal packPrice, int packAmount, int minSaleAmount) {
        Objects.requireNonNull(packPrice, "packPrice");
        if (packPrice.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("packPrice must be > 0");
        }
        if (packAmount <= 0 || minSaleAmount <= 0) {
            throw new IllegalArgumentException("amounts must be > 0");
        }
        if (packAmount % minSaleAmount != 0) {
            throw new IllegalArgumentException("packAmount must be divisible by minSaleAmount");
        }
        return packPrice
                .multiply(BigDecimal.valueOf(minSaleAmount))
                .divide(BigDecimal.valueOf(packAmount), 6, RoundingMode.HALF_UP);
    }

    public GeneratedResult generate(DrugStockDTO dto, String groupCode) {
        Objects.requireNonNull(dto, "dto");
        if (dto.getType() != 1) {
            throw new IllegalArgumentException("only type=1 supported by this generator");
        }
        String baseName = dto.getName().trim();
        if (baseName.isEmpty()) {
            throw new IllegalArgumentException("name is required");
        }
        String batchNo = dto.getBatchNo().trim();
        if (batchNo.isEmpty()) {
            throw new IllegalArgumentException("batchNo is required");
        }
        ParsedPackSpec pack = parseAndValidatePackSpec(dto.getPackSpecification());
        BigDecimal packPrice = Objects.requireNonNull(dto.getPackPrice(), "packPrice");
        if (packPrice.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("packPrice must be > 0");
        }
        int inboundPacks = dto.getInboundQuantity();
        if (inboundPacks <= 0) {
            throw new IllegalArgumentException("inboundQuantity must be > 0");
        }
        String gc = (groupCode == null || groupCode.isBlank()) ? java.util.UUID.randomUUID().toString() : groupCode;

        StockRecord packRecord = new StockRecord(
                "pack",
                baseName,
                dto.getPackSpecification().trim(),
                pack.packUnit(),
                packPrice.setScale(2, RoundingMode.HALF_UP),
                inboundPacks,
                batchNo,
                gc,
                pack.packAmount()
        );

        if (!dto.isRetailEnabled()) {
            return new GeneratedResult(packRecord, null);
        }

        ParsedMinUnit minUnit = parseAndValidateMinUnit(dto.getMinSaleUnit(), pack.unitName());
        BigDecimal minPrice = Objects.requireNonNull(dto.getMinSalePrice(), "minSalePrice");
        if (minPrice.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("minSalePrice must be > 0");
        }

        BigDecimal threshold = computeMinPriceThreshold(packPrice, pack.packAmount(), minUnit.minSaleAmount());
        if (minPrice.compareTo(threshold) <= 0) {
            throw new IllegalArgumentException("minSalePrice too low");
        }

        int totalUnits = inboundPacks * pack.packAmount();
        int retailQuantity = totalUnits / minUnit.minSaleAmount();

        String retailName = baseName + "(散)";
        String retailSpec = minUnit.minSaleAmount() + minUnit.unitName();
        StockRecord retailRecord = new StockRecord(
                "retail",
                retailName,
                retailSpec,
                minUnit.unitName(),
                minPrice.setScale(2, RoundingMode.HALF_UP),
                retailQuantity,
                batchNo,
                gc,
                minUnit.minSaleAmount()
        );

        return new GeneratedResult(packRecord, retailRecord);
    }

    public String uniqueKey(String name, String specification, String batchNo) {
        String n = (name == null) ? "" : name.trim().toLowerCase();
        String s = (specification == null) ? "" : specification.trim().toLowerCase();
        String b = (batchNo == null) ? "" : batchNo.trim().toLowerCase();
        if (n.isEmpty() || s.isEmpty() || b.isEmpty()) {
            throw new IllegalArgumentException("name/specification/batchNo required");
        }
        return n + "||" + s + "||" + b;
    }
}
