package com.medical.stock.service;

import com.medical.stock.dto.DrugStockDTO;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

public class DrugStockServiceTest {
    private final DrugStockService service = new DrugStockService();

    @Test
    void validatePackSpecRegex() {
        assertDoesNotThrow(() -> service.parseAndValidatePackSpec("20 mg×100粒/瓶"));
        assertThrows(IllegalArgumentException.class, () -> service.parseAndValidatePackSpec("20mg 100粒 瓶"));
    }

    @Test
    void minPriceThreshold() {
        BigDecimal t = service.computeMinPriceThreshold(new BigDecimal("10.00"), 100, 2);
        assertEquals(new BigDecimal("0.200000"), t);
    }

    @Test
    void quantityConversion() {
        DrugStockDTO dto = DrugStockDTO.builder()
                .type(1)
                .name("药品A")
                .batchNo("B001")
                .packSpecification("20 mg×100粒/瓶")
                .packPrice(new BigDecimal("10.00"))
                .inboundQuantity(3)
                .retailEnabled(true)
                .minSaleUnit("2粒")
                .minSalePrice(new BigDecimal("0.30"))
                .build();

        DrugStockService.GeneratedResult r = service.generate(dto, "G");
        assertNotNull(r.packRecord());
        assertNotNull(r.retailRecord());
        assertEquals(3, r.packRecord().quantity());
        assertEquals(150, r.retailRecord().quantity());
        assertEquals("G", r.packRecord().groupCode());
        assertEquals("G", r.retailRecord().groupCode());
    }

    @Test
    void batchUniquenessKey() {
        String k1 = service.uniqueKey(" 药品A ", "20 mg×100粒/瓶", "B001");
        String k2 = service.uniqueKey("药品a", "20 mg×100粒/瓶 ", " b001 ");
        assertEquals(k1, k2);
    }
}

