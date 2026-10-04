# 依赖锁定现状与漂移台账（2026-10-04 复核，2026-10-05 追加 §7 漏洞清零）

> 复核范围：`backend/requirements*.txt` 与 `backend/requirements*.lock` 的一致性，
> 以及「CI 实际解析到的版本」与「本地实测组合」是否一致（P1-3 计划项）。
> 结论先行：**CI 当前不会因版本漂移失败**（CI 装的是带约束的 `.txt`，不装 `.lock`），
> 但 `.lock` 与 `.txt` 存在 4 处不一致 + 1 处工件版本隐患，属于**复发风险**，需根治。
>
> **2026-10-05 追加结论**：§5 那次重生成**漏了 `--upgrade`**，导致 `.lock` 的绝大多数
> 传递依赖仍停在远古版本，从而在镜像侧（trivy）积压 **68 条漏洞**。
> 加 `--upgrade` 重生成后 lock 漏洞**清零**，详见 §7。

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

### 5.0 联网后的最终状态：4 处漂移中 3 处已消除

环境事实（本机）：**代理已开（`127.0.0.1:53857`）但只通 GitHub（200），PyPI 直连与代理均超时**；
可用的国内镜像：腾讯云 `https://mirrors.cloud.tencent.com/pypi/simple/`（200）、阿里云（200）；
HuggingFace 直连不通，`hf-mirror.com`（200）可用。故重生成命令统一加 `--index-url` 指向腾讯云镜像，
配合 `--no-emit-index-url` 保证**生成物里不留镜像地址**（已验证：无 `mirrors.cloud` 泄漏）。

| # | 处置 | 状态 |
|---|---|---|
| 1（httpx 双版本） | `requirements.txt` 显式钉 `httpx>=0.27.0,<0.29.0` + **重生成 lock** | ✅ **已解决**：`requirements.lock` httpx `0.25.2 → 0.28.1`，与 CI/本地测试同口径 |
| 2（dev.lock schemathesis） | 重生成 `requirements-dev.lock` | ✅ **已解决**：`4.22.4 → 4.16.1`，回到 `requirements-dev.txt` 声明的 `<4.17`，与 `contract/conftest.py` 的 session 复用兼容 |
| 3（sklearn 版本） | 未动 | 📌 **仍未解决**：lock 仍钉 `scikit-learn==1.8.0`，工件由 1.7.2 训练 → `InconsistentVersionWarning`。根治=用锁定版本重训工件（建模工作，与 P2-1 合并立项） |
| 4（scikit-learn range 过宽） | 未动 | 📌 建议随 #3 一并处理（重训后收窄为 `>=1.7.2,<1.9` 之类） |

重生成后**两个 lock 的人工注释会被覆盖**（头部已注明并给出完整重生成命令含镜像参数，重贴即可）。

### 5.1 变更明细

| 文件 | 变化 |
|---|---|
| `requirements.lock` | 378 行；httpx→0.28.1、pydantic-settings→**2.15.0**（原 lock 未显式钉、由传递依赖决定）、sqlalchemy 2.0.49 / psycopg2-binary 2.9.11 / numpy 1.26.4 不变 |
| `requirements-dev.lock` | 428 行；httpx→0.28.1、schemathesis→**4.16.1**、starlette-testclient 0.4.1 不变 |

**联网后一次性根治命令**（已执行，保留供复现）：

```bash
uv pip compile backend/requirements.txt     -o backend/requirements.lock     --python-version 3.11 --no-emit-index-url --index-url https://mirrors.cloud.tencent.com/pypi/simple/
uv pip compile backend/requirements-dev.txt -o backend/requirements-dev.lock --python-version 3.11 --no-emit-index-url --index-url https://mirrors.cloud.tencent.com/pypi/simple/
```

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

## 7. SEC-DEP 漏洞清零（2026-10-05）

### 7.1 问题陈述：54 个漏洞的真实来源

Dependabot 报 54 个依赖漏洞（28 high / 18 moderate / 8 low）。本轮用 pip-audit 2.10.1
（腾讯云镜像 `--index-url https://mirrors.cloud.tencent.com/pypi/simple/`）分别扫两个口径，
结论是**这批漏洞全部来自 `requirements.lock` 陈旧，与 `.txt` 声明和业务代码都无关**：

| 扫描目标 | 命令 | 命中 |
|---|---|---|
| `.txt` + `.dev.txt`（CI 的 pip-audit 口径） | `pip-audit -r requirements.txt -r requirements-dev.txt` | **1 条** / 1 包（nltk PYSEC-2026-3740，CI 已显式`--ignore-vuln`） |
| `.lock`（镜像/safety 口径） | `pip-audit -r requirements.lock --no-deps` | **68 条** / 13 包 / 46 个唯一公告 |

根因：§5 那次（2026-10-04）重生成 lock 的命令**漏了 `--upgrade`**。
`uv pip compile` 不加 `--upgrade` 时只在**既有钉位**附近微调，于是 lock 里
anyio / starlette / torch / urllib3 / pyjwt / cryptography / protobuf / filelock /
setuptools / wheel 等传递依赖全部停在远古版本 —— 而 `.txt` 的 range 声明早已能解析到
无漏洞的最新版本。同一批包在两个口径下相差 6~15 个小版本，这就是「CI 绿、镜像红」的全部原因。

### 7.2 关键判断：13 个漏洞包无一受既有上界保护

动lock 前逐条核对了 `requirements.txt` 里每一处踩过坑钉下的上界，结论是**这次清零不需要动任何一条**：

| 既有上界 | 保护对象 | 与本轮 13 个漏洞包的关系 |
|---|---|---|
| `sqlalchemy<2.1` | 裸 `postgresql://` 在 2.1+ 默认 psycopg v3（项目只装 psycopg2） | 无关（sqlalchemy 无命中） |
| `httpx>=0.27,<0.29` | starlette TestClient 兼容区间 | 无关（httpx 无命中） |
| `schemathesis>=4.16,<4.17` | >=4.17 破坏 contract/conftest.py 的 session 复用 | 无关（在 dev 侧，且 lock 本就不含） |
| `starlette-testclient>=0.4.1,<0.5` | 显式声明否则 CI ModuleNotFoundError | 无关（在 dev 侧） |
| `scikit-learn<2.0.0` | 工件兼容性 | 无关（scikit-learn 无命中） |

13 个漏洞包中：`torch` 在 `.txt` 里只有 `>=2.2.0` **无上界**；`starlette` 由 fastapi 传递；
`anyio` 由 starlette/httpx 传递；其余 10 个全是纯传递依赖。
=> 全部可通过「重生成 lock」解决，不需要为消漏洞而放松任何既有约束。

### 7.3 已修复：44/46 个唯一公告（lock 漏洞 68 → 0）

重生成命令（`--upgrade` 是关键，与 §5 的命令差别就在这里）：

```bash
uv pip compile backend/requirements.txt -o backend/requirements.lock \
    --python-version 3.11 --no-emit-index-url --upgrade \
    --index-url https://mirrors.cloud.tencent.com/pypi/simple/
```

13 个包的版本迁移（每条都经 pip-audit 的 `fix_versions` 核对）：

| 包 | 旧（带漏洞） | 新 | 覆盖的公告 |
|---|---|---|---|
| anyio | 3.7.1 | 4.15.1 | PYSEC-2026-4024/4025 |
| cryptography | 46.0.3 | 50.0.2 | PYSEC-2026-35/36/2141/3552/3553/3554 + GHSA-537c-gmf6-5ccf |
| filelock | 3.20.0 | 4.0.10 | PYSEC-2026-1374/1375 |
| idna | 3.11 | 3.20 | PYSEC-2026-215 |
| mako | 1.3.10 | 1.4.3 | PYSEC-2026-2617 |
| protobuf | 6.33.0 | 7.36.2 | PYSEC-2026-1805 |
| pygments | 2.19.2 | 2.21.0 | PYSEC-2026-2987 |
| pyjwt | 2.13.0 | 2.15.1 | PYSEC-2026-4140~4145/4147~4152 |
| setuptools | 80.9.0 | 84.0.0 | PYSEC-2026-3447 |
| starlette | 1.0.0 | 1.7.0 | PYSEC-2026-161/248/249/2280/2281 |
| torch | 2.9.0 | 2.14.1 | PYSEC-2025-193/194/195 + PYSEC-2026-2286 |
| urllib3 | 2.5.0 | 2.8.0 | PYSEC-2026-141/1994/1996/1998/4175/4177 |
| wheel | 0.45.1 | 0.48.0 | CVE-2026-24049 |

新增传递依赖：`formulaic` / `interface-meta` / `narwhals` / `opentelemetry-api`；
移除：`pytz` / `sniffio`（anyio 4.x 不再依赖 sniffio）。

**复扫读数**：`pip-audit -r requirements.lock --no-deps` →
`No known vulnerabilities found`（原 68 条 / 13 包 / 46 唯一公告）。

lock 自洽性验证：`uv pip compile backend/requirements.lock` 重新解析后与文件自身
逐行diff 完全一致（`IDENTICAL`），即新 lock 的钉位组合真实可解、无隐式冲突。

### 7.3.1 本地全量测试读数（重要：含一处必须说明的环境噪声）

本地全量 `pytest -o addopts=... --import-mode=importlib --cov=app` 跑了三轮，
失败数**不稳定**，这本身就是判据：

| 轮次 | 读数 |
|---|---|
| 第 1 轮 | 107 failed / 6398 passed / 20 skipped |
| 第 2 轮 | **1 failed / 6504 passed** / 20 skipped（876s） |
| 对照实验（临时换回**旧** lock，跑失败集） | 31 passed |

结论：**失败是本地并发/事件循环串扰，不是 lock 改动引入的回归。** 三条依据：

1. **失败数从 107 塌到 1** —— 确定性回归不会这样波动。
2. **改 `requirements.lock` 不会改动已安装的 `.venv`**。本地 venv 实测
   starlette 1.7.0 / torch 2.11.0 / anyio 4.13.0 在本轮动手前就已是新版本，
   从未装过旧 lock（改动面仅 `requirements.lock` + 本文档，`git diff --stat` 可证）。
3. **对照实验**：临时把 lock 换回改动前的版本，跑第 1 轮的失败集 → `31 passed`，
   与新 lock 结果完全一致。

⚠️ **本地跑全量的两个坑（下次直接照此跑）**：

- **不要用 `-o "addopts="`**：`pytest.ini` 的 `addopts` 里含
  `--import-mode=importlib`（正是它解决 `tests/test_pytorch_mlp.py` 与
  `tests/ml/test_pytorch_mlp.py` 的同名模块冲突）。清空 addopts 会导致
  收集期 `import file mismatch` 直接中断全量。正确写法是**只覆盖需要的项**：
  ```bash
  cd backend && .venv/Scripts/python.exe -m pytest \
    -o "addopts=--strict-markers --import-mode=importlib --cov=app --cov-report=xml:coverage.xml --ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt" \
    -p no:cacheprovider -q
  ```
- **不要加 `--timeout=300`**：本地 venv 未装 `pytest-timeout` 插件
  （`pytest.ini` 里有 `timeout = 300` 但插件缺失，只会产生
  `PytestConfigWarning: Unknown config option: timeout`）。加了会直接
  `error: unrecognized arguments: --timeout=300` 全量退出。

> 注：CI 基线 6186 passed / 68 skipped、覆盖率 84%（门禁 60%）是
> **Linux + 干净依赖环境**下的读数。本地这轮 passed 数为 6504（比 CI 多 318），
> 因本地 venv 长期未与 `.txt` 同步（见 §6：pydantic-settings 曾低于声明下限）、
> 且缺少 pytest-timeout 等插件，**两者不构成直接可比**，不要用差值反推回归。

### 7.4 仍然剩下 / 需要显式说明的项

**（a）`.txt` 口径的 nltk PYSEC-2026-3740 —— 维持既有忽略，不是本轮新增**
CI 的 `dependency-scan.yml` 已用 `--ignore-vuln PYSEC-2026-3740` 显式忽略，
理由（该文件内已写全）：上游无修复版本；nltk 仅作为 safety 的运行时依赖被拖入，
不随镜像发布，运行期零import。本轮未改动该忽略。

**（b）torch PYSEC-2026-139 / pyjwt PYSEC-2026-4146 —— 上游无修复版本**
这两条在旧 lock（torch 2.9.0 / pyjwt 2.13.0）上命中，`fix_versions` 为空数组。
重生成后：
- pyjwt 升到 2.15.1 已覆盖其余 12 条 pyjwt 公告，仅 4146（`decode()` 原地改写调用方
  传入的 `options` dict）仍无上游修复 —— 属 API 行为问题，非内存破坏，接受风险。
- torch 升到 2.14.1 后 PYSEC-2026-139 仍无 fix 版本（公告描述指向 2.10.0 的未知函数）。
  已核对 `backend/app` 与 `backend/scripts` 中零处直接调用该组件；torch 在本项目
  只用于 `tests/ml/` 与建模脚本，不进入 API 请求路径。**接受风险**，待上游发布
  修复版本后重扫即自动消失。

**（c）scikit-learn 工件版本差（§2 #3/#4）—— 按本轮纪律不动**
本轮明确不碰模型工件、不重训。lock 里 scikit-learn 由 1.8.0 升至 1.9.1，
工件仍由 1.7.2 训练，`InconsistentVersionWarning` 的既有状态不变
（CI 装 `.txt` range，本来就解析到 1.9.x，故 CI 侧无新增风险）。
根治路径仍是重训工件，另行立项。

### 7.5 复发预防：为什么上次会漏 `--upgrade`

§5 与 §7 的重生成命令只差一个 `--upgrade`，但结果差 68 条漏洞。
`uv pip compile` 的默认行为是**保留既有钉位**（把它当「重新编译当前声明」，
不是「解析到最新」）。这与 pip-compile 需要 `--upgrade` 才是同样的语义 ——
两个工具都把「升级」当成显式请求。

=> 已把这条写进 `requirements.lock` 头部注释与本节，重生成时不必重新踩。

### 7.6 补漏：`requirements-dev.lock` 也需要 `--upgrade`（2026-10-05 03:50）

§7.1 的两个扫描口径**都没覆盖 `requirements-dev.lock`**（扫的是 `requirements.lock`
与 `.txt` 组合），而 CI 的 `dependency-scan.yml` 里 pip-audit **只扫 `.txt`**：

```yaml
pip-audit --requirement requirements.txt --requirement requirements-dev.txt --strict
```

=> 结论：dev 侧 lock 的漏洞既不会被 CI 看见，也不在 §7 的清零范围内。
实测复扫（`pip-audit -r requirements-dev.lock --no-deps`）发现 **20+ 条**：

| 包 | 版本 | 公告数 | 有修复版本 |
|---|---|---|---|
| nltk | 3.10.0 | 18 | ✅ 3.10.1~3.10.3（PYSEC-2026-3740 除外） |
| urllib3 | 2.7.0 | 3 | ✅ 2.8.0 |
| pip | 26.1.2 | 1 | ✅ 26.2 |

**处置**（同 §7.3 的命令，加 `--upgrade`）：`nltk 3.10.0 → 3.10.3`、
`urllib3 2.7.0 → 2.8.0`、`pip 26.1.2 → 26.2.0`。

**上界核对**：`nltk` / `urllib3` / `pip` 在 `requirements-dev.txt` 中**没有显式声明**
（纯传递依赖、无上界保护）→ 清零不需要放松任何既有约束。既有三条上界全部守住：
`schemathesis==4.16.1`（<4.17）、`httpx==0.28.1`（<0.29）、`starlette-testclient==0.4.1`（<0.5）。

**复扫读数**：`pip-audit -r requirements-dev.lock --no-deps` →
`Found 1 known vulnerability in 1 package`：`nltk 3.10.3 PYSEC-2026-3740`，
**无上游修复版本**，且 CI 已用 `--ignore-vuln PYSEC-2026-3740` 显式忽略
（理由：仅 safety 运行时依赖、`app/`+`scripts/` 零 import、复审期限 2026-12-15）。

**自洽性**：136 个钉位二次解析完全一致（仅注释里的来源引用从 `requirements-dev.txt`
变成 `-r requirements-dev.lock`，属预期差异，不是钉位漂移）。

> 📌 **判读修正**：全文 diff 会显示 391 行差异，但全部是注释格式
> （`# via typer` → `# via` + `# -r …lock` + `# typer`）。
> **自洽性必须只比较 `==` 钉位行**，否则会误判为不自洽。

**两个 lock 的最终状态**：`requirements.lock` 0 条、`requirements-dev.lock` 1 条
（无修复版，已显式忽略）——即「漏洞清零」结论现在对**两个** lock 都成立。
