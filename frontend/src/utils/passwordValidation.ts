import { translate } from '@/i18n'

export const MAX_PASSWORD_BYTES = 72

const t = translate

function tooLongMessage(current: number): string {
  return t('passwordValidation.tooLong', { max: MAX_PASSWORD_BYTES, current })
}

export function validatePasswordBytes(
  _rule: unknown,
  value: string,
  callback: (error?: Error) => void
): void {
  if (!value) {
    callback()
    return
  }
  const byteLen = new TextEncoder().encode(value).length
  if (byteLen > MAX_PASSWORD_BYTES) {
    callback(new Error(tooLongMessage(byteLen)))
  } else {
    callback()
  }
}

export function checkPasswordBytes(value: string): string | null {
  if (!value) return null
  const byteLen = new TextEncoder().encode(value).length
  if (byteLen > MAX_PASSWORD_BYTES) {
    return tooLongMessage(byteLen)
  }
  return null
}
