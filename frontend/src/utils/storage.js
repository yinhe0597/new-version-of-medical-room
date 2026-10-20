export function safeJsonParse(value, fallback = null) {
  if (!value) return fallback
  try {
    const parsed = JSON.parse(value)
    return parsed ?? fallback
  } catch {
    return fallback
  }
}
