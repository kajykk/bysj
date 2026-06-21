export const MAX_PASSWORD_BYTES = 72

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
    callback(
      new Error(
        `密码不能超过${MAX_PASSWORD_BYTES}字节（当前${byteLen}字节）。中文字符按UTF-8可能占用3字节，请缩短密码。`
      )
    )
  } else {
    callback()
  }
}

export function checkPasswordBytes(value: string): string | null {
  if (!value) return null
  const byteLen = new TextEncoder().encode(value).length
  if (byteLen > MAX_PASSWORD_BYTES) {
    return `密码不能超过${MAX_PASSWORD_BYTES}字节（当前${byteLen}字节）。中文字符按UTF-8可能占用3字节，请缩短密码。`
  }
  return null
}
