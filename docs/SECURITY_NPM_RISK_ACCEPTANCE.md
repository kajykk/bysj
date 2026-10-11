# SEC-N: npm 前端依赖漏洞风险接受记录

本文件是 npm 生态（`frontend/package-lock.json`）的风险接受台账，与后端
`backend/.trivyignore` 同一纪律：**每条必须写清「现象 → 根因 → 处置 → 复审期限」，
不接受「暂时没空修」这类无期限条目。**

## 为什么需要单独一份文件

trivy 的忽略清单是**文件式**的（`.trivyignore`），可提交、可 review、可 diff。
而 **Dependabot 没有文件式忽略清单** —— 只能在 GitHub 上一条条 dismiss，
且需要 `security_events` / `admin:repo_hook` 权限。这导致：

- dismiss 状态**不进git 历史**，review 不了、改不了、传不下去
- 同一条告警在依赖升级后会复活，无人知道当初为何接受

因此本文件是 GitHub 上那些 dismiss 动作的**可审计镜像**。

**纪律**：本文件每条风险接受，必须与 GitHub 上对应的 dismiss 动作**成对存在**。
若发现本文件有条目而 GitHub 上告警仍open，说明 dismiss 动作丢失，需重做。

---

## R-N-001: extract-zip 2.0.1 —— symlink 逃逸导致任意文件写（2 条 high）

| 字段 | 内容 |
|---|---|
| **告警** | GHSA-7pqw-9j4j-h8q3 (CVE-2026-19693, high)<br>GHSA-jmr9-qjv8-65gv (CVE-2026-56876, high) |
| **包** | `extract-zip@2.0.1` |
| **依赖 scope** | `development` |
| **引入者** | `@puppeteer/browsers@2.13.2`（`puppeteer@^24.43.1` 的传递依赖） |
| **上游状态** | **无补丁**。`npm view extract-zip versions` 实测最新即 `2.0.1`，<br>vulnerable range `<= 2.0.1`，**不存在 2.0.2+** |
| **复审期限** | **2026-11-12**（见下方「解除条件」） |

### 现象

两条 high 指向同一类缺陷：`extract-zip` 解压 zip 时不校验 symlink 目标。

- CVE-2026-19693：containment 检查只看父目录、从不检查条目自身最终路径分量。
  含「同名 symlink（指向目的地外）+ 同名普通文件」的归档会穿透已植入的
  symlink，实现往destination 目录外的**任意文件写**。
- CVE-2026-56876：不校验 symlink 的相对路径目标（如 `../../../../etc/passwd`），
  会原样抽出该 symlink。

### 可达性取证（实测，非推断）

风险接受的前提是「不可达」。本条**逐层取证**：

1. **本仓库源码零引用** —— `git grep -E "extract-zip|extractZip"` 在**全部
   受版本控制的源码中无匹配**。应用代码从不直接调用它。
2. **唯一调用点** —— `@puppeteer/browsers/lib/cjs/fileUtil.js:61`：

   ```js
   if (archivePath.endsWith('.zip')) {
     const extractZip = await import('extract-zip');      // 动态 import, 惰性
     await extractZip.default(archivePath, { dir: folderPath });
   }
   ```

   注意这是 `await import(...)`，**加载期不加载**。实测
   `require('@puppeteer/browsers')` 的加载图中**未出现** `extract-zip`。

3. **唯一调用者的上游** —— `install.js:233` `unpackArchive(archivePath, outputPath)`，
   而 `archivePath` 来自紧邻上方的 `downloadFile(url, archivePath)`，即
   **从 puppeteer 下载源取回的归档**。

### 风险为何可接受

- 攻击需要**同时**满足：篡改/劫持 puppeteer 浏览器下载源，或向本地缓存目录
  (`~/.cache/puppeteer`) 植入恶意 zip。这已超出「供应链攻击」范畴 ——
  攻击者若能做到这一步，本机已处于失陷状态（可直接改`node_modules`、
  改 `.npmrc` registry、改 postinstall 脚本）。
- 该包为 **development scope，不进生产 bundle**。线上运行时不存在此代码。
- 上游无补丁，**无可执行的修复动作**（override 到不存在的版本只会破坏安装）。

### 缓解措施

- CI 中浏览器安装走 puppeteer 官方 CDN（`npm ci` 的 postinstall），
  无自定义 `PUPPETEER_DOWNLOAD_HOST`
- CI runner 为一次性容器，缓存不可跨构建复用

### 解除条件（任一满足即复审）

- `extract-zip` 发布 2.0.2+ → 立即升版并删除本条目
- `puppeteer` 或 `@puppeteer/browsers` 改用其他解压实现 → 复核后删除本条目
- **2026-11-12** 到期未解除 → 重新评估，不得默认延期

---

## 已处置（不再是风险接受，仅留档）

以下条目曾为 open 告警，已通过升级修复，记录处置路径便于追溯。

| 包 | 旧 → 新 | 告警 | 处置 |
|---|---|---|---|
| `@vue/server-renderer` | 3.5.41 → 3.5.42 | XSS (high) | 提交 `5174b28` |
| `source-map-js` | 1.2.1 → 1.2.2 | DoS | 提交 `5174b28` |
| `undici` / `ip-address` / `js-yaml` / `fast-uri` / `immutable` / `js-cookie` / `browserslist` / `@babel/*` / `baseline-browser-mapping` | 见提交 `4caaf94` | 46 条 | 提交 `4caaf94` |
| `brace-expansion` ×7 副本 | 1.1.14→1.1.21 / 2.0.3→2.1.7 / 5.0.5→5.0.12 | 6 条 | 提交 `c87178c`，`overrides` 按 major 分叉 |
| `ws` ×2 副本 | 7.5.10→7.5.13 / 8.20.0→8.22.0 | 2 条 | 提交 `c87178c`，`overrides` 按 major 分叉 |
| `postcss-selector-parser` | 6.1.2 → 6.1.4 | low | 提交 `6ced5e1` |
| `@opentelemetry/instrumentation-*` ×6 | **包从依赖树移除** | 6 条 (GHSA-qqmp-wf37-98f9) | 提交 `80ed98f`：升 `lighthouse` 13.1.0→13.5.0，<br>其 `@sentry/node` 从 `^9.28.1` 提到 `^10.0.0`（Sentry 10 不再引入 DB 探针） |

### 为什么 `@opentelemetry/instrumentation-*` 选「升上游」而非 dismiss

6 条告警（GHSA-qqmp-wf37-98f9, medium）均为「instrumentation 包在 span 上
**无条件暴露数据库用户名**」。曾考虑按「development scope + 不接数据库」
dismiss，但**实测推翻了该理由**：

hook `Module._load` 实测 `require('@sentry/node')` 会加载 **2852 个模块**
（otel 相关 60 个），6 个目标包**全部被真实加载**。「未被加载故不适用」
这条常见理由在此不成立，不能据此dismiss。

也不能直接 `overrides` 到修复版本：修复版要求
`@opentelemetry/instrumentation ^0.221.0`（现 `^0.57.1`）与
`@opentelemetry/core ^2.9.0`（现 `^1.26.0`），而 `@sentry/node@9.47.x` 把这两个
核心包硬pin 在旧线 —— 直接 override 会造成 otel 核心**双版本分裂**
（0.57.x 与 0.220.x 并存），Sentry 的 instrumentation 注册依赖单一核心实例，
行为不可预测。且 `@sentry/node` 9.47.1 与 9.47.2 的 6 个 pin **完全相同**，
升 patch 无效。

最终走`lighthouse` 同 major 升级（`^13.1.0` → `^13.5.0`），让这 6 个包
**从依赖树彻底消失**而非被强行升版本。附带确认 `puppeteer-core` 仍是 24.43.1
（项目自身 `devDependencies.puppeteer ^24.43.1` 钉住，未隐式跳 24→25）。
