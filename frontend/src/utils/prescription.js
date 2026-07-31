// 处方相关纯函数（从 doctor/VisitForm.vue 提取，行为保持一致）

/**
 * 解析用量文本，返回单次用量数值。
 * 如 '半片' -> 0.5，'2片' -> 2；无法解析返回 null。
 */
export function parseDosageAmount(dosage) {
  const text = String(dosage || '')
  if (text.includes('半')) return 0.5
  const dosageMatch = text.match(/(\d+)([片粒袋包支瓶贴喷丸次滴])/)
  if (!dosageMatch) return null
  const dosageAmount = parseFloat(dosageMatch[1])
  if (!dosageAmount) return null
  return dosageAmount
}

/**
 * 解析频次文本，返回每日次数，默认 1。
 * 如 '每日3次' -> 3，'每6小时1次' -> 4。
 */
export function parseFrequencyPerDay(frequency) {
  const text = String(frequency || '')
  const frequencyMatch = text.match(/每日(\d+)次/)
  if (frequencyMatch) return parseFloat(frequencyMatch[1])
  if (text.includes('每4小时')) return 6
  if (text.includes('每6小时')) return 4
  if (text.includes('每8小时')) return 3
  if (text.includes('每12小时')) return 2
  return 1
}

/**
 * 计算零散用药总数量 = 单次用量 × 每日次数 × 天数（四舍五入取整）。
 * 用量无法解析时返回 null（调用方保持原数量不变）。
 */
export function calcScatteredQuantity(dosage, frequency, days) {
  const dosageAmount = parseDosageAmount(dosage)
  if (dosageAmount == null) return null
  const frequencyAmount = parseFrequencyPerDay(frequency)
  return Math.round(dosageAmount * frequencyAmount * (days || 1))
}
