import { ENABLE_MOCK_FALLBACK } from '@/config/feature'

export async function withMockFallback<T>(
  realCall: () => Promise<T>,
  mockCall: () => Promise<T>
): Promise<T> {
  try {
    return await realCall()
  } catch (error) {
    if (ENABLE_MOCK_FALLBACK) {
      return await mockCall()
    }
    throw error
  }
}
