import { describe, it, expect } from 'vitest'
import {
  parseDosageAmount,
  parseFrequencyPerDay,
  calcScatteredQuantity
} from '@/utils/prescription'

// VisitForm.vue 零散用药自动数量计算的核心纯逻辑
describe('prescription utils (VisitForm)', () => {
  it('解析用量：半片=0.5、2片=2、无法解析返回 null', () => {
    expect(parseDosageAmount('半片')).toBe(0.5)
    expect(parseDosageAmount('2片')).toBe(2)
    expect(parseDosageAmount('适量')).toBeNull()
  })

  it('解析频次：每日3次=3、每6小时1次=4、未知默认1', () => {
    expect(parseFrequencyPerDay('每日3次')).toBe(3)
    expect(parseFrequencyPerDay('每6小时1次')).toBe(4)
    expect(parseFrequencyPerDay('必要时')).toBe(1)
  })

  it('计算零散总数量：用量×频次×天数并取整', () => {
    // 2片 × 每日3次 × 2天 = 12
    expect(calcScatteredQuantity('2片', '每日3次', 2)).toBe(12)
    // 半片 × 每日3次 × 1天 = 1.5 -> 四舍五入 2
    expect(calcScatteredQuantity('半片', '每日3次', 1)).toBe(2)
    // 用量无法解析时返回 null（数量保持不变）
    expect(calcScatteredQuantity('--', '每日3次', 2)).toBeNull()
  })
})
