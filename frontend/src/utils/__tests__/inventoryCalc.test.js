import { describe, it, expect } from 'vitest'
import {
  calcGroupRetailLimit,
  calcGroupTotalUnits,
  splitGroupStock
} from '@/utils/inventoryCalc'

// Inventory.vue 联合盘点（整件/零售）核心纯逻辑
describe('inventoryCalc utils (Inventory)', () => {
  it('零售份数上限：整件100/零售10 -> 9；缺参数 -> 0', () => {
    expect(calcGroupRetailLimit(100, 10)).toBe(9)
    expect(calcGroupRetailLimit(0, 10)).toBe(0)
    expect(calcGroupRetailLimit(100, 0)).toBe(0)
  })

  it('盘点后总计 = 整件数×整件量 + 零售份数×零售量', () => {
    expect(calcGroupTotalUnits(3, 2, 100, 10)).toBe(320)
    expect(calcGroupTotalUnits(0, 0, 100, 10)).toBe(0)
  })

  it('总量拆分为整件与零售份数（含无零售量场景）', () => {
    expect(splitGroupStock(320, 100, 10)).toEqual({ packs: 3, retailUnits: 2 })
    expect(splitGroupStock(320, 100, 0)).toEqual({ packs: 3, retailUnits: 0 })
  })
})
