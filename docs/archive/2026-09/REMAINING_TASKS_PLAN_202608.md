# 剩余任务详细执行计划（2026-08）

> **状态**：待执行（依据 `CODE_OPTIMIZATION_PLAN_202608.md` 第五轮完成后的剩余项重排）
> **验证基线**：后端 `pytest tests/api tests/services tests/unit --no-cov` = **1331 passed / 10 skipped**；前端 `npm run typecheck` 零错误 + vitest 全过
> **事实基线**（2026-08-26 复核，非审计快照）：
> - 缺 response_model 端点：user_content 7 / content_governance 5 / ops_dashboard 2 / gdpr 2 / uploads 1 / metrics 2 = **19 个**
> - observability 未拆分：`__init__.py` 484 行 / `aggregate.py` 443 行 / `query.py` 407 行
> - 前端超阈值组件：RiskReportTab 525 / TextAssessTab 516 / UserRiskPage 517 / CounselorUserDetailPage 507；i18n 语言包各 ~2290 行
> - scripts：m4_fusion 家族 ×6、train_physiological ×3、test_plan_phase ×8、verify_* ×16；42 个脚本含硬编码绝对路径；两个 DEPRECATED v1 脚本与 1 个散落 md 待清理

---

## 一、剩余任务全景

| 编号 | 任务 | 类型 | 风险 | 工作量 | 前置 |
|---|---|---|---|---|---|
| R-A | T5-B3/B4：19 端点 response_model 补齐 | 契约 | 中 | 2~3d | 无（有 B1/B2 范式） |
| R-B | T4-P2：PDF asyncio 路径下线 + 端点合一 | 行为变更 | 高 | 2d | Redis/Celery 集成环境 + 排期窗口 |
| R-C | T3-rem：observability 超长函数拆分 | 等价重构 | 中 | 1~1.5d | 无 |
| R-D | T6：事务边界统一 | 行为一致性 | 中高 | 2~3d | 先立 ADR |
| R-E1 | T14-rem：dedupedGet 调用方渐进迁移 | 前端 | 低 | 0.5d | 无 |
| R-E2 | T15：i18n 语言包按域拆分 | 前端 | 低 | 1d | 无 |
| R-E3 | T16：四大组件瘦身 | 前端 | 低 | 1d | 无 |
| R-F1 | T9：m4_fusion 六合一 | ML 脚本 | 中 | 1.5~2d | 无（等价红线） |
| R-F2 | T10：train_physiological 三合一 | ML 脚本 | 低 | 0.5d | 无 |
| R-F3 | T11：docx 工具链 argparse 化（42 脚本） | 脚本卫生 | 低 | 1d | 无 |
| R-F4 | T12：杂项清理（v1 删除/文档迁移/phase 合并/grafana client） | 脚本卫生 | 低 | 1d | 无 |
| R-G | T7：core 包拆分 | 架构 | 高 | 1~2w | R-A 完成后、单独分支 |

---

## 二、任务群 A：契约补齐（T5-B3/B4）

### R-A 19 端点 response_model

**现状**：`response_model=ApiResponse` 裸泛型或完全缺失，OpenAPI data 不可导航。

**批次与 Schema 设计**

| 批次 | 文件 | 端点数 | 需要的响应模型 |
|---|---|---|---|
| B3-a | user_content.py | 7 | 内容项/列表（Paginated 泛型）、收藏/反馈动作确认、详情视图 |
| B3-b | content_governance.py | 5 | 审核项列表（含 needs_review_reason 复合结构）、动作确认 |
| B4-a | ops_dashboard.py + metrics.py | 4 | 指标仪表板聚合体、指标快照 |
| B4-b | gdpr.py + uploads.py | 3 | 导出任务状态、上传结果 |

**步骤**
1. **前置设计**（半天）：`schemas/common.py` 增加
   `PaginatedData(BaseModel, Generic[T])`（items/total/page/page_size）与
   `ActionConfirm(BaseModel)`（action/target_id/status/message 通用确认体）；
   gdpr/upload 的返回若与已有模型重合则复用
2. 每批：读端点 ok() 实际返回 → 写 Schema（**全部字段先 Optional，收紧留给后续批次**）→
   端点改 `ApiResponse[具体模型]` → 复用 `test_analytics_response_contract.py` 范式
   写契约断言（注意 `T | None` 生成 anyOf 需解包）
3. 每批完成后：契约测试 + 该文件 api 测试 + OpenAPI 快照 diff（只许新增约束）
4. 收尾：grep 全仓 `response_model=ApiResponse` 裸引用清零（或登记豁免清单）

**风险与对策**：response_model 触发输出校验，历史脏数据（None 混入必填字段）会导致 500 →
字段先全 Optional + staging 观察日志一周后逐步收紧；SQLite/Postgres 双环境各跑一次

**验证**：`pytest tests/api -k "user_content or governance or ops_dashboard or gdpr or upload or metrics"` + 契约测试 + 基线
**工作量**：2~3d　**完成标准**：19 端点全部可导航；裸 ApiResponse 清零

---

## 三、任务群 B：PDF 收敛 P2（T4-P2，行为变更）

### R-B 统一到 Celery 单路径

**现状**（第五轮核实）：
- 主路径 Celery：job 状态与字节已在 Redis（`pdf:job:*` / `pdf:bytes:*`，TTL 1h）✅
- 遗留：`/user-risk/pdf/async` 进程内 asyncio 路径（`pdf_job_store` 内存态）；`/user-risk/pdf` 同步路径；
- 端点组三套：`/pdf/{job_id}/status|download`（内存）、`/pdf/celery/{job_id}/status|download`（Redis）、同步下载

**目标**
```
POST /user-risk/pdf/celery-async   → 唯一异步入口（已有，保留）
GET  /reports/pdf/{job_id}/status  → 统一状态查询（Redis 优先，内存兜底只服务于降级任务）
GET  /reports/pdf/{job_id}/download→ 统一下载（同上）
POST /user-risk/pdf                → 同步即时下载（小报告场景，保留并标注）
/async 旧路径                      → 301/兼容包装 2 个版本周期后删除
```

**步骤**
1. 状态/下载端点内部实现"Redis 查无 → 内存兜底"的读取顺序（`get_job_from_redis` + `pdf_job_store.get` 合一辅助 `_resolve_pdf_job(job_id)`）
2. `/user-risk/pdf/async` 端点主体改为调用 celery-async 的内部逻辑（派发 Celery + 失败降级线程），响应结构不变；旧客户端零感知
3. `/pdf/celery/*` 两个路由保留为别名，内部指向统一端点；OpenAPI 标记 deprecated
4. 前端 reportsApi.ts 切换统一端点；E2E 覆盖三场景（同步/队列成功/降级线程）
5. 两个版本周期后删除 `/async` 原实现与 celery 别名路由

**风险与对策**：多实例部署行为变化 → docker-compose 双副本 + 独立 worker 环境过 E2E；
Redis 故障降级策略明确为"拒绝并告警，回退线程路径仅限本进程可见"（文档写入 EMERGENCY_RUNBOOK）
**验证**：test_pdf_celery + test_reports_api_extended + 手动三场景
**工作量**：2d + 2 个版本观察期

---

## 四、任务群 C：可观测性拆分（T3-rem，等价重构）

### R-C observability 超长函数

**现状**：`aggregate.py` 4 个 `_compute_*`（102-148 行）、`query.py` 3 个（124-126 行）、
`__init__.py` `alertmanager_webhook` 166 行。

**步骤**
1. 每个超长函数按三段抽私有函数：参数解析（时间窗/过滤）→ 数据获取 → 聚合计算
2. `alertmanager_webhook` 拆：签名校验 / 告警分类映射 / 降级派发（AlertService 调用）
3. **红线**：重构前后对 `GET /api/v1/observability/*` 各抓一份 JSON 做逐字段 diff = 空；
   契约测试已有则复用，缺失则先补 snapshot 测试
**验证**：observability 相关 api 测试 + JSON diff 证据
**工作量**：1~1.5d

---

## 五、任务群 D：事务边界（T6）

### R-D 统一 commit 归属

**步骤**
1. **先立约定**：ADR 写入 docs/architecture.md——
   a) 业务 commit 只发生在 Service 层；b) OperationLog 与业务变更必须同事务；
   c) 跨聚合编排由上层服务完成，单端点 ≤1 commit
2. 按 commit 数降序迁移：silences.py(×7) → canary.py(×6) → tenant_admin.py(×4) →
   admin.py:400-418（审计与业务同事务修复）→ auth/gdpr/reports 收尾
3. 每文件迁移：把 API 层 `db.commit()` 下沉到对应 service 方法返回值后的统一出口；
   API 层保留的 OperationLog 写入改为 service 方法参数或回调
4. 专项测试：每个迁移文件补"service 中途抛异常 → 断言无部分提交"用例
**验证**：api 测试 + 新专项用例 + 基线
**工作量**：2~3d

---

## 六、任务群 E：前端收尾

### R-E1 T14-rem：dedupedGet 调用方迁移

- 现状：`dedupedGet` 包装器已提供，旧猴子补丁机制并存
- 步骤：grep 全部 `get(` 调用按域分批替换为 `dedupedGet`；迁移完成后下掉猴子补丁
  （保留一个版本周期的 deprecation 注释）；网络层单测确认并发去重语义一致
- 工作量：0.5d

### R-E2 T15：i18n 语言包拆分

- 现状：zh-CN 2296 行 / en-US 2292 行，多角色命名空间混居
- 步骤：按 `common / user / counselor / admin / error` 拆子模块（`locales/zh-CN/*.ts`），
  根文件聚合导出；**键路径不变**；补键集合一致性脚本（拆分前后 diff 必须为空）
- 验证：typecheck + i18n 完整性脚本 + 页面抽查
- 工作量：1d

### R-E3 T16：四大组件瘦身（507~525 行）

- RiskReportTab / TextAssessTab：图表 option 构建抽 `composables/useRiskReportChart.ts` 等纯函数模块
- UserRiskPage：自动融合提交编排已有 T13 收口，继续抽模板区块为子组件
- CounselorUserDetailPage：Tab 区抽子组件
- 目标：全部 ≤450 行；验证：vitest 相关用例 + typecheck + 手动走查
- 工作量：1d

---

## 七、任务群 F：scripts / ML 债务

### R-F1 T9：m4_fusion 六合一（等价红线最严）

- 对象：`m4_fusion_retrain{,_v2,_v3,_v4}.py` + `_stacking.py` + `_v3_save_artifacts.py`（~2500 行）
- 步骤：① 新建 `scripts/lib/fusion_pipeline.py`（SEEDS/特征划分/数据加载/delong_test 唯一实现/
  评估参数化，`--variant v1|v2|v3|v4 --stacking`）② 新旧各跑一次完整评估，
  **F1/AUC/CI 必须 bit-exact 或 <1e-9**，产出对比报告 ③ 通过后删旧六件
  ④ `scripts/lib/constants.py` 收敛 SEEDS/RANDOM_STATE（m3 的 [42,123,7] 漂移需先判定有意还是笔误）
- 工作量：1.5~2d

### R-F2 T10：train_physiological 三合一

- 合并 xgb/lgbm（76% 同文）为单入口 `--model {xgb,lgbm}`；evaluate_model 归一；
  验证两模型特征重要度 top-N 与指标与旧脚本一致
- 工作量：0.5d

### R-F3 T11：docx 工具链 argparse 化

- 42 个含绝对路径脚本：`--src/--out` 参数 + 默认相对项目根；统一移入 `scripts/thesis_tools/`；
  纯机械改造，每脚本改完 `python -m py_compile` 冒烟
- 工作量：1d

### R-F4 T12：杂项清理

- [ ] 删除 gen_canary_traffic.py / deep_scan_zip.py v1（DEPRECATED 头已挂一个观察周期）
- [ ] `scripts/金丝雀期间其他事情.md` 移入 docs/
- [ ] test_plan_phase1~5(+simple/final 共 8 件) 合并 `--phase` 参数化
- [ ] verify_grafana_*（3 件）抽 `scripts/lib/grafana_client.py`（16 个 verify_* 全量复用）
- 工作量：1d

---

## 八、任务群 G：架构级（T7，可选长周期）

### R-G core 包拆分

- 前置：R-A 完成后（契约固化）再动骨架；单独分支，每步独立可合入
- 目标分层：`core/`（横切件）→ `infra/`（cache/breaker/celery/otel/ws/event_bus）→
  `security/`（deps/tenant/safe_pickle/pii）→ `ml/`（model_engine）
- 步骤：import-linter 冻结现状 → 搬迁 infra → security → model_engine，
  每步 re-export shim 一个版本周期；health.py celery 导入惰性化
- 工作量：1~2w + 观察期

---

## 九、执行路线图

```
M1 契约与可见性（1~1.5w）
  R-A(B3-a user_content → B3-b governance → B4) ─┬─► R-D 事务边界（ADR → 迁移）
  R-C observability 拆分 ─────────────────────────┘
  R-E1/E2/E3 前端（任意插入）

M2 行为变更窗口（排期后 1w）
  R-B PDF 收敛 P2（需 Redis/Celery 集成环境 + E2E）
  R-F1 m4_fusion（等价红线报告）
  R-F2/F3/F4 脚本清理

M3 架构级（可选）
  R-G core 拆分（单独分支，2w）
```

**建议推进顺序**：R-E（前端快赢）→ R-A（契约，紧接 R-D）→ R-F3/F4/R-F2（脚本快赢）→
R-C → R-B（窗口）→ R-F1 → R-G

---

## 十、红线与通用保障

1. **每任务一条分支一个 PR**，标题带本计划编号（如 `refactor(R-A): response_model for user_content`）
2. **验证基线命令**：

```bash
# 后端（绿线：1331 passed / 10 skipped）
cd backend; $env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"
.venv\Scripts\python.exe -m pytest tests/api tests/services tests/unit -q --no-cov

# 前端
cd frontend; npm run typecheck; npx vitest run
```

3. **等价重构红线**（R-C/R-F1/R-F2）：附"重构前后输出 diff = 空"证据；R-F1 数值必须 bit-exact
4. **行为变更**（R-B/R-D）：PR 描述列明对外可见变化清单；R-B 需 E2E 三场景 + 双副本环境
5. **离线环境**：跑任何后端测试前设置 HF/TRANSFORMERS_OFFLINE=1（第四轮已实证不设会网络阻塞）
6. **回滚**：重构保留 shim 一个版本周期；R-B 的端点切换保留别名路由两版本后删除
7. **文档同步**：任务完成后回写本文件与 `CODE_OPTIMIZATION_PLAN_202608.md` 第七节跟踪表

---

## 十一、进度跟踪总表（起始于第五轮之后）

| 编号 | 任务 | 状态 |
|---|---|---|
| R-A | 19 端点 response_model | ✅ 第五轮（user_content 7 / governance 5 / ops_dashboard 2 / gdpr 2 / uploads 2 / metrics 1；契约测试 test_ra_response_model_contract 覆盖 19 端点） |
| R-B | PDF 收敛 P2 | ✅ 代码完成（统一 `_resolve_pdf_job` Redis→内存兜底；/pdf/{id}/status|download 统一读取；/user-risk/pdf/async 并入 `_dispatch_pdf_async`（Celery 优先降级线程）；/pdf/celery/* 别名 deprecated；前端 celery 变体切统一端点；剩余：双副本环境 E2E 三场景 + 两版本后删别名） |
| R-C | observability 拆分 | ✅ 第五轮（query/aggregate 7 个 _compute_* 拆为参数解析/数据获取/聚合三阶段；alertmanager_webhook 拆签名校验/静默分支/活跃分支；快照等价测试 test_observability_equivalence 7 项 + perf 8 项 + webhook 全过） |
| R-D | 事务边界统一 | ✅ ADR-012 已立（docs/architecture/adr/）；silences.py 迁移（update/enable 收敛单 commit）；仓库级 AST 护栏确认无"单路径多 commit"残留（canary/tenant_admin 的 commit 为端点各 1、review/warning 为 if/else 互斥分支各 1，均合规）；契约测试 test_adr012_transaction_boundaries 含护栏 + 无部分提交运行时验证 |
| R-E1 | dedupedGet 迁移 | ✅ 第五轮（14 个 API 文件全量迁移 + 17 个测试 mock 同步；猴子补丁保留一个版本周期）→ 第六轮加速收尾：实测全仓零 `.get(`/快捷方法调用方后**删除 DEDUPE_METHODS 兼容桥**（`request.request` 覆写保留为去重引擎；三处 `request.delete` 回落 axios 原生方法，DELETE 本不参与去重），typecheck/eslint 通过 |
| R-E2 | i18n 拆分 | ✅ 第五轮（zh/en 各拆 4 域文件，56 命名空间键集合一致，i18n.test 37 用例通过） |
| R-E3 | 组件瘦身 | ✅ 第五轮（RiskReportTab 431 / TextAssessTab 446 / UserRiskPage 392 / CounselorUserDetailPage 428，全部 ≤450；融合 Tab 抽 FusionAssessTab，只读 Tab 抽 UserDetailInfoTabs） |
| R-F1 | m4_fusion 六合一 | ✅ 第七轮完成：统一库 `scripts/lib/fusion_pipeline.py` 收敛全部 **5 个评估变体（v1/v2/v3/v4/stacking），逐一在真实数据（n=1275）上通过 bit-exact 等价验证**（深度比对含 fold_details 全精度浮点，忽略 5 个非确定键）；基线锚定于 `models/experiments/_rf1_baselines/`；旧五件已删除（scripts/ 本就 gitignore，纯本地资产）；`v3_save_artifacts.py` 保留为部署产物导出器，特征常量改为从 lib 导入消除漂移面。复核期修复：FIX-P0 子代理跨编辑回归（VariantConfig.strategies 移除致 v1 AttributeError→常量化）、死存储/裸 now()/导入序 21 处 lint 清理且重验证仍 bit-exact |
| R-F2 | physiological 三合一 | ⬜ |
| R-F2 | physiological 三合一 | ✅ 第五轮（合并入口 train_physiological.py --model xgb|lgbm；xgb/lgbm 训练/评估/重要性路径逐字保留，config.json 字段与旧脚本一致；旧脚本挂 DEPRECATED 待真实数据集等价验证后删除） |
| R-F3 | docx argparse | ⚠️ 部分（6 个 SRC/OUT=Path 模式脚本已转 --src/--out + 项目根相对默认，py_compile 通过；TOKEN_FILE/LOG_FILE/ZIP 等运维类硬编码不在 docx 管线范围，待后续） |
| R-F4 | 杂项清理 | ⚠️ 大部分完成（gen_canary_traffic.py / deep_scan_zip.py 已删除；金丝雀 md 已移入 docs；verify_grafana_datasource/prometheus 已抽 scripts/lib/grafana_client.py 并用 mock urlopen 冒烟验证 GET/POST/错误分支等价；test_plan_phase 8 件已收敛为 scripts/test_plan.py --phase 单入口（importlib 调度，零逻辑改动，8 模块导入验证通过）；剩余：真实 Grafana/数据集环境等价验证 + test_plan 内联合并） |
| R-G | core 拆分（可选） | ⬜ |

> 维护说明：与主计划文档 `CODE_OPTIMIZATION_PLAN_202608.md` 第七节保持互指；任一任务完成
> 后同时更新两处跟踪表。

---

## 十二、第六轮复核修复记录（混合工作区健康验证）

对第五轮大规模改动后的工作区做全量复核，发现并修复两个问题：

### FIX-P0-INTERNAL：model_loader 懒加载内部引用 NameError（真实运行时破损）

T1-1 用 PEP 562 模块级 `__getattr__` 实现路径常量懒加载——但模块级 `__getattr__`
只拦截**外部**属性访问（`from app.ml.model_loader import MODEL_PATH`）；模块内函数体的
裸名 `MODEL_PATH` 走普通 globals 字典查找，首次命中即 `NameError`（ruff F821 ×9），
五个 load 函数的默认路径分支全部不可用。

**修复**：新增 `_artifact_path(name)` 内部辅助（优先读已回写的 globals 缓存，否则调
`__getattr__` 解析），替换全部 6 处内部引用；三个 loader 运行时冒烟通过。
**教训**：PEP 562 懒常量方案落地时必须同步排查**模块内自引用点**，ruff F821 应纳入 CI 门禁。

### FIX-ORDER-3：等价快照被进程活体状态污染

`test_lock_stats_snapshot` 的 memory 段读进程级 `dedup_lock.get_stats()`——单跑为零值匹配
基线，全量下被先前 API 测试（告警去重路径）污染导致快照必现失配。

**修复**：测试内 monkeypatch `_fetch_lock_memory_stats` 注入固定零值。确定性边界收敛为
DB 派生段（historical_recent/recent_flushes 逐字段红线不受影响），生产代码不动。
**教训**：等价红线测试的数据源必须全量可重置或可注入；凡混入进程级单例状态的断言，
在孤立运行时是假绿。

### 复核结论

全量基线 **1364 passed / 10 skipped / 0 failed**（较上轮 +33：契约测试、等价快照、
事务护栏等新增用例）；前端 typecheck 零错误。混合工作区（双方未提交改动合并态）整体健康。
