/**
 * @deprecated This file is deprecated in v1.11 and replaced with an empty stub.
 *
 * 安全修复：原实现包含完整的 fetch 事件监听器，会将 /api/ 路径下的所有 GET 响应
 * （含用户风险报告、预警列表、咨询记录等敏感医疗数据）缓存到 Cache Storage。
 * 即使文件被标记为弃用，若被意外重新启用或被构建工具包含，敏感数据将在用户
 * 登出后仍残留在浏览器中，无法通过 clearStoredAuth 清理。
 *
 * 现已移除所有缓存逻辑，仅保留弃用声明。
 *
 * 项目现在使用 `vite-plugin-pwa` 的 `generateSW` 策略自动生成 service worker。
 * 注册逻辑在 `src/utils/serviceWorker.ts` 中使用 `virtual:pwa-register/vue`。
 */

// 空实现：不注册任何 fetch/install/activate 事件监听器
export {}
