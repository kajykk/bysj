# 代码全面优化计划（2026-08）

> **文档状态**：执行中（四轮已完成，T15/T16 及高风险/大范围任务仍待排期）
> **生成依据**：2026-08-26 全仓四路并行代码审计（仅读源码，未参考任何缓存/状态/临时文件）
> **验证基线**：后端 `pytest tests/api tests/services tests/unit --no-cov` = **1331 passed / 10 skipped**；前端 `npm run typecheck` 零错误 + vitest 全过
> **关联文档**：[architecture.md](architecture.md) · [FULL_AUDIT_REPORT.md](FULL_AUDIT_REPORT.md) · [FRONTEND_OPTIMIZATION_PLAN.md](FRONTEND_OPTIMIZATION_PLAN.md) · [剩余任务执行计划](REMAINING_TASKS_PLAN_202608.md)

---

## 目录

- [一、审核背景与范围](#一审核背景与范围)
- [二、审核发现汇总](#二审核发现汇总)
- [三、已完成优化记录（三轮）](#三已完成优化记录三轮)
- [四、剩余任务详细计划](#四剩余任务详细计划)
  - [P0 快赢层（低风险）](#p0-快赢层低风险可随时插入)
  - [P1 后端结构重构（中风险）](#p1-后端结构重构中风险)
  - [P2 契约与分层治理](#p2-契约与分层治理)
  - [P3 架构级改造（需专门排期窗口）](#p3-架构级改造需专门排期窗口)
  - [P4 ML / scripts 债务（独立并行）](#p4-ml--scripts-债务独立并行)
  - [P5 前端收尾（独立并行，低风险）](#p5-前端收尾独立并行低风险)
- [五、执行顺序与依赖关系](#五执行顺序与依赖关系)
- [六、通用保障措施](#六通用保障措施)
- [七、进度跟踪总表](#七进度跟踪总表)

---

## 一、审核背景与范围

### 1.1 审计对象与规模

| 区域 | 规模 | 审计方式 |
|---|---|---|
| `backend/app` | 242 个 Python 文件（core 61 / services 60 / api 50 / models 12 / schemas 15 / ml 26 等） | 并行子代理只读审计 + 反模式 Grep 扫描 |
| `frontend/src` | 340 个 TS/Vue 文件 | 同上 |
| `backend/app/ml` | ML 库模块 | 同上 |
| `scripts` | 189 个 Python 脚本 | 同上 |

### 1.2 审计纪律

- **不参考任何状态文件**：跳过 `.cache`、`htmlcov`、`dist`、`node_modules`、日志、临时产物
- 仅基于源码本身给出结论，每条发现附 `文件:行号` 证据
- 发现按严重度分级（高/中/低），修复前逐条人工核实上下文

---

## 二、审核发现汇总

### 2.1 后端核心（core / main.py）

**整体评价**：工程质量显著高于常见毕业设计水平——无 SQL 注入（全 ORM 绑定）、无硬编码密钥（生产启动期强制校验+快速失败）、pickle 加载三重防护、token blocklist fail-closed。短板集中在中间件栈顺序正确性、超长函数与成段复制的逻辑。

| 编号 | 严重度 | 问题 | 位置 |
|---|---|---|---|
| H-1 | 高 | 中间件注册顺序错位：request_id 位于最内层（外层日志拿不到 request_id）；CORS 最内层化使错误响应缺 CORS 头；SlowAPI 中间件层抛出的 RateLimitExceeded 无法被内层异常处理器捕获，429 可能退化为 500 | `main.py:300-326`、`rate_limit.py:151-176` |
| H-2 | 高 | metrics_middleware 无异常保护，异常收场的请求不计入指标，SLO 可用性偏乐观 | `middlewares.py:92-94` |
| H-3 | 高 | `except BaseException` 吞掉 CancelledError，破坏任务取消语义且误报 failed | `main.py:159-173` |
| M-2 | 中 | except 分支重复执行同一段赋值（无效重试死代码） | `model_engine/loading.py:460-477` |
| M-3 | 中 | WS 认证(10s)/空闲(300s) 超时硬编码未入 settings | `ws.py:317,356,407` |
| M-4 | 中 | WS 鉴权查库绕过 db_breaker，DB 故障时每连接直连池等待 | `ws.py:392-398` |
| M-5 | 中 | safe_pickle 两个加载函数 ~45 行校验逻辑逐行重复 | `safe_pickle.py:141-207 vs 259-328` |
| M-6 | 中 | 租户依赖工厂重复"角色+租户一致性"校验块 ×2 | `tenant_context.py:246-256, 300-309` |
| M-7 | 中 | JWT 密钥安全校验逻辑双份维护 | `config.py:207-216 vs 496-509` |
| M-9 | 中 | core 成为"上帝包"（61 文件），靠延迟导入规避循环依赖 | `core/*` |
| M-10 | 中 | 权限矩阵手工复制 user 权限子集，存在漂移风险 | `deps.py:77-87` |
| M-12 | 中 | get_real_client_ip 每请求重建受信代理集合 | `rate_limit.py:42-46` |
| L-1~L-4 | 低 | 静默异常吞噬、token 构建三兄弟样板重复、废弃 /health 端点同步 I/O 等 | 见审计原文 |

### 2.2 API 与服务层

**整体评价**：模型层索引完善、count 全用 `select(func.count())`、分页参数带校验、限流全覆盖。债务集中在事务边界不成文、异步纪律不彻底、"修而不撤"的并行实现。

| 编号 | 严重度 | 问题 | 位置 |
|---|---|---|---|
| AH-1 | 高 | 归档 N+1：对每个受影响用户循环 2 条查询（2N 次往返） | `admin_service_archive.py:176-192` |
| AH-2 | 高 | 内存分页：pending/overdue 全量加载 Python 列表后切片 | `content_governance.py:284-292` |
| AH-3 | 高 | 同步 Pillow 重编码 + ClamAV 网络扫描直接内联 async 端点，阻塞事件循环 | `user_upload.py:192,283` |
| AH-4 | 高 | 死代码：泛型 BaseService 全项目 0 采用 | `base_service.py`（205 行） |
| AH-5 | 高 | 巨型函数 anonymize_user 约 352 行，合规关键路径不可单测 | `gdpr_service_anonymize.py:59` |
| AM-6 | 中 | ~49 端点缺 response_model；ApiResponse 泛型形同虚设（data 恒 null） | auth/user_content/content_governance 等 |
| AM-7 | 中 | 事务边界不一致：commit 散落 API/Service 两层；admin.py 审计日志与业务更新不在同一事务 | 多处 |
| AM-8 | 中 | batch_export_excel 流式/非流式双分支重复约 110 行 | `reports.py:151-257` |
| AM-9 | 中 | get_metrics 单函数 252 行 × 13 处宽捕异常 | `metrics.py:56` |
| AM-11 | 中 | model_predict_service God module（789 行）：全局 TRAINING_JOBS 字典 + Lock + JSON 持久化 + 推理缓存 + fusion 混居 | `model_predict_service.py` |
| AM-12 | 中 | PDF 三套并行管线（同步/进程内 asyncio/Celery），pdf_job_store 存进程内存（重启即失、多实例不共享） | `reports.py:74,277,493` |
| AM-14 | 中 | refresh_token 约 102 行逻辑内联 API 层，分层不一致 | `auth.py:207-330` |

**最值得重构 Top5**：gdpr_service_anonymize ✅已拆 · model_predict_service · metrics.py · reports.py 三管线 · observability 聚合函数群

### 2.3 前端 src

**整体评价**：成熟度远超典型毕设——路由懒加载全覆盖、定时器/监听器/WS 清理齐全、几乎无 any 滥用、GET 去重与 401 刷新队列完备。短板在"最后一公里"：基础设施建成但未被消费方接入。

| 编号 | 问题 | 位置 |
|---|---|---|
| F-M1 | VirtualList 组件零使用（有虚拟化能力但无消费方） | components/common/VirtualList |
| F-M2 | UserRiskPage 自动融合流程一次提交触发两次 report+trend 请求瀑布 | UserRiskPage.vue |
| F-M3 | escapeHtml 双份维护 | RiskReportTab.vue:396 与 sharedDashboardUtils.ts:68 ✅已收敛 |
| F-M4 | GET 去重通过猴子补丁覆写 axios 实例方法，升级易碎 | request.ts:308-354 |
| F-L1 | 生产代码残留 3 处 console.log | serviceWorker.ts ✅已修 |
| F-L2 | 8 处内联 toLocaleString 绕过统一 formatDate | 多组件 ✅已收敛 |
| F-L4 | 四个组件略超 500 行阈值 | RiskReportTab/TextAssessTab/UserRiskPage/CounselorUserDetailPage |
| F-L5 | i18n 语言包单文件 ~2290 行，多角色混居 | zh-CN.ts / en-US.ts |
| F-L6 | 危机干预热线号码硬编码模板 | UserRiskPage.vue:240-274 |

### 2.4 scripts 与 backend/app/ml

**整体评价**：ml 库本身质量高（全程 logging、批处理、文档充分）；真正债务集中在 scripts——176 个脚本中相当比例是一次性研究脚本直接入库。

| 编号 | 问题 | 规模 |
|---|---|---|
| S-H1 | 33 处硬编码绝对路径（`C:\Users\k\Downloads` 等，换机即失效） | 论文 docx 工具链 ~30 脚本 |
| S-H2 | m4_fusion_retrain{,_v2,_v3,_v4} + stacking + save_artifacts 复制粘贴家族，delong_test 复制 5 份 | ~2500 行，估计 500 行可覆盖 |
| S-H3 | 40 处宽泛/裸异常吞噬后继续打印成功 | deep_scan_zip_v3(8处) 等 |
| S-H4 | 一次性调试脚本入库 | `_tmp_check_*` 等 9 个 ✅已删 |
| S-M6 | 63 处 `sys.path.insert` path hack | scripts 全局 |
| S-M7 | train_physiological xgb/lgbm 76% 同文 | 420 行 ×2 |
| S-M10 | SEEDS=[42,1337,2024] 在 10+ 脚本重复定义，已有漂移（m3 变为 [42,123,7]） | 全局 |
| S-M11 | statistical_tests 类型撒谎（声明 dict 返回 None）✅已修；model_loader 导入时文件系统探测副作用 | `ml/*` |

---

## 三、已完成优化记录（三轮）

> 以下改动均已合入工作区并通过回归验证。提交建议按轮次分批 commit。

### 第一轮（21 文件，+156/−146 行）

**P1 正确性**
- [x] H-2 metrics 中间件 try/finally 保护，异常请求也计入指标 — `core/middlewares.py`
- [x] H-3 CancelledError 补重抛 + skipped 状态，不再吞取消信号 — `main.py`

**P2 性能**
- [x] M-12 受信代理解析 lru_cache（按配置原文为键，兼容运行期变更）— `core/rate_limit.py`
- [x] AH-3 上传处理 `asyncio.to_thread` 化（单文件+批量两处）— `api/v1/user_upload.py`
- [x] review_service 4 条串行 count 合并为单条条件聚合（COUNT FILTER）— `services/review_service.py`

**P3 质量**
- [x] M-7 删除 config 中不可达的模块级 JWT 双份校验（validator 为唯一权威）
- [x] PYTORCH_AVAILABLE/TRANSFORMERS_AVAILABLE 注释修正（经查测试有消费，属受保护契约勿删）
- [x] loading.py 无效重试删除；log_sanitizer 静默 pass 改 debug 日志并补 logger；text_tokenizer 收窄 except AttributeError
- [x] statistical_tests 类型注解修正 `dict | None`

**P4 前端**
- [x] 新增 `utils/security.ts` 统一 escapeHtml（F-M3），sharedDashboardUtils re-export 保持兼容 + 6 用例单测
- [x] F-L2 九处内联日期格式化收敛到 formatUtils.formatDate
- [x] F-L1 serviceWorker console.log 加 DEV 守卫

**验证**：py_compile ✅ ruff ✅ 后端 91 用例 ✅ 前端 typecheck 零错误 ✅ vitest 60 用例 ✅

### 第二轮（后端 16 文件）

- [x] **H-1 中间件栈重构**：新增 `SafeRateLimitMiddleware`（就地捕获中间件层 RateLimitExceeded → 429 JSON）；main.py 注册序重排为 request_id(最外)→security_headers→metrics→CORS→SafeRateLimit→SlowAPI→tenant_context(最内)；新增全栈回归测试 `tests/test_rate_limit_middleware_stack.py`（429 非 500 + 错误响应带 X-Request-ID/CORS）
- [x] M-10 admin 权限改程序化并集（admin专属 ∪ user全量）
- [x] M-4 WS 鉴权查库接入 db_breaker（OPEN 快速失败 4503）
- [x] L-3 token 构建三兄弟收敛 `_build_token()`
- [x] M-5 safe_pickle 抽取 `_validated_model_file()`（文案逐字节保留）
- [x] M-6 tenant_context 抽取 `_check_role_and_tenant()`
- [x] AH-5 gdpr anonymize_user 352 行拆分为编排 + 11 个步骤函数（⚠️ verify_password 必须保持模块级导入，tests 通过 patch 该符号注入替身，已在 docstring 标注）
- [x] scripts 清理：删除 10 个 gitignore 的 `_tmp_check_*` 等草稿（确认零引用）；gen_canary_traffic.py / deep_scan_zip.py v1 加 DEPRECATED 头

**验证**：777 passed / 0 failed（unit+core+api 广谱回归）

### 第三轮（后端 8 文件）

- [x] AH-1 归档 N+1：ROW_NUMBER() 窗口函数 + 单条 IN UPDATE（2N→2 次往返，id DESC 平局裁决）
- [x] AH-2 内存分页：单条 OR 查询 + CASE 排序（保持 pending 在前原语义）+ 数据库端 offset/limit/count
- [x] M-3 WS 超时配置化：`websocket_auth_timeout_seconds`(10s) / `websocket_idle_timeout_seconds`(300s)；ws.py settings 提升为模块级导入
- [x] AM-14 refresh_token 下沉 `AuthService.refresh()`（8 条 401 契约消息逐字保留；清理 6 死导入 + 死函数 _to_utc_naive）
- [x] AM-8 Excel 导出双分支去重：抽 `_safe_export_filename` / `_record_excel_export_audit` / `_XLSX_MEDIA_TYPE`（非流式分支 row_count 保持 len(payload.data) 原语义）

**验证**：1327 passed / 10 skipped / 0 failed（api+services+unit 全目录）

### 三轮累计

- 后端 24 文件修改、前端 12 文件修改、新增 3 文件（security 工具+测试、限流全栈回归测试）
- 删除 10 个草稿脚本；累计回归 **2100+ 用例零失败**

### 第四轮（结构重构 + 契约 + 前端收尾）

**执行内容**
- [x] T1-1~T1-5 快赢层五项：核验后确认既有实现已覆盖，纳入记录
- [x] T2 model_predict God module 拆分：新增 `services/model_predict/`（training_jobs / inference / fusion + 门面 `__init__.py`），旧 import 路径经 re-export 保持兼容
- [x] T3 metrics 拆分：新增 `api/v1/metrics_helpers.py`，抽取指标采集与 Prometheus 查询解析
- [x] T5-B1 auth 8 端点补具体 response_model（`schemas/auth.py` 扩展）
- [x] T8 新增 `backend/pyproject.toml` 可安装包配置
- [x] T13 UserRiskPage 自动融合重复请求消除
- [x] T14 request.ts 新增显式 `dedupedGet`（旧猴子补丁机制保留兼容）
- [x] T17 删除零引用 VirtualList 组件及测试
- [x] T18 危机热线号码迁入 zh-CN/en-US i18n

**收尾修复：FIX-ORDER-2 测试顺序依赖（transformers 5.x _LazyModule）**

全量基线复跑发现 1 例失败：`test_experiment_trainer.py::test_train_full_flow_with_mocks`（单跑通过、`tests/api` 之后必现）。

- **根因（经四组探针实证）**：transformers 5.5.0 顶层为 `_LazyModule`，对它做属性级 @patch 存在两种失效模式——
  a) **深层路径 patch + 先前实体化**：其他用例真实触发过 transformers 导入后，顶层 `__dict__` 已缓存真类；`from transformers import X` 直接命中字典，深层 patch（如 `tokenization_auto.AutoTokenizer`）不再转发 → 全量运行必现；
  b) **顶层多符号堆叠 patch**：解析后续属性（如 Trainer）时 `_LazyModule` 批量物化会覆写字典，把先挂上的 mock（如 AutoTokenizer）冲回真类 → 单跑也复现（探针 F）。
  即对该模块的任何属性级 patch 都不可靠，与导入顺序强耦合。
- **修复**：测试内不再对 transformers 做任何 @patch，改为 `_inject_fake_transformers(monkeypatch)` 向 `sys.modules` 整体注入假 transformers 模块（含真实基类 TrainerCallback 以支持 `class EpochHistoryCallback(TrainerCallback)` 定义），函数级 `from transformers import ...` 无论历史状态如何都只拿到假货；datasets 同样强制注入保持封闭；monkeypatch 结束自动恢复。文件内两个使用堆叠 patch 的用例统一迁移。
- **教训**：对 `_LazyModule` 型库（transformers≥4/5、pandas API 等），mock 粒度应选择"消费方可见边界"——函数内动态导入的场景，sys.modules 注入是唯一与导入顺序无关的方案。

**验证**：定向回归 144 passed；vitest 1112 passed / 4 skipped；typecheck 通过；基线复跑 **1327 passed / 10 skipped / 0 failed**（含 FIX-ORDER-2 修复；原失败组合 tests/api+trainer 单独复现组合亦通过）

> ⚠️ **基线口径澄清**：本计划第六节的基线命令为 `pytest tests/api tests/services tests/unit --no-cov`。
> 直接跑全量 `pytest` 会包含 e2e/performance/stability/integration 等需要本地 Redis、Grafana、
> 运行中后端的目录——离线环境下会因连接重试/HF 下载阻塞而"卡住无失败输出"，属预期行为而非缺陷
> （第四轮的 test_experiment_trainer 失败即属此类：mock 失效后真实 from_pretrained 阻塞在网络层）。
> 另建议设置 `$env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"` 后再跑任何后端测试。

### 第五轮（T4-P1 列表统一 + T5-B2 契约补齐）

**T4-P1 发现**：审计中"三套 PDF 管线"的主路径（Celery）**已具备** Redis 共享存储
（`tasks/pdf_report.py` 的 save/get_job_to_redis + `pdf:bytes:*`），真正的缺口是
**任务列表端点只聚合进程内存储，Celery 任务对前端/运维不可见**。

- [x] `tasks/pdf_report.py` 新增 `list_jobs_from_redis(created_by)`：遍历索引集合
      `pdf:jobs`，读取任务 JSON 并规范化为与 `PdfJob.to_status_dict()` 相同的形状
      （epoch 时间戳转 ISO、追加 `backend="celery"` 标记）；Redis 故障内层降级为空列表
- [x] `reports.py` `/reports/pdf/jobs` 合并双后端任务（内存项补 `backend="local"`，
      celery 经 `asyncio.to_thread` 读取，按 id 去重、created_at 倒序）；
      Redis 不可用时静默跳过（与生成端点的回退语义一致）
- [x] 新增 4 个 `TestListJobsFromRedis` 用例（归一化/过滤/Redis 宕机/孤儿索引项）
- **T4 剩余（P2）**：asyncio 进程内路径下线转发 Celery、status/download 端点合一、
  旧路由兼容包装——行为变更，需排期窗口

**T5-B2**：
- [x] 新增 `schemas/analytics.py`：EventsSubmit/ConsentStatus/ConsentUpdate/
      AnalyticsEventRecord/EventsQuery 五个响应模型（与 ok() 实际返回逐字段对齐）
- [x] `analytics_events.py` 四个端点补 `ApiResponse[具体模型]`
- [x] 新增契约测试范式 `tests/api/test_analytics_response_contract.py`：直接断言
      OpenAPI 中 data 的 $ref 与字段集合（注意 `T | None` 生成 anyOf，需解包）——
      该模式可复制用于 B3/B4 批次
- [x] 基线更新为 1331 passed（+4 契约用例）

**验证**：ruff 通过；`test_pdf_celery` 23 passed；契约测试 4/4；全量基线
**1331 passed / 10 skipped / 0 failed**

---

## 四、剩余任务详细计划

### P0 快赢层（低风险，可随时插入）

#### T1-1 ARTIFACTS_DIR 导入时副作用改懒加载

- **文件**：`backend/app/ml/model_loader.py:40-51`
- **问题**：`ARTIFACTS_DIR = _resolve_artifacts_dir()` 在 import 时执行文件系统探测，测试难 mock；`except Exception: pass` 吞掉 settings 导入错误
- **步骤**：
  1. `_resolve_artifacts_dir()` 包 `@lru_cache(maxsize=1)` 的 getter，首次访问才探测
  2. except 分支补 `logger.warning("artifacts dir resolution failed, fallback to default", exc_info=True)`
- **验证**：`pytest tests/ml`；import 模块时无文件系统访问（可用 monkeypatch 断言）
- **工作量**：0.25d

#### T1-2 bootstrap 退化样本计数上报

- **文件**：`backend/app/ml/model_validation.py:112-115`
- **问题**：bootstrap 循环内 `except Exception: continue`，退化样本静默剔除无计数
- **步骤**：循环外计数器；结果 dict 增加 `"degenerate_samples": n` 字段并在 logger.warning 中体现
- **验证**：构造全同类标签样本的单测断言计数
- **工作量**：0.25d

#### T1-3 调参结果缓存与早剪枝

- **文件**：`backend/app/ml/hyperparameter_tuning.py:46-58`
- **问题**：默认网格 162 组合、每组从头完整重训，无断点续跑
- **步骤**：
  1. 每组合评估完成后追加写入 JSON 结果文件（key=参数指纹 hash）
  2. 启动时加载已有结果跳过已完成组合
  3. 可选：按当前最优中位分剪枝明显劣质组合（早停）
- **验证**：同一数据跑两遍，第二遍命中缓存秒级完成；最终最优参数与一次性跑完一致
- **工作量**：0.5d

#### T1-4 业务公式裸常数收敛

- **文件**：`backend/app/core/model_engine/fallback.py:63-79`（权重 5.0/2.5/10.0/15.0/8.0…）、`predict.py:199-218`（0.1/0.3/0.7/0.9…）
- **问题**：直接影响临床分级输出的启发式权重散落代码中，无出处注释
- **步骤**：提为模块级具名常量表（如 `_FALLBACK_WEIGHTS`），注明标定依据/来源实验；数值不变
- **验证**：现有预测单测回归，输出逐字段 diff 为零
- **工作量**：0.25d

#### T1-5 get_db 重复局部导入归位

- **文件**：`backend/app/core/database.py:80,93,102`
- **步骤**：验证无循环导入后移至模块顶部；若有环则合并为一处并注释原因
- **验证**：全量 import 冒烟 + db 相关单测
- **工作量**：0.1d

---

### P1 后端结构重构（中风险）

#### T2 model_predict_service God module 拆分（789 行）

- **现状**：全局可变 `TRAINING_JOBS` 字典 + Lock + JSON 磁盘持久化 + LRU 淘汰 + 推理缓存 + breaker 调用 + predict_fusion(105行) 全部混居一个模块
- **目标结构**：

```
services/model_predict/
├── __init__.py          # 门面：re-export 全部旧符号，调用方零改动
├── training_jobs.py     # 任务存储：TRAINING_JOBS + Lock + JSON 持久化 + LRU
├── inference.py         # 推理缓存 + breaker 调用 + predict_* 编排
└── fusion.py            # predict_fusion
```

- **步骤**：
  1. **先补 characterization tests**：锁定全部公开函数签名与输入输出（含并发加锁行为、持久化读写格式）
  2. 按"先纯搬移、后解耦"原则切三刀；门面 `__init__.py` re-export 保证 `from app.services.model_predict_service import X` 兼容
  3. 全局状态收敛到 `training_jobs.get_store()` 单例访问器，禁止新代码直触字典
  4. grep 全仓引用确认门面覆盖完整后删除旧文件路径 shim
- **风险与对策**：
  - 全局可变状态是雷区 → 第 1 步 characterization tests 是安全网
  - pickle/joblib 工件可能引用旧模块路径 → 迁移后加载一次存量模型工件验证
- **验证**：`pytest -k predict` + 契约测试 + 手动触发一次完整训练任务走通
- **工作量**：1.5~2d　**完成标准**：旧 import 路径全部可用、无行为差异、单文件不再超过 300 行

#### T3 metrics / observability 超长函数拆分

- **文件**：`api/v1/metrics.py:56`（get_metrics 252 行、13 处宽捕）、`observability/aggregate.py`（4 个 `_compute_*` 各 102-148 行）、`observability/query.py`（3 个 124 行函数）、`observability/__init__.py:74`（alertmanager_webhook 166 行）
- **步骤**：
  1. get_metrics 拆为每指标一个 `_collect_xxx()` 协程 + `asyncio.gather` 并行采集
  2. 统一降级装饰器（`@degrade_to(None)`）替换分散的 `except Exception`，失败指标记入响应的 `degraded: []` 字段便于排障
  3. aggregate/query 按时间窗解析 / 过滤构建 / 聚合执行三段抽私有函数
- **验证**：重构前后各抓一份 `/metrics` 与 observability 响应 JSON 做**逐字段 diff**（必须一致）；契约测试
- **工作量**：1~1.5d

#### T4 PDF 三管线收敛（行为变更，需排期窗口）

- **现状**：`reports.py` 三条生成路径并存——同步(:74) / 进程内 asyncio 任务(:277) / Celery 队列(:493)，各自独立的 status/download 端点与鉴权检查；`pdf_job_store` 把 PDF 字节存进程内存（重启即失、多实例不共享）
- **方案**：统一 Celery + Redis 存储（job 元数据 + 字节均入 Redis，TTL 1h）；同步路径保留用于小报告即时下载
- **步骤**：
  1. 新增 `PdfJobStore(Redis)` 实现，与内存版同接口，配置开关切换（灰度期）
  2. 进程内 asyncio 路径下线：端点内部转发 Celery，响应结构不变
  3. 两组 status/download 端点合一；旧路由做兼容包装，两个版本周期后删除
  4. 审计块复用第一轮 R5 的公共辅助模式
- **风险与对策**：
  - 多实例部署行为变化 → 上线前在 docker-compose 双副本环境过 E2E
  - Redis 故障降级策略必须明确：拒绝任务并告警，**不得静默回落进程内存**
- **前置条件**：Redis 可用的集成环境
- **验证**：E2E test_grafana_e2e 之外的 reports 相关 e2e + 手动三场景（小报告同步/大队列 Celery/重启后 job 仍可下载）
- **工作量**：2~3d

---

### P2 契约与分层治理

#### T5 response_model 补齐（49 端点，机械但量大）

- **问题**：191 端点中约 49 个裸 dict 返回无 response_model；已用的 `response_model=ApiResponse` 未传类型参数（OpenAPI 中 data 恒为 null）
- **批次划分**（每批一个 PR，契约测试护航）：

| 批次 | 文件 | 端点数 | 备注 |
|---|---|---|---|
| B1 | auth.py | 8 | 已有 schemas/auth.py 基础，最快见效 |
| B2 | user_content.py + analytics_events.py | 11 | 多数返回 ok() 包装 dict |
| B3 | content_governance.py + ops_dashboard.py | ~10 | 列表型需要 Paginated 泛型 |
| B4 | gdpr.py + uploads.py + metrics.py 等 | ~20 | 收尾 |

- **关键前置设计**：
  1. `schemas/common.py` 增加 `PaginatedResponse(Generic[T])` 与 `ok_envelope(data_model)` 辅助
  2. 存量 `response_model=ApiResponse` 一并修正为 `ApiResponse[XxxData]`
  3. OpenAPI schema snapshot 测试：每批完成后 diff，**只允许新增约束、不允许删除字段**
- **风险与对策**：response_model 会做输出校验，历史脏数据可能触发 500 → 首批部署 staging 观察日志，Schema 字段先全 Optional 再逐步收紧
- **工作量**：3~4d　**完成标准**：全部端点有具体类型参数的 response_model；OpenAPI 文档 data 字段可导航

#### T6 事务边界统一

- **先立约定（写入 docs/architecture.md ADR），后迁移**：
  - 规则 1：业务 commit 只发生在 Service 层；API 层只消费返回值
  - 规则 2：审计日志（OperationLog）与业务变更必须同事务提交
  - 规则 3：跨聚合操作由上层服务编排，禁止单端点多 commit
- **迁移顺序**（按 commit 数降序）：silences.py(×7) → canary.py(×6) → tenant_admin.py(×4) → admin.py:400-418（修复审计与业务不同事务）→ auth/gdpr/reports 收尾
- **验证**：每迁移一个文件跑对应 api 测试；专项测试"service 抛异常时数据库无部分提交"
- **工作量**：2~3d

---

### P3 架构级改造（需专门排期窗口）

#### T7 core 包拆分（61 文件"上帝包"）

- **现状**：HTTP 中间件、WS、Celery、Sentry/OTel、ML 引擎、安全全部塞进 core；health.py 顶层导入 celery_app 使 API 进程初始化 broker；大量函数内延迟导入是循环依赖的结构性信号
- **目标分层**：

```
app/
├── core/       # 仅剩真正横切件：config / database / security / request_id / log_sanitizer
├── infra/      # cache / db_breaker / celery_* / otel / sentry / rate_limit / ws / event_bus
├── security/   # deps / tenant_context / safe_pickle / pii_crypto / kill_switch
└── ml/         # model_engine 整体迁出（与 app/ml 库区分：引擎 vs 算法库）
```

- **步骤**：
  1. 用 `pydeps` / import-linter 画依赖图，标出延迟导入掩盖的环
  2. 引入 import-linter CI 规则**先冻结现状**（禁止新增违规），再渐进搬迁
  3. 搬迁顺序：infra（叶子最多）→ security → model_engine；每搬一个模块全仓改导入 + 留 re-export shim 一个版本周期
  4. health.py 的 celery 导入改惰性获取
- **风险**：极高（涉及几乎所有文件）→ 必须单独分支、每步独立可合入；预留 1 周实施 + 1 周观察期
- **验证**：每步全量 pytest；启动冒烟（uvicorn 冷启动无 broker 连接日志）

#### T8 backend 可安装包化（消除 63 处 sys.path hack）

- **步骤**：
  1. 根部新增 `pyproject.toml`（setuptools，`app` 为包，extras：`[ml]` 含 torch/transformers）
  2. README + CI 增加 `pip install -e .[dev]` 步骤
  3. 新 scripts 直接 `from app.xxx import`；存量 63 处 hack 在触碰对应脚本时顺手删（不做专门批量改，避免无效 churn）
  4. tests/conftest.py 统一注入 backend 路径，删除 tests 内散布的 path 操作
- **工作量**：0.5d 搭建 + 渐进迁移

---

### P4 ML / scripts 债务（独立并行）

#### T9 m4_fusion 六件套参数化合并

- **对象**：`scripts/m4_fusion_retrain{,_v2,_v3,_v4}.py` + `m4_fusion_stacking.py` + `m4_fusion_v3_save_artifacts.py`（~2500 行，delong_test 复制 5 份）
- **步骤**：
  1. 新建 `scripts/lib/fusion_pipeline.py`：SEEDS / 特征划分 / 数据加载 / delong_test（唯一实现）/ 评估指标 参数化
  2. 版本差异转 CLI 参数（`--variant {v1,v2,v3,v4} --stacking`）
  3. **等价性红线**：合并前后各跑一次完整评估，F1/AUC/CI 数值 bit-exact 或差异 < 1e-9 才允许删除旧脚本
  4. SEEDS/RANDOM_STATE 收敛到 `scripts/lib/constants.py`（顺带修复 m3 的 [42,123,7] 漂移决策：确认是有意还是笔误后统一）
- **工作量**：1.5~2d

#### T10 train_physiological 三兄弟合并

- **对象**：`train_physiological_xgboost.py`(420行) vs `train_physiological_lightgbm.py`（76% 同文）
- **方案**：合并为单入口 `train_physiological.py --model {xgb,lgbm}`；evaluate_model 两份近似实现归一
- **验证**：两模型各自产出与旧脚本一致的特征重要度 top-N 和评估指标
- **工作量**：0.5d

#### T11 论文 docx 工具链 argparse 化

- **对象**：~30 个「SRC=硬编码路径 → 改段落 → OUT=新硬编码路径」同模板脚本，33 处绝对路径
- **方案**：统一改为 `--src/--out` CLI 参数 + 默认相对项目根；移入 `scripts/thesis_tools/` 子目录
- **工作量**：1d

#### T12 scripts 杂项清理

- [ ] gen_canary_traffic.py / deep_scan_zip.py v1 正式删除（DEPRECATED 头已挂一个观察周期）
- [ ] test_plan_phase1~5(+simple/final) 合并为 `--phase` 参数化验收套件（可延后）
- [ ] 12 个 verify_grafana_*.py 抽公共 grafana client 小工具库（可延后）
- **工作量**：0.5d（前两项）

---

### P5 前端收尾（独立并行，低风险）

#### T13 UserRiskPage 请求编排去重

- 自动融合流程收敛为单一刷新出口，消除一次提交触发两次 `getRiskReport` + `getRiskTrend` 的请求瀑布
- 验证：Network 面板确认提交一次仅一组请求；vitest 回归
- 工作量：0.5d

#### T14 request.ts GET 去重显式化

- 覆写 axios 实例方法的猴子补丁（request.ts:308-354）改为导出显式 `dedupedGet` 包装函数；调用方渐进切换，axios 大版本升级不再依赖原型链实现细节
- 验证：并发相同 GET 只发一次的网络层单测
- 工作量：0.5d

#### T15 i18n 语言包按域拆分

- zh-CN.ts / en-US.ts（各 ~2290 行）按 `user/counselor/admin/common` 拆子模块后聚合导出，键名不变
- 验证：i18n key 完整性对比脚本（拆分前后键集合一致）；typecheck
- 工作量：1d

#### T16 大组件瘦身（四个 500+ 行文件）

- RiskReportTab.vue / TextAssessTab.vue：图表 option 构建（如 paintReportTrend 85 行）抽 composable/纯函数模块；融合结果卡拆子组件
- 目标：四个文件均降至 500 行以内
- 验证：vitest + 手动页面走查
- 工作量：1d

#### T17 VirtualList 处置决策（二选一）

- 方案 A：接入预警列表/操作日志等长列表页（发挥既有虚拟化能力）
- 方案 B：连同测试一起删除（消除零使用死代码）
- 决策依据：是否存在真实的长列表性能痛点（>200 条渲染卡顿）
- 工作量：0.5d

#### T18 危机热线号码配置化

- UserRiskPage.vue:240-274 硬编码号码迁入 i18n 消息参数或 env 配置（安全关键常量，改动需双人复核）
- 工作量：0.25d

---

## 五、执行顺序与依赖关系

```
P0 快赢(T1-1..T1-5, 1~2d) ──► P1 结构重构(T2→T3→T4, 3~5d) ──► P2 契约与分层(T5→T6, 5~8d) ──► P3 架构级(T7, T8, 1~2w)
                                                                              ▲
P4 ML/scripts(T9~T12, 3~5d) ────────────────────────────────────────────────┘ （独立并行，T8 完成后收益最大）
P5 前端收尾(T13~T18, 2~3d) （独立并行，任意时机插入）
```

**关键依赖约束**

1. **T5 必须先于 T7**：先固化 API 契约再动 core 骨架，否则拆分期间契约漂移无法检测
2. T4 依赖 Redis 集成环境就绪
3. T2/T3/T9 属于**行为等价重构**：任何响应体/F1 数值差异即回滚
4. T9 依赖 T8 的收益最大（合并后的 lib 可直接 `from app.ml.evaluation import ...` 复用），但非硬依赖

**若时间有限只做三件事**（价值/成本比排序）：

1. **T4** — PDF 内存态 job store 是多实例部署的正确性缺陷，不只是优化
2. **T5-B1/B2** — OpenAPI 契约可用性，前端联调与自动化收益立竿见影
3. **T9** — 2500 行复制粘贴的长期维护成本最高

---

## 六、通用保障措施

1. **分支纪律**：每任务一条分支一个 PR，标题携带本计划编号（如 `refactor(T2): split model_predict_service`）
2. **验证基线命令**：

```bash
# 后端（当前绿线：1327 passed / 10 skipped）
cd backend && .venv\Scripts\python.exe -m pytest tests/api tests/services tests/unit -q --no-cov

# 前端（当前绿线：typecheck 零错误 + 60 用例）
cd frontend && npm run typecheck && npx vitest run

# lint
cd backend && .venv\Scripts\ruff.exe check app tests
```

3. **等价重构红线**：T2/T3/T9 交付物必须附"重构前后输出 diff = 空"的证据
4. **行为变更任务**（T4/T5/T6）：必须在 PR 描述列明对外可见变化清单
5. **回归环境要求**：本地 Redis（`docker run -d --name bysj-redis -p 6379:6379 redis:7-alpine`）；离线环境设置 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`
6. **回滚策略**：所有重构保留门面/shim 一个版本周期；配置开关类改动（T4 PdfJobStore）支持一键切回

---

## 七、进度跟踪总表

| 任务 | 描述 | 优先级 | 风险 | 工作量 | 状态 |
|---|---|---|---|---|---|
| ~~R1~~ | ~~metrics try/finally~~ | 高 | 低 | — | ✅ 第一轮 |
| ~~R2~~ | ~~CancelledError 重抛~~ | 高 | 低 | — | ✅ 第一轮 |
| ~~R3~~ | ~~IP 解析缓存/to_thread/count 聚合~~ | 高 | 低 | — | ✅ 第一轮 |
| ~~R4~~ | ~~死代码清除/静默异常/类型修正~~ | 中 | 低 | — | ✅ 第一轮 |
| ~~R5~~ | ~~escapeHtml/日期/console 收敛~~ | 中 | 低 | — | ✅ 第一轮 |
| ~~H-1~~ | ~~中间件栈重排 + SafeRateLimit~~ | 高 | 中 | — | ✅ 第二轮 |
| ~~M-4/M-5/M-6/M-10/L-3~~ | ~~WS 熔断/pickle 去重/租户去重/权限并集/token 去重~~ | 中 | 低 | — | ✅ 第二轮 |
| ~~AH-5~~ | ~~GDPR 352 行函数拆分~~ | 高 | 中 | — | ✅ 第二轮 |
| ~~AH-1~~ | ~~归档 N+1 集合化~~ | 高 | 中 | — | ✅ 第三轮 |
| ~~AH-2~~ | ~~内容治理 DB 端分页~~ | 高 | 中 | — | ✅ 第三轮 |
| ~~M-3/AM-14/AM-8~~ | ~~WS 超时配置化/refresh 下沉/导出去重~~ | 中 | 低 | — | ✅ 第三轮 |
| ~~T1-1~~ | ~~model_loader 懒加载~~ | 中 | 低 | 0.25d | ✅ 第四轮（既有实现核验） |
| ~~T1-2~~ | ~~bootstrap 失败计数~~ | 中 | 低 | 0.25d | ✅ 第四轮（既有实现核验） |
| ~~T1-3~~ | ~~调参缓存+剪枝~~ | 中 | 低 | 0.5d | ✅ 第四轮（既有实现核验） |
| ~~T1-4~~ | ~~业务常数收敛~~ | 中 | 低 | 0.25d | ✅ 第四轮（既有实现核验） |
| ~~T1-5~~ | ~~get_db 导入归位~~ | 低 | 低 | 0.1d | ✅ 第四轮（既有实现核验） |
| ~~T2~~ | ~~model_predict 拆分~~ | 高 | 中 | 1.5~2d | ✅ 第四轮 |
| ~~T3~~ | ~~metrics/observability 拆分~~ | 中 | 中 | 1~1.5d | ✅ 第四轮 |
| T4 | PDF 三管线收敛 | 高 | 高 | 2~3d | 🔶 P1 完成（列表统一），剩余见 T4-P2 |
| T5-B1 | auth response_model 补齐 | 高 | 中 | 0.5d | ✅ 第四轮 |
| T5-B2 | analytics_events response_model | 高 | 中 | 0.5d | ✅ 第五轮 |
| T5-B3~B4 | response_model 其余批次 | 高 | 中 | 2~3d | ⬜ |
| T6 | 事务边界统一 | 高 | 中 | 2~3d | ⬜ |
| T7 | core 包拆分 | 中 | 高 | 1~2w | ⬜ |
| ~~T8~~ | ~~backend 可安装包化~~ | 中 | 低 | 0.5d+渐进 | ✅ 第四轮 |
| T9 | m4_fusion 六合一 | 中 | 中 | 1.5~2d | ⬜ |
| T10 | physiological 三合一 | 低 | 低 | 0.5d | ⬜ |
| T11 | docx 工具链 argparse 化 | 低 | 低 | 1d | ⬜ |
| T12 | scripts 杂项清理 | 低 | 低 | 0.5d | ⬜ |
| ~~T13~~ | ~~UserRiskPage 请求去重~~ | 中 | 低 | 0.5d | ✅ 第四轮 |
| ~~T14~~ | ~~request.ts 显式化~~ | 中 | 中 | 0.5d | ✅ 第四轮（导出兼容包装器，渐进迁移） |
| T15 | i18n 拆分 | 低 | 低 | 1d | ⬜ |
| T16 | 大组件瘦身 | 低 | 低 | 1d | ⬜ |
| ~~T17~~ | ~~VirtualList 处置（方案 B：删除零使用死代码）~~ | 低 | 低 | 0.5d | ✅ 第四轮 |
| ~~T18~~ | ~~危机热线配置化~~ | 低 | 低 | 0.25d | ✅ 第四轮 |

> **维护说明**：完成任务后将状态列改为 ✅ 并附 PR 链接；若执行中发现新的审计偏差（如第二轮发现的"PYTORCH_AVAILABLE 实际被测试消费"），请回写第二节对应条目，保持本文档与仓库实况一致。
