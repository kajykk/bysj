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
