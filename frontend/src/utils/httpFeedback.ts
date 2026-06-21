import { ElMessage } from 'element-plus'
import { normalizeHttpError } from '@/utils/errorPolicy'

export const showHttpFeedback = (error: unknown, fallback: string) => {
  const normalized = normalizeHttpError(error, fallback)
  if (normalized.status === 401) {
    return normalized
  }
  if (normalized.status === 403) {
    ElMessage.warning(normalized.detail)
    return normalized
  }
  if (normalized.level === 'warning') {
    ElMessage.warning(normalized.detail)
    return normalized
  }
  ElMessage.error(normalized.detail)
  return normalized
}
