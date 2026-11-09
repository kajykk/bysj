# 密钥扫描 allowlist 核定记录（2026-11-09）

本文件是 `.gitleaks.toml` 的判定依据。目的不是「让扫描变绿」，而是把每一条
已核定的误报写清楚、把放行范围压到最小，并留下将来复核的入口。

## 一、背景与实测口径

推送 `e09b5a2` 后，CI 的 `Secret Scan (gitleaks)` 三个 job 全红：
`dir` 工作区扫描 46 条、增量与全历史 git 扫描各 4 条。

本地复现方式（不依赖 CI）：

1. 从 GitHub release 取 `gitleaks 8.30.1` Windows 二进制；
2. `git archive HEAD | tar -x -C <干净目录>` 造一份与 CI checkout 一致的
   **无未跟踪文件**树（2489 个文件，约 27.17 MB），避免本机 `docs/onboarding/`
   等未跟踪内容污染读数；
3. `gitleaks dir <干净树> --redact --no-banner --exit-code 0 --report-format json`。

**基线实测 46 条，与 CI 逐文件吻合**：

| 文件 | 条数 | 规则 | 形态与判定 |
|---|---|---|---|
| `backend/tests/api/test_auth_flow.py` | 22 | generic-api-key | 注册/登录/改密载荷里的固定假密码 |
| `backend/tests/api/test_p0_p1_regressions.py` | 5 | generic-api-key | 同上 |
| `.github/workflows/v1.39-alerting-e2e.yml` | 4 | generic-api-key ×2 / curl-auth-user ×2 | CI 占位 env 与 `curl -u admin:<CI 口令>` |
| `backend/tests/api/test_auth_p0p1.py` | 3 | generic-api-key | 固定假密码 |
| `docs/archive/2026-09/planning/v1.40-audit-beautify/_baseline_ruff.txt` | 3 | generic-api-key | 归档 ruff F841 告警**引用的源码行**，同一批假密码 |
| `backend/tests/api/test_round35_rbac_real_object_e2e.py` | 2 | generic-api-key | 固定假密码 |
| `backend/tests/test_pii_crypto_helpers.py` | 2 | generic-api-key | monkeypatch 用的合成 Fernet 形值（可读前缀 + 顺序数字） |
| `backend/tests/test_sec_p2_007_log_sanitizer.py` | 2 | jwt / generic-api-key | 脱敏器输入样例：jwt.io 示例 JWT、假 `sk-` token |
| `backend/scripts/modeling/eval/v1_50/protocol_robustness.json` | 1 | generic-api-key | `"round48_key": "sensitivity_*"` 用例标识符 |
| `backend/scripts/modeling/eval/v1_50/01_protocol_robustness.py` | 1 | generic-api-key | 同上（Python 锚点字典） |
| `backend/tests/test_sec_p2_004_aes_gcm.py` | 1 | generic-api-key | 测试模块导入前设置的占位环境变量 |

git 模式另测：以「只有 `[extend] useDefault = true`、无 allowlist」的配置扫最近
20 个提交，得 **4 条**，fingerprint 落在 `e09b5a2` 的
`test_round35_rbac_real_object_e2e.py:65/72` 与 `84b7b109` 的
`test_auth_flow.py:137/143`，与 CI 日志逐条吻合。也就是说增量 4 条与全历史 4 条
是同一批测试夹具假密码，不是两类问题。

## 二、判定：全部为固定假值，不构成凭据泄漏

- 测试文件里的密码是同一批固定字符串（日志显示熵恒为 3.546594），用于构造
  HTTP 请求体；`invalid.token.here`、jwt.io 示例 JWT、假 `sk-`/`ghp_` token 是
  日志脱敏器**故意放置**的输入样例。
- 评测基线里的 `round48_key` 是敏感度分析用例名，不是 key-value 凭据。
- `.env.example` 明确禁止写入真实值，真实密钥由 `ENV_FILE` 从仓库外注入
  （见 `docs/ops/SECRET_ROTATION_2026-11.md`）。
- workflow 里同块 env 还包含 `ci-` 前缀占位、`example.invalid` 域名和
  `hooks.slack.com/services/CI/CI/CI`，整体是 CI 专用构造。

**唯一需要单独标记的一条**：`.github/workflows/v1.39-alerting-e2e.yml` 的
`PII_ENCRYPTION_KEY` 行，值形态是 44 字符 Fernet 形串，与真实生产密钥格式一致。
判定它为 CI 占位的证据链有三条：(a) 它位于 workflow 的 env 块，注释写明是为
「生产模式 Settings 硬性要求 >=32 字节」而写的固定值；(b)
`tests/test_ci_secret_placeholders.py` 用真实强度校验函数反向钉住 workflow 占位值，
说明这类高强度占位是被闸门逼出来的；(c) 真实密钥按轮换文档放在仓库外。
处置上仍按最窄粒度放行：只按「单个文件 + 行内变量名 + 单条 generic-api-key 规则」
命中，不写具体值、不整文件放行。**若该值曾在任何非 CI 环境使用过，应按
`docs/ops/SECRET_ROTATION_2026-11.md` 轮换，并回来复核本条是否保留。**

## 三、放行范围与不变式

`.gitleaks.toml` 每条 `[[allowlists]]` 都同时限定
`targetRules` + `paths`（精确文件）+ `regexes`（`regexTarget = "line"`）+
`condition = "AND"`，没有整目录放行、没有关闭任何规则。新增同类字面量一旦换文件
或换键名就不会命中，扫描照红，必须回来逐条复核。

配套改动：`.github/workflows/secret-scan.yml` 三个 job 统一到 **8.30.1**
（两个 action job 用 `GITLEAKS_VERSION` + `GITLEAKS_CONFIG`，dir job 钉镜像 tag
并显式 `--config`）。理由是实测反例：

| 场景 | 版本 | 结果 |
|---|---|---|
| dir，无 allowlist | 8.30.1 | 46 leaks（基线） |
| dir，`--config .gitleaks.toml` | 8.30.1 | **0 leaks** |
| dir，不带 `--config`（自动发现） | 8.30.1 | **0 leaks** |
| git，无 allowlist（`-n 20`） | 8.30.1 | 4 leaks |
| git，带 allowlist（`-n 20`） | 8.30.1 | **0 leaks** |
| dir，`--config .gitleaks.toml` | **8.24.3** | **47 leaks（allowlist 静默失效，且多 1 条自命中）** |

`gitleaks-action@e0c47f4` 的 `src/index.js:138` 默认版本是 8.24.3，不认识
`[[allowlists]]` / `targetRules`（8.25.0 起支持）；若不钉版本，action 两个 job
会带着「看似配置好了」的假象继续红。这是本次必须改 workflow 的唯一原因。

## 四、未验证记账

1. CI 上三个 job 的实际运行结果需下一次 push 后复核；本文所有读数均为本地
   8.30.1 实测，不是远端结论。
2. `gitleaks-action` 是否真的把 `GITLEAKS_CONFIG` 透传给 CLI 未单独实测；
   但同一配置在 8.30.1 下经 target path 自动发现已实测生效，二者构成双保险。
3. git 模式只复现了最近 20 个提交（与 CI 日志 "20 commits scanned" 一致），
   未跑全仓库历史；若全历史另有存量检出，需按同样纪律逐条核定后再追加。
4. 本轮未处理 `dir` 之外的任何扫描器（Dependabot / pip-audit / Trivy），
   推送时 GitHub 提示的 21 个依赖漏洞仍在。
