import { describe, expect, it } from 'vitest'
import { safeJsonParse } from '@/utils/storage'

describe('storage utils', () => {
  it('parses valid JSON and preserves falsy parsed values', () => {
    expect(safeJsonParse('{"role":"doctor"}', {})).toEqual({ role: 'doctor' })
    expect(safeJsonParse('0', {})).toBe(0)
    expect(safeJsonParse('false', {})).toBe(false)
  })

  it('returns fallback for empty or malformed values', () => {
    expect(safeJsonParse(null, {})).toEqual({})
    expect(safeJsonParse('', {})).toEqual({})
    expect(safeJsonParse('{broken', {})).toEqual({})
    expect(safeJsonParse('null', {})).toEqual({})
  })
})
