// 库存联合盘点纯函数（从 nurse/Inventory.vue 提取，行为保持一致）

/**
 * 零售份数上限：整件可拆出的零售份数减 1；无整件量或零售量时为 0。
 */
export function calcGroupRetailLimit(packAmount, retailAmount) {
  const pack = Number(packAmount || 0)
  const retail = Number(retailAmount || 0)
  if (!pack || !retail) return 0
  return Math.max(0, Math.floor(pack / retail) - 1)
}

/**
 * 盘点后总计（最小单位）= 整件数 × 整件量 + 零售份数 × 零售量。
 */
export function calcGroupTotalUnits(actualPacks, actualRetailUnits, packAmount, retailAmount) {
  const pack = Number(packAmount || 0)
  const retail = Number(retailAmount || 0)
  return actualPacks * pack + actualRetailUnits * retail
}

/**
 * 将总最小单位数拆分为整件数与零售份数（用于盘点弹窗初始值）。
 */
export function splitGroupStock(totalUnits, packAmount, retailAmount) {
  const total = Number(totalUnits || 0)
  const pack = Number(packAmount || 1)
  const retail = Number(retailAmount || 0)
  const remainder = total % pack
  return {
    packs: Math.floor(total / pack),
    retailUnits: retail ? Math.floor(remainder / retail) : 0
  }
}
