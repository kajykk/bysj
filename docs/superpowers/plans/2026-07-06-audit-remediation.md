# Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-executing-plans (recommended) or superpowers-using-superpowers to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清除本轮深度审核发现的质量门禁阻塞项，并补齐可重复执行的验证路径，使项目重新达到可构建、可测试、可验收状态。

**Architecture:** 先修复前端类型与 lint 阻塞，再隔离处理后端格式化噪音，最后补跑测试与构建门禁。修复保持最小化，不重构业务模块，不引入新依赖，避免把格式化改动与功能修复混在同一提交中。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest、Playwright、ESLint、Element Plus、FastAPI、Python 3.11、pytest、ruff、black。

## Global Constraints

- 明确忽略所有状态文档与 Ralph 文档：不要读取、编辑、引用 `docs/planning/**/AUDIT_STATE.md`、`docs/planning/**/REMEDIATION_STATE.md`、`**/04-ralph-tasks.md`、`.trae/rules/Ralph.md` 或任何 `*ralph*` 文档。
- 不修改本计划文件本身。
- 不做业务重构；每个任务只解决本轮审核列出的具体阻塞项。
- 不新增依赖，除非某任务执行时发现现有依赖确实缺失且用户确认。
- 不提交用户未要求提交的 git commit；下面的 commit 步骤仅作为执行者在获得提交授权后的建议边界。
- 后端 `black` 格式化必须单独成批，不能与前端修复或业务逻辑变更混合。
- 若遇到未预期的大量文件变更或外部改动，立即停止并询问用户。

---

## File Structure

- Modify: `frontend/src/api/request.ts`
  - 负责 Axios 实例、认证刷新、GET 去重和便捷方法包装；修复 `InternalAxiosRequestConfig` 类型不兼容。
- Modify: `frontend/src/i18n/index.ts`
  - 负责导出全局 i18n 实例；如现有导出类型过窄，在这里提供统一的翻译函数适配器。
- Modify: `frontend/src/stores/loading.ts`
  - 负责 loading 文案；修复 `i18n.global.t` 泛型不兼容与可能未定义调用。
- Modify: `frontend/src/utils/errorPolicy.ts`
  - 负责 HTTP/业务错误文案策略；改用统一翻译函数。
- Modify: `frontend/src/utils/passwordValidation.ts`
  - 负责密码规则校验文案；改用统一翻译函数。
- Modify: `frontend/src/utils/riskFormatters.ts`
  - 负责风险文案格式化；改用统一翻译函数。
- Modify: `frontend/e2e/role-admin.spec.ts`
  - 删除未使用的 `expectTableVisible` 导入，或恢复实际断言。
- Modify: `frontend/e2e/role-counselor.spec.ts`
  - 删除未使用的 `expectTableVisible` 导入，或恢复实际断言。
- Modify: `frontend/e2e/role-user.spec.ts`
  - 删除未使用的 `expectTableVisible` 导入，或恢复实际断言。
- Modify: `frontend/e2e/seed.spec.ts`
  - 修复空对象解构 lint 错误。
- Modify: `frontend/playwright.config.ts`
  - 删除未使用的 `backendDir` 变量。
- Modify: `frontend/src/views/user/UserContentPage.vue`
  - 复核 `v-html` 内容来源；如果已净化，增加局部 ESLint 安全说明；如果未净化，使用已有 DOMPurify 净化。
- Format: `backend/app/**/*.py`、`backend/tests/**/*.py`
  - 仅由 `black app tests` 修改，单独作为格式化任务。

---

### Task 1: 修复 Axios GET 去重包装的 TypeScript 类型错误

**Files:**
- Modify: `frontend/src/api/request.ts:300`
- Test: `frontend/src/api/request.ts`

**Interfaces:**
- Consumes: 现有 `DedupeableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean; bypassDedupe?: boolean }`
- Produces: `request.get/delete/head/options(url, config?)` 继续可用，并通过 `npm run typecheck`

- [ ] **Step 1: 定位当前错误代码**

打开 `frontend/src/api/request.ts`，确认当前便捷方法包装类似如下：

```ts
const DEDUPE_METHODS = ['get', 'delete', 'head', 'options'] as const
for (const method of DEDUPE_METHODS) {
  (request as unknown as Record<string, (url: string, config?: InternalAxiosRequestConfig) => Promise<unknown>>)[method] = function (url: string, config?: InternalAxiosRequestConfig) {
    return (request as unknown as { request: (config: DedupeableRequestConfig) => Promise<unknown> }).request({ ...(config || {}), method, url })
  }
}
```

- [ ] **Step 2: 改成兼容 AxiosRequestConfig 的外部包装类型**

在 import 行把 `AxiosRequestConfig` 加入类型导入：

```ts
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
```

将便捷方法包装替换为：

```ts
const DEDUPE_METHODS = ['get', 'delete', 'head', 'options'] as const
type DedupeMethod = (typeof DEDUPE_METHODS)[number]
type DedupeShortcutConfig = AxiosRequestConfig & {
  _retry?: boolean
  bypassDedupe?: boolean
}

for (const method of DEDUPE_METHODS) {
  ;(request as unknown as Record<DedupeMethod, (url: string, config?: DedupeShortcutConfig) => Promise<unknown>>)[method] = function (
    url: string,
    config?: DedupeShortcutConfig,
  ) {
    return request.request({ ...(config || {}), method, url })
  }
}
```

- [ ] **Step 3: 运行类型检查确认该错误消失**

Run: `npm run typecheck`

Expected: 不再出现 `src/api/request.ts(312,111): error TS2345`。如果仍有 i18n 类型错误，留给 Task 2。

- [ ] **Step 4: Commit（仅在用户授权提交时执行）**

```bash
git add frontend/src/api/request.ts
git commit -m "fix: align axios dedupe shortcut types"
```

---

### Task 2: 统一 i18n 翻译函数类型，修复工具层 typecheck 错误

**Files:**
- Modify: `frontend/src/i18n/index.ts`
- Modify: `frontend/src/stores/loading.ts`
- Modify: `frontend/src/utils/errorPolicy.ts`
- Modify: `frontend/src/utils/passwordValidation.ts`
- Modify: `frontend/src/utils/riskFormatters.ts`
- Test: `frontend/src/stores/loading.ts`
- Test: `frontend/src/utils/errorPolicy.ts`
- Test: `frontend/src/utils/passwordValidation.ts`
- Test: `frontend/src/utils/riskFormatters.ts`

**Interfaces:**
- Consumes: 现有默认导出的 `i18n` 实例
- Produces: `translate(key: string, named?: Record<string, unknown>): string`，供非组件 TypeScript 模块安全调用

- [ ] **Step 1: 在 i18n 入口新增稳定翻译适配器**

打开 `frontend/src/i18n/index.ts`。保留现有 `i18n` 创建逻辑，在默认导出之前或之后新增：

```ts
export function translate(key: string, named?: Record<string, unknown>): string {
  const t = i18n.global.t as unknown as (key: string, named?: Record<string, unknown>) => string
  return named ? t(key, named) : t(key)
}
```

如果文件中默认导出是 `export default i18n`，保留它。

- [ ] **Step 2: 修改 `frontend/src/stores/loading.ts`**

把直接绑定 `i18n.global.t` 的代码：

```ts
import i18n from '@/i18n'

const t = i18n.global.t.bind(i18n.global)
```

替换为：

```ts
import { translate } from '@/i18n'

const t = translate
```

如果文件中存在 `t?.(...)` 或可能未定义调用，改为直接调用：

```ts
t('common.loading')
```

- [ ] **Step 3: 修改 `frontend/src/utils/errorPolicy.ts`**

把直接绑定 `i18n.global.t` 的代码替换为统一适配器：

```ts
import { translate } from '@/i18n'

const t = translate
```

保留原有 key，不改业务文案。

- [ ] **Step 4: 修改 `frontend/src/utils/passwordValidation.ts`**

把直接绑定 `i18n.global.t` 的代码替换为：

```ts
import { translate } from '@/i18n'

const t = translate
```

保留原有密码规则和返回结构。

- [ ] **Step 5: 修改 `frontend/src/utils/riskFormatters.ts`**

把直接绑定 `i18n.global.t` 的代码替换为：

```ts
import { translate } from '@/i18n'

const t = translate
```

保留风险等级、颜色和展示逻辑。

- [ ] **Step 6: 运行类型检查**

Run: `npm run typecheck`

Expected: 不再出现以下错误：

```text
src/stores/loading.ts(7,9): error TS2322
src/stores/loading.ts(9,12): error TS2722
src/utils/errorPolicy.ts(15,9): error TS2322
src/utils/passwordValidation.ts(7,9): error TS2322
src/utils/riskFormatters.ts(19,9): error TS2322
```

- [ ] **Step 7: Commit（仅在用户授权提交时执行）**

```bash
git add frontend/src/i18n/index.ts frontend/src/stores/loading.ts frontend/src/utils/errorPolicy.ts frontend/src/utils/passwordValidation.ts frontend/src/utils/riskFormatters.ts
git commit -m "fix: stabilize i18n translation typing"
```

---

### Task 3: 清理 E2E 与 Playwright 配置 lint 错误

**Files:**
- Modify: `frontend/e2e/role-admin.spec.ts:8`
- Modify: `frontend/e2e/role-counselor.spec.ts:8`
- Modify: `frontend/e2e/role-user.spec.ts:8`
- Modify: `frontend/e2e/seed.spec.ts:22`
- Modify: `frontend/playwright.config.ts:10`
- Test: `frontend/e2e/*.spec.ts`

**Interfaces:**
- Consumes: 现有 Playwright spec 与 helper 导入
- Produces: `npm run lint` 不再报告 unused vars / no-empty-pattern

- [ ] **Step 1: 删除三个角色测试中的未使用导入**

在以下文件中删除未使用的 `expectTableVisible` 导入项：

```text
frontend/e2e/role-admin.spec.ts
frontend/e2e/role-counselor.spec.ts
frontend/e2e/role-user.spec.ts
```

如果当前导入为：

```ts
import { expectTableVisible, loginAsRole } from './helpers'
```

改为：

```ts
import { loginAsRole } from './helpers'
```

如果当前导入包含更多符号，仅删除 `expectTableVisible`，保留其他已使用符号。

- [ ] **Step 2: 修复 `seed.spec.ts` 空对象解构**

打开 `frontend/e2e/seed.spec.ts`，找到第 22 行附近的空对象解构。如果代码类似：

```ts
test('seed data is available', async ({}) => {
```

改为：

```ts
test('seed data is available', async () => {
```

如果是 helper 回调参数中的 `({})`，同样改成无参数 `()`。

- [ ] **Step 3: 删除 Playwright 未使用变量**

打开 `frontend/playwright.config.ts`，删除：

```ts
const backendDir = path.join(rootDir, 'backend')
```

如果删除后 `rootDir` 也未使用，再删除：

```ts
const rootDir = path.resolve(currentDir, '..')
```

如果删除 `rootDir` 后 `path.resolve` 仍在其他位置使用，保留 `path` import；否则不动 import，因为 `path.dirname` 和 `path.join` 仍可能使用。

- [ ] **Step 4: 运行 lint 验证**

Run: `npm run lint`

Expected: 不再出现：

```text
expectTableVisible is defined but never used
Unexpected empty object pattern
backendDir is assigned a value but never used
```

- [ ] **Step 5: Commit（仅在用户授权提交时执行）**

```bash
git add frontend/e2e/role-admin.spec.ts frontend/e2e/role-counselor.spec.ts frontend/e2e/role-user.spec.ts frontend/e2e/seed.spec.ts frontend/playwright.config.ts
git commit -m "fix: clean playwright lint violations"
```

---

### Task 4: 复核并收敛 `UserContentPage.vue` 的 `v-html` 风险

**Files:**
- Modify: `frontend/src/views/user/UserContentPage.vue:318`
- Test: `frontend/src/views/user/UserContentPage.vue`

**Interfaces:**
- Consumes: 页面中当前用于 `v-html` 的字段或 computed 值
- Produces: 页面仍能展示富文本内容，且 lint 中 `vue/no-v-html` 有明确安全处理或局部豁免说明

- [ ] **Step 1: 定位 `v-html` 表达式**

打开 `frontend/src/views/user/UserContentPage.vue`，找到第 318 行附近，例如：

```vue
<div class="content-body" v-html="content.html"></div>
```

记录实际表达式名称，例如 `content.html`、`article.content` 或 `renderedContent`。

- [ ] **Step 2: 如果表达式未净化，使用 DOMPurify 净化**

在 `<script setup lang="ts">` 中添加导入：

```ts
import DOMPurify from 'dompurify'
```

新增 computed，名称按实际字段调整。假设原字段是 `selectedContent?.body`：

```ts
const safeContentHtml = computed(() => {
  return DOMPurify.sanitize(selectedContent.value?.body || '', {
    USE_PROFILES: { html: true },
  })
})
```

模板改为：

```vue
<!-- eslint-disable-next-line vue/no-v-html -- 内容已通过 DOMPurify 净化，允许展示受控富文本 -->
<div class="content-body" v-html="safeContentHtml"></div>
```

- [ ] **Step 3: 如果表达式已在上游净化，仅添加局部说明**

如果代码已经存在 `DOMPurify.sanitize(...)`，不要重复净化。只在 `v-html` 前一行添加：

```vue
<!-- eslint-disable-next-line vue/no-v-html -- 内容已通过 DOMPurify 净化，允许展示受控富文本 -->
```

- [ ] **Step 4: 运行 lint 验证 warning 消失**

Run: `npm run lint`

Expected: 不再出现：

```text
frontend/src/views/user/UserContentPage.vue
warning  'v-html' directive can lead to XSS attack  vue/no-v-html
```

- [ ] **Step 5: Commit（仅在用户授权提交时执行）**

```bash
git add frontend/src/views/user/UserContentPage.vue
git commit -m "fix: sanitize user content rich text rendering"
```

---

### Task 5: 单独格式化后端 Python 代码

**Files:**
- Format: `backend/app/**/*.py`
- Format: `backend/tests/**/*.py`
- Test: `backend/app/**/*.py`
- Test: `backend/tests/**/*.py`

**Interfaces:**
- Consumes: 当前 Python 代码
- Produces: `black --check app tests` 通过；不改变业务逻辑

- [ ] **Step 1: 确认当前格式化失败基线**

Run: `black --check app tests`

Expected: 输出类似：

```text
would reformat ...
Oh no! 💥 💔 💥
371 files would be reformatted
```

- [ ] **Step 2: 执行 black 格式化**

Run: `black app tests`

Expected: 输出被格式化文件列表，命令 exit code 为 0。

- [ ] **Step 3: 验证 black 门禁**

Run: `black --check app tests`

Expected:

```text
All done! ✨ 🍰 ✨
... files would be left unchanged.
```

- [ ] **Step 4: 验证 ruff 未因格式化产生新问题**

Run: `ruff check app tests`

Expected:

```text
All checks passed!
```

- [ ] **Step 5: Commit（仅在用户授权提交时执行）**

```bash
git add backend/app backend/tests
git commit -m "style: format backend python code"
```

---

### Task 6: 重新运行质量门禁与核心测试

**Files:**
- No source changes expected
- Test: `frontend/package.json`
- Test: `backend/pyproject.toml`
- Test: `backend/pytest.ini`

**Interfaces:**
- Consumes: Task 1-5 的修复结果
- Produces: 可复现的质量门禁结果，用于决定是否进入功能 E2E 验证

- [ ] **Step 1: 前端类型检查**

Run: `npm run typecheck`

Working directory: `frontend`

Expected: exit code 0，无 TypeScript error。

- [ ] **Step 2: 前端 lint**

Run: `npm run lint`

Working directory: `frontend`

Expected: exit code 0，无 error；warning 也应为 0，除非有明确局部豁免。

- [ ] **Step 3: 前端单元测试**

Run: `npm run test`

Working directory: `frontend`

Expected: Vitest exit code 0。

- [ ] **Step 4: 前端构建**

Run: `npm run build`

Working directory: `frontend`

Expected: Vite build exit code 0，并输出 `dist/` 构建产物。

- [ ] **Step 5: 后端 ruff**

Run: `ruff check app tests`

Working directory: `backend`

Expected: `All checks passed!`

- [ ] **Step 6: 后端 black check**

Run: `black --check app tests`

Working directory: `backend`

Expected: `would be left unchanged`。

- [ ] **Step 7: 后端测试**

Run: `pytest`

Working directory: `backend`

Expected: pytest exit code 0。若超过 30s，应继续等待到结束，不要仅凭超时判断失败。

- [ ] **Step 8: Commit（仅在用户授权提交时执行且前序修复尚未提交时）**

```bash
git status --short
git add frontend backend
git commit -m "fix: restore audit quality gates"
```

---

### Task 7: 补跑角色级功能验证与性能基线

**Files:**
- No source changes expected unless tests expose real bugs
- Test: `frontend/playwright.config.ts`
- Test: `frontend/e2e/*.spec.ts`
- Test: `frontend/vite.config.ts`

**Interfaces:**
- Consumes: Task 6 通过后的可运行前后端环境
- Produces: 角色链路验证结论与前端性能优化基线

- [ ] **Step 1: 启动或复用后端服务**

Run backend server with the repository’s existing command. If the project convention is uvicorn, use:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Working directory: `backend`

Expected: `/health` 返回 `status` 为 `ok` 或 `degraded`，但服务可响应。

- [ ] **Step 2: 运行 Playwright smoke 测试**

Run: `npm run test:e2e -- --project=chromium-smoke`

Working directory: `frontend`

Expected: smoke 测试 exit code 0。

- [ ] **Step 3: 运行角色回归测试**

Run: `npm run test:e2e -- --project=chromium-regression`

Working directory: `frontend`

Expected: 普通用户、咨询师、管理员关键页面通过。

- [ ] **Step 4: 构建性能基线**

Run: `npm run build`

Working directory: `frontend`

Expected: 记录各 chunk 体积，特别关注 `vendor`、`element-plus`、`ep-table`、`charts`。

- [ ] **Step 5: 如本地可访问浏览器，运行 Lighthouse CI**

Run: `npm run lighthouse:ci`

Working directory: `frontend`

Expected: 生成 `frontend/lighthouse-report.json`。若因 Chrome/环境限制失败，记录失败原因，不修改业务代码。

- [ ] **Step 6: 形成验证结论**

在最终回复中报告：

```text
前端 typecheck: PASS/FAIL
前端 lint: PASS/FAIL
前端 test: PASS/FAIL
前端 build: PASS/FAIL
后端 ruff: PASS/FAIL
后端 black: PASS/FAIL
后端 pytest: PASS/FAIL
E2E smoke: PASS/FAIL/SKIPPED + reason
E2E regression: PASS/FAIL/SKIPPED + reason
Lighthouse: PASS/FAIL/SKIPPED + reason
```

---

## Self-Review

- Spec coverage: 覆盖审核中发现的全部阻塞项：前端 `request.ts` 类型错误、i18n 类型错误、E2E lint、Playwright 配置 lint、`v-html` warning、后端 black 格式漂移、质量门禁与功能验证。
- Placeholder scan: 本计划没有使用 TBD/TODO/implement later，也没有“写适当测试”之类无操作细节的步骤。
- Type consistency: `translate(key: string, named?: Record<string, unknown>): string` 在 Task 2 中定义，并被所有工具层文件以同一签名消费；`DedupeShortcutConfig` 只在 Task 1 内消费。
