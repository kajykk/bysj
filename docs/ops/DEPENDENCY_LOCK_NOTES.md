# 依赖锁定现状与漂移台账（2026-10-04 复核）

> 复核范围：`backend/requirements*.txt` 与 `backend/requirements*.lock` 的一致性，
> 以及「CI 实际解析到的版本」与「本地实测组合」是否一致（P1-3 计划项）。
> 结论先行：**CI 当前不会因版本漂移失败**（CI 装的是带约束的 `.txt`，不装 `.lock`），
> 但 `.lock` 与 `.txt` 存在 4 处不一致 + 1 处工件版本隐患，属于**复发风险**，需根治。

## 1. 谁在用什么（先搞清才能判断风险）

| 消费者 | 实际安装的文件 | 风险 |
|---|---|---|
| `contract-tests.yml` / `coverage.yml` / `migration-tests.yml` / `test-harness.yml` | `requirements.txt` + `requirements-dev.txt` | 按 `.txt` 的 range 解析 → **lock 的钉版本与之无关** |
| `e2e-tests.yml` / `migration-tests.yml` / `pr-quality-gates.yml` | 仅 `requirements.txt` | 同上 |
| `deployment-window-check.yml` | 刻意不装 `requirements-dev.txt`（含 schemathesis/locust/mkdocs，装易失败） | — |
| `dependency-scan.yml` | `requirements.lock`（safety 扫描 + `-r requirements.lock`） | **唯一装 lock 的地方**，但只做漏洞扫描，不跑测试 |
| `Dockerfile`（镜像） | `requirements.txt` | 镜像实际安装集合 ≠ lock（见 §2 第 1 条） |

结论：**`.lock` 目前不参与任何测试执行**，因此下述漂移当下不会让 CI 变红。

## 2. 已确认的 4 处不一致

| # | 文件 | 实测值 | 冲突对象 | 性质 |
|---|---|---|---|---|
| 1 | `requirements.lock` | `httpx==0.25.2` | `requirements-dev.txt`: `httpx>=0.27.0,<0.29.0` | **镜像与测试的 httpx 不同**：生产镜像装 0.25.2，CI 测试解析到 0.28.x。TestClient 对 httpx 版本敏感（0.28 移除了 `app=` 参数），两套组合的行为差异未被任何测试覆盖 |
| 2 | `requirements-dev.lock` | `schemathesis==4.22.4` | `requirements-dev.txt`: `schemathesis>=4.16.0,<4.17.0` | **lock 明确违反声明上界**。上界存在的理由（见 `requirements-dev.txt` 内注释）：`>=4.17` 的 `RequestsTransport.send` 破坏了 `tests/contract/conftest.py` 复用 `starlette_testclient.TestClient` 作为 session 的写法，本地实测 4.16.1 + pytest 8.x 全量 269 passed。谁若改用 `requirements-dev.lock` 装环境，会装到已被排除的版本 |
| 3 | `requirements.lock` | `scikit-learn==1.8.0` | 工件训练版本 `1.7.2` | **工件与运行库版本不一致**：加载 `TfidfVectorizer` / `LogisticRegression` 时实测 `InconsistentVersionWarning: Trying to unpickle estimator ... from version 1.7.2 when using version 1.8.0`（测试仍过，但属未受控的跨版本反序列化） |
| 4 | `requirements.txt` | `scikit-learn>=1.5.0,<2.0.0` | 同上 | range 过宽：允许装到 1.5~2.0 任意版本，而工件只由 1.7.2 训练验证过 |

## 3. 根治建议（本轮未执行，需你决策）

1. **重生成两个 lock**（命令已写在两个文件头部，需网络 + `uv`）：
   ```bash
   uv pip compile backend/requirements.txt      -o backend/requirements.lock      --python-version 3.11 --no-emit-index-url
   uv pip compile backend/requirements-dev.txt  -o backend/requirements-dev.lock  --python-version 3.11 --no-emit-index-url
   ```
   注意：`requirements-dev.txt` 的上界会使重生成结果落在 `schemathesis<4.17`（当前 lock 显然是更早或绕过约束生成的）。**本轮不擅自重生成**：会改动 400+ 行、需联网，且属于「锁定基线」类变更应由你确认基线后再动。
2. **httpx 双版本问题**（#1）需要决策方向：要么镜像也用 `requirements-dev.txt` 口径对齐测试组合，要么 CI 增一条「按 lock 安装」的烟测 job 暴露差异。
3. **sklearn 版本**（#3/#4）：短期可把 `requirements.txt` 的上界收窄到 `>=1.7.2,<1.9` 并在 CI 复跑模型加载测试；根治是**用当前锁定版本重训并重新生成工件**，使训练/运行版本一致。

## 4. 计划验收对照

| 计划验收项 | 本轮状态 |
|---|---|
| 复核 `requirements-dev.txt` 钉版本与 `requirements.lock` 一致性 | ✅ 已复核，**发现 4 处不一致**（§2） |
| 确认 CI 解析版本与本地实测组合一致（防漂移复发） | ✅ 已确认 CI 走 `.txt` 不走 `.lock`（§1），故 CI 与本地实测组合一致；漂移仅存在于 `.lock` |
| 连续 3 次 CI 全绿无版本相关失败 | ⏳ **跨轮次目标**，需后续 CI 观测；本轮基线为全绿 |

## 5. 本轮已执行的处置（2026-10-04 晚）

| # | 处置 | 状态 |
|---|---|---|
| 1（httpx 双版本） | **`requirements.txt` 显式钉 `httpx>=0.27.0,<0.29.0`**（与 dev 同口径）。CI/本地按 txt 安装即刻一致 | ✅ 已改（`requirements.txt`） |
| 1 续 | lock 内 `httpx==0.25.2` **未手工改**：无 `--hash` 允许手改，但离线无法验证依赖树自洽（httpx 0.28 配套的 httpcore 等），手改可能产出装不上的 lock——比漂移更糟。已在两个 lock 头部注明「待联网重生成」 | ⏳ **阻塞：需联网** |
| 3（sklearn 版本） | 保留 `scikit-learn>=1.5.0,<2.0.0` 不动。实测工件由 **1.7.2** 训练、lock 钉 1.8.0，加载时仅 `InconsistentVersionWarning` 而 375 测试全过。**真正的根治是用锁定版本重训工件**，属建模工作，与 P2-1 合并立项更合理 | 📌 转入 P2-1 立项 |
| 2（dev.lock schemathesis） | 同样阻塞于联网（需重生成才会回落到 `<4.17`）。在此之前 CI 不受影响（走 dev.txt 的 range） | ⏳ **阻塞：需联网** |

**联网后一次性根治命令**（两个 lock 均无 `--hash`，可安全重生成）：

```bash
uv pip compile backend/requirements.txt     -o backend/requirements.lock     --python-version 3.11 --no-emit-index-url
uv pip compile backend/requirements-dev.txt -o backend/requirements-dev.lock --python-version 3.11 --no-emit-index-url
```

⚠️ 重生成会覆盖人工加入的头部注释（两处指针 + httpx 说明），重生成后需重新贴上。
⚠️ 本机 PyPI 不可达（`urlopen` 超时），`uv --offline` 亦因缓存元数据不全失败——**必须在有网环境执行**。

## 6. 顺带发现：本地 venv 低于 CVE 修复下限（2026-10-04）

用项目 venv 实测已装版本与 `requirements.txt` 声明的差距：

| 包 | 本地 venv 实测 | `requirements.txt` 声明 | 结论 |
|---|---|---|---|
| httpx | 0.28.1 | `>=0.27.0,<0.29.0`（本轮新增） | ✅ 满足 |
| scikit-learn | 1.8.0 | `>=1.5.0,<2.0.0` | ✅ 满足（但见 §2 #3 的工件版本差） |
| requests | 2.34.2 | `>=2.33.0` | ✅ 满足 |
| **pydantic-settings** | **2.13.1** | **`>=2.14.2`**（SEC-B 修复 GHSA-4xgf-cpjx-pc3j） | ❌ **不满足** |

**影响面**：CI 按 `requirements.txt` 安装 → 拿到 ≥2.14.2，**CI 不受影响**；
但**本地开发与本地测试跑在 2.13.1 上**（低于已声明的 CVE 修复下限）。
这不是本轮引入的漂移，是长期未同步的环境债。

**处置**：本机 PyPI 不可达，无法在本地升级（`pip install -U pydantic-settings` 会失败）。
需在有网环境执行 `pip install -U "pydantic-settings>=2.14.2"` 后重跑本地测试，
确认无回归（2.13 → 2.14 跨小版本，pydantic-settings 依赖 pydantic 版本需一并核对）。
