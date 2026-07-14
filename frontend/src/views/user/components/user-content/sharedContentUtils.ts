/**
 * UserContent 共享工具：DOMPurify 配置、内容类型标签映射。
 * 从原 UserContentPage.vue 提取，保持行为一致。
 */

// ISSUE-008 修复：显式白名单策略，避免默认配置过宽
// 心理健康内容系统仅需基础富文本标签，禁用 script/iframe/form 等危险标签
export const DOMPURIFY_CONFIG = {
  ALLOWED_TAGS: [
    'p', 'br', 'strong', 'em', 'u', 's', 'sub', 'sup',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'a', 'img', 'hr',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span',
  ],
  ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'target', 'rel', 'width', 'height'],
  ALLOW_DATA_ATTR: false,
  FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'style', 'link', 'meta'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onsubmit', 'style', 'srcset'],
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
} as Record<string, unknown>

/** 内容类型 → i18n key 后缀映射 */
export const CONTENT_TYPE_LABEL_KEYS: Record<string, string> = {
  article: 'typeArticle',
  audio: 'typeAudio',
  video: 'typeVideo',
}
