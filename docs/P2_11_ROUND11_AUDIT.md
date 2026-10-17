# P2 第十一轮审计清单（#39 死代码拆分裁定 + #33/#35 第一批 + #32 矛盾裁定 + #34 分类 + #36 首批）

- 生成时间：2026-10-14（HEAD = `ac58f97`；扫描在**无变异窗口**内生成）
- 扫描器：`backend/scripts/scan_p2_11_audit.py`（AST 口径，产物 `scripts/scan_p2_11_result.json`）
- 闸门：`backend/tests/test_p2_11_round11.py`
- 保留决议登记册：`docs/RETENTION_REGISTRY.md`（本轮新建）

---

## 一、开工抽验：「已闭环」清单独立判据复核

判据一律与清单**不同源**（清单说已删 → 查文件存在性；清单引审计结论 → 去 grep 生产代码；
清单给计数 → 自己重扫并写明口径差异），且**先读审计定性再对照代码**。

| 项 | 清单说法 | 独立判据 | 实测 | 结论 |
|---|---|---|---|---|
| #39 `bertDisabled` | 有意保留 | 读 `P2_09:18/58` 定性 + grep 代码 | 定性为「保留」；代码 4 处模板 + 常量仍在 | ✅ 一致，**非漏做** |
| #39 `trainBert`/`evaluateBert` | 被上一并"保留" | 读 F-32 原文 + 定位函数体 | ~40 行在 `if (bertDisabled) return` 之后，**永不可达** | ⚠️ **保留决策覆盖过宽**，本轮拆分 |
| #39 `_flushed_buffer` | RES-P1-004 保留 | grep 全仓该编号 | 仅 10 处**引用**（含 `config.py:247`、`test_observability_service.py` TC-001~004），**无登记正文** | ⚠️ 可追溯性缺口，本轮补册 |
| #39 `BottomNav.vue` | 死组件待处置 | 全仓 import + 模板扫描 | 仅 `components.d.ts`（自动生成）+ 2 条 i18n 注释引用 | ⚠️ 确为死组件，**本轮删除** |
| #33 余量 | 62 | AST 重扫 `OperationLog(` Call 节点 | **62**（生产构造点，非 64；64 含类定义行） | ✅ 属实，口径已写明 |
| #35 候选 | 119（第九轮）/ 222（复核宽口径） | 本轮 AST 宽口径（含 `logger.warning` + `pass`） | 真降级 **242** + ImportError 特性探测 **16** = 258 | ⚠️ 三种口径判据不同，见下表 |
| #37 `roles.ts` | 15 语句收编 | grep helper 调用点 | 14 个生产文件 + 1 测试文件命中 | ✅ 属实且**被使用**（非仅存在） |
| #38 BE 棘轮 | 95 | 读 `test_p2_10_round10.py` 断言 | `assert len(got) == 95` | ✅ 属实 |
| #40 `prometheus_client` | 真解析 | grep 测试 | `test_p2_09_round9.py` 2 处引用 | ✅ 属实（`promtool` 仍无） |
| prettier | CI 不检查 | grep `.github/workflows/` | **0 命中**（`.prettierrc` 与 `format:check` 脚本存在但 workflow 不调用） | ✅ 属实 |
| 前端基线 | 102 files / 1291 passed / 4 skipped | 本地 `vitest run` 全量 | **102 files / 1292 passed / 4 skipped** | ⚠️ 差 1 条，见下 |
| 类型存量 | 42 / 45 | `npm run typecheck` 完整落盘计数 | **42 错 / 15 文件** | ✅ 属实 |

### 两处口径差异（如实记账，不合并成"一致"）

1. **前端测试数 1292 vs 1291**：本轮起点实测为 **1292**。第十轮记为 1291。
   未找到动态用例生成（`it.each` / 循环生成用例均不存在），差异来源未查清
   （不排除第十轮取样时点不同）。**本轮一律以 1292 为起点做逐位比对。**
2. **#35 候选数三口径**：119（第九轮，只数 `except→debug/continue/pass`，且限 `logger.debug`）、
   222（第十轮复核宽口径）、**242**（本轮，再含 `logger.warning` 且无 raise 的处理器）。
   三者**判据不同、不矛盾**；`ImportError` 特性探测 16 处单独分桶，**不计入降级债**。

---

## 二、#39 死代码：拆分裁定与全链路清单

### 裁定原则

「保留 UX 常量 / 禁用态」与「保留不可达函数体」是**两件事**。第九轮把二者合并保留了，
本轮拆分：**常量与禁用态保留（登记 `RES-P2-039-01`），约 40 行不可达函数体移除（F-32）**。

### 全链路清单

| 对象 | 位置 | 裁定 | 依据 |
|---|---|---|---|
| `bertDisabled = true` | `ExperimentTab.vue:302`（原 339） | **保留** | RES-P2-039-01：删了用户看到的是点了必报错的坏按钮 |
| 训练/验证按钮禁用态 + `title` | `:80-97` | **保留** | 同上，且移除 `@click` 后无处理函数，语义自洽 |
| `trainBert` / `evaluateBert` | 原 `:341`/`:362` | **移除** | `if (bertDisabled) return` 之后永不可达（F-32） |
| `applyTrainResult` / `applyEvaluateResult` | 原 `:270`/`:288` | **移除** | 仅被上面两个不可达函数调用 → 连带不可达 |
| `TrainResult` / `EvaluateResult` 类型导入 | 原 `:222` | **移除** | 连带 |
| `experimentAssess.actionTrain` / `.actionEvaluate` | i18n 双语种 `:998-999` | **移除** | 唯一消费点（label map）已删 |
| 导入/对比按钮缺 loading 守卫 | `:74`/`:98` | **补** | F-32 另一半：`:disabled="experimentLoading"` × 2 |
| `_flushed_buffer` / `consume_flushed_logs` | `observability_service.py:99/151` | **保留（补正文）** | RES-P1-004 现登记于 `docs/RETENTION_REGISTRY.md` |
| `BottomNav.vue` | `components/common/` | **删除** | 死组件：无 import 方、无模板引用、不在构建图 |

### ⚠️ 连带发现（记账，本轮不处理）

移除不可达函数体后，`lossChartData` / `accuracyChartData` / `confusionMatrix` /
`sampleRows` / `trainLogRows` / `evalLogRows` 六个 ref 变成**只声明、从不写入**的状态，
对应图表恒为空。**这与改前运行时行为完全一致**（`bertDisabled=true` 时这些函数体从未执行），
不是本轮引入的回归。是否下线这些图表属于**产品决策**，登记为第十二轮候选。

### 孤儿组件（死组件）全量扫描 —— 不止 BottomNav

用闸门同款判据（import 语句 / `<PascalCase>` / `<kebab-case>` / 字符串名引用）扫
`frontend/src/components/**/*.vue`，共 30 个组件，**9 个无任何引用方**：

| 孤儿组件 | 备注 |
|---|---|
| `components/charts/ModelPerformanceChart.vue` | 图表类，疑似被动态组件名引用但实测无 |
| `components/charts/SystemHealthChart.vue` | 同上 |
| `components/common/illustrations/EmptyAssessment.vue` | 插画类 |
| `components/common/illustrations/EmptyReport.vue` | 插画类 |
| `components/common/illustrations/EmptyUser.vue` | 插画类 |
| `components/common/illustrations/EmptyWarning.vue` | 插画类 |
| `components/common/LanguageSelector.vue` | 语言切换（LayoutHeader 可能自带实现） |
| `components/common/LazyImage.vue` | 有同名 `.test.ts`，但生产无引用 |
| `components/common/ThemeSwitcher.vue` | 主题切换 |

**处置**：本轮**只删除 BottomNav**（有明确裁定），其余 9 个**不删**（属产品决策），
改用**棘轮**锁住 `ORPHAN_BASELINE = 9` —— 新增孤儿即红，且清单必须与本文档同步。
> 判"死组件"不能用 `components.d.ts`：它由 unplugin-vue-components 对目录内**所有**
> 组件自动生成，存在与否都不证明被使用（这是第十轮 `BottomNav` 语法坏而 CI 全绿的根因）。

---

## 三、#33 第一批：`OperationLog(` → `record_audit`

- 开工实测生产构造点 **62**（AST Call 口径；`models/admin.py` 的类定义行不是调用，不计）。
- 第一批迁移 **8** 处，剩余 **54**。迁移点均**补上了原先完全缺失的 `ip_address`**。

| 文件 | 迁移处 | action | detail 形态变化 |
|---|---|---|---|
| `api/v1/silences.py` | 3 | `update_silence` / `enable_silence` / `delete_silence` | `json.dumps(dict)` → 直接传 dict（等价） |
| `api/v1/content_governance.py` | 3 | `content.review` / `.takedown` / `.restore` | 分号拼接串 → **结构化 dict**（行为变更，见下） |
| `api/v1/model_kill_switch.py` | 2 | `model.kill_switch.activate` / `.deactivate` | 裸字符串 → `{"reason": ...}` |

**行为变更（已确认无测试断言依赖）**：`content_governance` 的 `detail` 由
`"reviewer_note=…; review_cycle_days=…; …"` 改为 JSON dict。全仓检索
`content.review|content.takedown|content.restore` 在 `tests/` 下**零命中**，
改后 `tests/api/test_content_governance_api.py` 14 passed。

**剩余 54 处分布（前 12）**：`counselor_service_binding` 6、`tenant_admin` 4、
`counselor` 3、`warning_service` 3、`admin`/`alerts/__init__`/`gdpr`/`user_upload`/
`admin_service_template`/`counselor_service_consultation`/`counselor_service_group`/
`counselor_service_warning` 各 2。→ 第十二轮。

---

## 四、#35 第一批：真降级点接 `silent_degradation_total`

- 新建 SSOT：`app/core/degradation.py::record_silent_degradation(location)`
  —— 内部吞掉一切异常（metrics 不可用时绝不能反弹给被保护的主流程），
  一行调用即可接线，避免 `cache.py` 那种 5 行嵌套 try 的复制粘贴。
- 第一批接线 **8** 处（均为审查报告 §7.2 ③ 点名或同型的真实降级，非特性探测）：

| location | 文件 | 降级语义 |
|---|---|---|
| `core.ws.publish_to_user` | `core/ws.py` | Redis 发布失败 → 其它 worker 的用户收不到消息 |
| `core.ws.broadcast` | `core/ws.py` | 广播降级 |
| `core.event_bus.publish` | `core/event_bus.py` | 队列满**丢事件**，事件永久消失 |
| `core.pii_crypto.process_result_value` | `core/pii_crypto.py` | 解密失败返回 `[DECRYPTION_FAILED]` = 数据实际丢失 |
| `core.model_engine.fusion.{structured,text,physio}` | `core/model_engine/fusion.py` | 模态异常被吞 → 该模态缺席 → **融合分系统性偏低（漏预警方向）** |
| `api.metrics_helpers.collect_ml_quality` | `api/v1/metrics_helpers.py` | 模型质量指标采集失败 |
| `api.metrics_helpers.collect_drift` | 同上 | 漂移指标采集失败 |
| `api.metrics_helpers.collect_canary` | 同上 | 金丝雀指标采集失败 |

> `fusion.py` 一并补了 `logger.warning`（原实现只有 `continue`，连日志都没有），
> 并把 `isinstance(value, Exception)` 改为 `BaseException` 前保持原语义不变
> —— 注意 `asyncio.CancelledError` 在 Py3.8+ 是 `BaseException` 子类，
> `gather(return_exceptions=True)` 会把它当结果返回；此处**保持原行为**不额外处理，
> 仅计数留痕（改动取消语义属于另一议题，登记在案）。

**剩余 238 处未接线**（真降级口径），Top 5：`model_engine/predict.py` 17、
`tasks/scheduler.py` 13、`core/ws.py` 11、`model_engine/loading.py` 9、
`api/v1/validation.py` 8。→ 分批移第十二轮。

### 后续批次追加登记（棘轮为 `>=` 式，只补表不改数）

| location | 文件 | 降级语义 | 批次 |
|---|---|---|---|
| `api.model_predict.predict.review_task_schedule_failed` | `api/v1/model_predict/predict.py` | 复核任务 fire-and-forget 创建失败 | 第十二轮第三批 |
| `api.model_predict.predict.crisis_record_failed` | 同上 | 危机事件落库失败（最高危静默丢失） | 第十二轮第三批 |
| `api.reports.pdf_job.redis_fallback` | `api/v1/reports.py` | 任务存储从 Redis 降级进程内存（跨实例不可见） | 第十二轮第三批 |
| `api.reports.pdf_jobs.merge_failed` | 同上 | 列表合并失败 = 静默少数据 | 第十二轮第三批 |
| `services.risk_service_assessment.structured_predict_fallback` | `services/risk_service_assessment.py` | 模型不可用 → 启发式打分（风险分是干预触发依据） | 第十二轮第六批 |
| `services.drift_monitoring_service.resolve_canary_version_failed` | `services/drift_monitoring_service.py` | 版本解析失败 → 该漂移告警退出自动回滚闭环 | 第十二轮第六批 |
| `services.shadow_comparison_service.commit_shadow_stats_failed` | `services/shadow_comparison_service.py` | 对拍统计落盘失败 → 激活校验缺依据 | 第十二轮第六批 |
| `api.validation.job_store.create.redis_fallback` | `api/v1/validation.py` | 写路径降级到内存 → 多实例下任务查不到 | 第十二轮第六批 |

> 第十二轮第六批实测接线总数 **20**（`record_silent_degradation(` 调用点，含
> `fusion.py` 的动态 location 一处），棘轮 `BASELINE = 8` 为下限，无需改数。

---

## 四·二、#36 `useListQuery()` 首批（3/12 页）

### 三要素缺失矩阵（开工扫描）

判据：`loading` ref 存在？独立 `error` ref 存在？有竞态守卫（序号/AbortController）？
筛选变化后是否重置页码？（`components.d.ts` 不算引用；`useListQueryState` 只管 URL 持久化，
**不管**时序与三态，两者分工不同、可叠加。）

| 页面 | loading | 独立 error | 竞态守卫 | 页码重置 | 本轮 |
|---|---|---|---|---|---|
| `admin/AdminAuditLogsPage.vue` | Y | Y(`pageError`) | ❌ | 手抄（有） | ✅ 已迁移 |
| `admin/AdminOperationLogsPage.vue` | Y | Y | ❌ | 手抄（有） | ✅ 已迁移 |
| `counselor/CounselorUsersPage.vue` | Y | Y | ❌ | 手抄（有） | ✅ 已迁移 |
| `admin/AdminAlertsPage.vue` | Y | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminCrisisEventsPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminSilencesPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminTemplatesPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `counselor/CounselorReviewListPage.vue` | Y | ❌ | ❌ | Y | 第十二轮 |
| `counselor/CounselorWarningsPage.vue` | ❌ | ❌ | ❌ | ❌ | 第十二轮 |
| `user/UserAssessmentsPage.vue` | Y | ❌ | ❌ | ❌ | 第十二轮 |
| `user/UserWarningsPage.vue` | Y | ❌ | ❌ | ❌ | 第十二轮 |
| `admin/AdminMonitoringPage.vue` 等其余 | — | — | — | — | 待扫 |

**12 页中 11 页无竞态守卫、8 页无独立错误态** —— 与审查报告「约 700 行重复」的描述一致。

### composable 本体

`frontend/src/composables/useListQuery.ts`：

- **竞态守卫**：单调序号 `seq`，每次 `run()` 取 token；响应回来 `token !== seq` 即丢弃
  （不写 rows、不改 loading、不触发 `onSuccess`）。`search()` 额外先 `seq += 1`，
  覆盖「`await setPage` 窗口内旧响应返回」这一段。
- **页码重置**：`search()` 统一 `setPage(1)` 后再拉，不再靠各页手抄。
- **三态**：`loading` / `error` / `empty`；`empty` 严格定义为「已成功加载过 + 当前 0 条 +
  无错误」，与「从未加载」区分开（这是 P1-15 空 catch 类问题的同型防线）。
- 不接管参数组装（各页筛选形态差异大），`onError` 返回文案以保留页面侧 i18n。

闸门 `src/composables/useListQuery.test.ts`（10 条）。回退实验 **E11/E12/E13** 逐项验证：
删守卫 → 4 红；删 `search()` 的作废窗口 → 1 红（**首轮 E12 曾为假闸门，已补用例**，见第六节）；
`empty` 退化 → 2 红。

---

## 四·三、类型存量收敛：42 → 0（BASELINE 45 → 0）

| 类别 | 数量 | 处置 |
|---|---|---|
| `DefaultRow` 不可赋值给页面行类型（TS2345） | 33 | 新建 `utils/tableRow.ts::asRow<T>()` 在插槽边界统一收窄（**避免各页各写一份 `as Xxx`** = 根因②） |
| `emit` 重载只匹配最后一个（TS2769） | 7 | 三处组件改 Vue 3.3+ 元组式 emits 声明；另外 3 处根因其实是 `row` 未收窄，一并 `asRow` |
| `PageTable` 的 `:data`（TS2322） | 1 | 组件边界收窄 `data as Record<string, unknown>[]` |
| `UserRiskPage` 融合参数（TS2322） | 1 | `features`/`physiological` 按 API 契约收窄为标量 map |

- 命令一律 `npm run typecheck`（= `vue-tsc --noEmit -p tsconfig.app.json`）；
  **禁裸 `vue-tsc --noEmit`**（根配置 `files: []`，只查 `env.d.ts`，历轮"0 error"是假读数）。
- 门禁自证：造 `src/__probe_typeerror.ts`（`const probe: number = 'x'`）→
  `vue-tsc-baseline.mjs`（BASELINE=0）**exit 1**；删除后 exit 0。
- ⚠️ 本机 `npm run typecheck:baseline`（spawn 模式）报 `EBUSY` 起不了 vue-tsc
  → 用脚本头部注释里的 **stdin 模式**跑通，结论一致。**CI 上是 spawn 模式，不受影响。**

---

## 五、#34 错误方言：分类审计（本轮**只分类**，不落地改造）

扫描口径：`ast.Raise` + `Call`，按异常构造名分桶（生产代码 `backend/app/**`）。

```
HTTPException=248
other_raise=334
ServiceError=0
```
（细口径见 `scripts/scan_p2_11_result.json`：`builtin_ValueError` 228、
`custom_or_other` 69、`bare_re_raise` 48、`builtin_RuntimeError` 26、
`builtin_AttributeError` 6、`raise_name_only` 6、`builtin_TypeError` 4、`builtin_KeyError` 1）

- **`ServiceError` 全仓 0 处** —— #34 的方言本体尚未建立，本轮只审计。
- **疑似 detail 泄漏内部信息 28 处**（判据：`detail=` 实参含 `str(e)`/`exc`/`sql`/`token`/`secret`/`path`/`debug` 等特征词）。典型：
  - `api/v1/review.py:226/254/282` —— `detail=str(e)`，**原始异常消息直接出网**（最高危一类）
  - `api/v1/alerts/__init__.py:93/104/108`、`api/v1/metrics.py:58/64/67` —— 配置名/凭证状态字面量
- **第一批建议（第十二轮）**：先收 `detail=str(e)` 这一类（把内部异常文本换成固定
  客户端文案 + `internal_detail` 入日志），再上中间件末道脱敏；
  中间件必须有「原始内部信息进、通用文案出」的**前后对照测试**，不能只断言中间件存在。

> 分类计数已写入闸门 `TestP234RaiseClassificationSynced`：源码一改，本表必须同步，
> 否则闸门红（#38 范式）。

---

## 六、#32 矛盾裁定

见 `docs/P2_09_ROUND9_AUDIT.md` 的**追加更正**段（不修改原文）：

- **模型元数据**：第九轮「无第二定义处、不建 SSOT」**失实**（只扫 `model_version`）。
  实测定义处 **4 个**：`MODEL_PATHS`、`MODEL_REGISTRY`、`MODEL_COMPATIBILITY_REGISTRY`、
  `ModelRegistryV2`（+ JSON）。审查原文「3 份」也偏保守。裁定：**只裁定不合并**
  （合并是业务决策），用事实锁固定现状。
- **风险等级**：`risk.py` 返回 `medium`（契约输出） vs `risk_thresholds.py` 用
  `mild/moderate`（阈值键）—— 两套语义，与审查原文吻合，同为业务决策，不合并。
- **文件名清洗**（`_sanitize_filename` × 2 + `_safe_export_filename`）：维持第九轮
  「3 实现语义不等价、不合并」的**豁免**，措辞更正为「**审计豁免**」而非「已闭环」
  （`admin.py:42` 与 `user_risk.py:24` 仍两份同名重复）。

### 豁免表（本轮沿用，不得推翻；有异议用追加更正）

沿用 `P2_10_ROUND10_AUDIT.md`：`require_role` 参数 / `target_type` / dict 响应键 /
类型声明 / 路由 path / `.label()` 别名。本轮新增两条豁免登记：

| 豁免 | 理由 |
|---|---|
| 9 个孤儿组件不删 | 属产品决策（可能有意保留备用），用棘轮防新增，不逐个删除 |
| 其余 238 处静默降级点不接线 | 分批原则，本轮只做第一批 8 处；已登记 Top-5 文件供下轮 |

---

## 七、本轮改动文件一览

**后端**：`app/core/degradation.py`（新）、`app/core/audit.py`（未改，SSOT）、
`app/api/v1/silences.py`、`app/api/v1/content_governance.py`、
`app/api/v1/model_kill_switch.py`、`app/core/ws.py`、`app/core/event_bus.py`、
`app/core/pii_crypto.py`、`app/core/model_engine/fusion.py`、
`app/api/v1/metrics_helpers.py`、`app/services/observability_service.py`。

**前端**：`views/user/components/ExperimentTab.vue`、`components.d.ts`、
`i18n/locales/{zh-CN,en-US}/user.ts`，删除 `components/common/BottomNav.vue`。

**文档**：`docs/RETENTION_REGISTRY.md`（新）、`docs/P2_11_ROUND11_AUDIT.md`（本文件）、
`docs/P2_09_ROUND9_AUDIT.md`（两段**追加更正**）、`docs/CODE_REVIEW_2026-10-11.md`
（追加「第十一轮」小节）。

## 八、CI 事故：`backend-coverage` 红（6 failed / 6730 passed）—— 本轮修复

**现象**：`eba00f8` / `f0cd16b` 推送后 `backend-coverage` failure，
`gh run view --log-failed` 取证：

    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_physio_high_risk_boost
    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_physio_low_risk
    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_missing_text
    FAILED tests/api/test_fusion_enhanced.py::TestFusionEnhanced::test_fusion_intervention_linked_to_dominant_modality
    FAILED tests/api/test_model_predict.py::TestModelPredict::test_fusion_with_physiological_high_risk
    FAILED tests/api/test_model_predict_v116.py::TestFusionPredictionV116::test_fusion_review_triggers
    6 failed, 6730 passed, 68 skipped, 278 deselected

    根因（日志原文）：
    NameError: name 'logger' is not defined   ← app/core/model_engine/fusion.py:79
    ERROR | app.api.v1.model_predict._common | 融合预测失败: name 'logger' is not defined

**根因**：`fusion.py` 原本**没有 `logger`**（该文件从未定义）。本轮 #35 给它加了
`logger.warning(...)`，我本地只跑了 `py_compile` —— **`py_compile` 只查语法、不查名字绑定**，
所以模块 import 成功、CI 跑到运行时才 `NameError`。这是"验证工具的失效伪装成修复有效"的
又一形态：语法通过 ≠ 名字有定义。

**修复**：`fusion.py` 补 `import logging` + `logger = logging.getLogger(__name__)`。
本地复跑 CI 失败的那 3 个文件 → **34 passed**。

**新闸门（`test_p2_11_round11.py::TestModuleLevelNamesDefined`）**：按作用域链解析每个
`Name(ctx=Load)` 是否可解析（模块级 + 各函数/类/lambda/推导式作用域 + 函数参数 +
函数内延迟 import + for/with/except 绑定 + global/nonlocal + builtins）。
**覆盖本轮改动的 11 个后端文件**，抓的正是"模块 import 不报错、运行期 NameError"这个形态。

**闸门变异验证（2/2 红，恢复绿）**：
| 变异 | 结果 |
|---|---|
| 删掉 `ws.py` 的 `record_silent_degradation` import | 红：报 `core/ws.py:199/223 record_silent_degradation` |
| `fusion.py` 的 `logger` 定义改名 | 红：报 `core/model_engine/fusion.py:79 logger`（**正是本轮 CI 事故的形态**） |

**教训固化**：给一个**原本没有 logger 的文件**加日志调用时，`py_compile`/esbuild 这类
"只查语法"的校验一律不够；必须要么 import 该模块跑一次（模块级 import 就会暴露
NameError 之外的更多问题，但 import 成功仍不保证函数体能跑），要么用本闸门做静态
作用域检查。已写入 CODE_REVIEW「新坑」节。

---

提示词建议"独立提交做 prettier `--write`"。本轮实测后**决定不做**，理由三条（均可复现）：

1. **规模**：`prettier --list-different` 在 `src/**` + `scripts/**` 范围内报
   **不一致文件 437 个**（更大范围同样失败）。一次 `--write` 会重排 437 个文件的格式，
   diff 与整改提交完全混在一起时无法逐文件验证；若独立成一次提交，回退它必须全量重跑
   103 个测试文件，收益/成本不成立。
2. **prettier 自身 parser 有存量语法错**：`--check` 对 `AdminMonitoringPage.vue`
   （HEAD 即报，148:11 `Unexpected closing tag "template"`）、`SilencesTable.vue`、
   `TrainingRegistryCard.vue` 报 SyntaxError。**已用 `git show HEAD:<file>` 对照证实是存量**
   （HEAD 版本在同一位置同样报错，非本轮引入），`--write` 在这些文件上会失败/跳过
   ⇒ 即便全仓 `--write` 也拿不到"全仓一致"的终态。
3. **CI 不检查**（`.github/workflows/` 对 `prettier` / `format:check` 零命中），非阻塞。

⇒ **结论**：prettier 维持第九轮/第十轮的"存量问题"定性，不排入本轮。
若要治理，正确路径是**先修 prettier parser 报错的 3 个 `.vue`**（属前端模板写法问题，
与本轮类型收敛同源），再按目录分批 `--write`（每批独立跑一次前端全量）。
已登记为第十二轮候选。

---

## 附：第十二轮同步（追加，不改上文历史快照）

- 2026-10-14，第十二轮 #34 全量收敛后重扫（同口径 ast.Raise + Call）：

    HTTPException=215
    other_raise=335
    ServiceError=33

- 变化解释：HTTPException 248→215（-33 = 第一批 30 + 第二批 admin/counselor 3 处改 ServiceError）；ServiceError 0→33；other_raise 334→335（+1 来自 ServiceError.__init__ 内的 sentinel TypeError，即必填 tenant_id 漏传检测本身）。
- 上文“五、#34 分类”节的 248/334/0 是第十一轮快照，保持不动；TestP234RaiseClassificationSynced 按本附录新 token 同步。

- 2026-10-14（第二批补遗）：gdpr.py 4 处 msg 中转泄漏改 ServiceError 后重扫：

    HTTPException=211
    other_raise=335
    ServiceError=37

  变化解释：HTTPException 215→211（-4）、ServiceError 33→37（+4），other_raise 不变（本次只换构造名，未增删 raise 语句）。

- 2026-10-14（第二批补遗）：#35 新增接线 3 处：

    core.model_engine.loading.preload.missing_file
    core.model_engine.loading.preload.failed
    core.model_engine.loading.adapter.pkl_fallback

- 2026-10-15（第十二轮第五批补遗）：#35 新增接线 4 处（此前漏登记，本批收口）：

    services.risk_service_assessment.structured_predict_fallback
    services.drift_monitoring_service.resolve_canary_version_failed
    services.shadow_comparison_service.commit_shadow_stats_failed
    api.validation.job_store.create.redis_fallback

- 2026-10-15（第十二轮第六批）：#35 新增接线 6 处 + **候选清单逐条裁定归零**：

    core.model_engine.predict.text_ml_all_unavailable
    core.model_engine.predict.physiological_model_not_found
    core.model_engine.predict.physiological_prediction_failed
    tasks.scheduler.upload_reference_query_failed
    tasks.pdf_report.save_pdf_bytes_failed
    api.model_predict._common.assessment_save_schedule_failed

  裁定工具与桶计数（W27/P16/S36/D22/C7/H6/K11/R4/M6/G8/V2/F2/X187，共 334）
  见 `tests/tools/scan_p2_35_batch6.py` + `classify_p2_35_batch6.py`
  （产物 JSON 同目录）；桶计数由 `test_p2_11_round11.py::
  TestP235SilentDegradationRatchet::test_batch6_bucket_counts_pinned` 钉死。
  X 桶 187 条为「真降级留档」（后续批待接），全量清单见 JSON 产物。
  #35 收尾口径变化：扫描器日志级由 debug/warning 扩至全级，故候选总数
  318 > 第十一轮 243（差异已记账，判据不同不矛盾）。

- 2026-10-15（第十三轮第一批）：#35 X 桶接线 7 处（X 187→180，W 27→34，
  调用点 26→33，扫描器+分类器复跑实测，总数 334 不变）：

    api.validation.job_store.get.redis_fallback
    api.validation.job_store.update.redis_fallback
    api.validation.job_store.delete.redis_fallback
    api.validation.job_store.list_jobs.redis_fallback
    api.validation.job_store.count.redis_fallback
    core.cache.redis_client_init_failed
    core.cache.redis_pubsub_client_init_failed

  裁定说明：读路径 5 处为 Redis→内存降级（任务不存在/状态冻结/计数偏小的
  假象直接呈现给用户，写路径 create 已在第十二轮第五批接线，同型补全）；
  cache 2 处为客户端初始化失败（根因性降级，全仓缓存消费者随后静默退回
  内存层，各消费点只看到"没有客户端"而不知根因）。
  本批跳过 2 条并记账（仍留 X 桶，机器不裁、由文档裁）：
  `api.validation.job_store._get_redis`（line 88，生产不可达——共享
  `get_redis_client` 内部已吞 `from_url` 失败返回 None，接线即死代码）、
  `core.cache._get_redis_url` 内层 except（metrics 自报失败的兜底，
  外层 handler 已直调 inc 完成接线，属提示词规定的跳过类目）。
  桶计数由 `TestP235SilentDegradationRatchet::test_batch6_bucket_counts_pinned`
  同步改钉（W=34/X=180）；新增 `TestP235Round13Batch1Wiring`
  （存在性 location 双向核对 + 运行时计数器 +1 行为断言）。
  详见 `P2_13_ROUND13_AUDIT.md`。

- 2026-10-15（第十三轮第二批）：#35 X 桶接线 6 处（X 180→174，W 34→40，
  调用点 33→39，扫描器+分类器复跑实测，总数 334 不变）：

    core.model_engine.predict.experimental_v121_scaler_fallback
    core.model_engine.predict.shadow_predict_trigger_failed
    core.model_engine.predict.physiological_cleaner_fallback
    core.model_engine.predict.shap_factors_fallback
    core.model_engine.predict.shap_factors_array_fallback
    services.auto_rollback_service.rollback_savepoint_failed

  裁定说明：predict 5 处——scaler 失败→未缩放特征算分（对照数据失真无标识）、
  影子触发丢失（fire-and-forget，对拍覆盖率静默归零）、cleaner 统计量缺失→
  原始输入进模型（姊妹路径 predict_lite 同型失败有 `_incr_fallback` 计数、
  本路径此前零计数）、SHAP 失败→简单特征重要性（dict/array 两路径，用户看到的
  "特征贡献"实为 |特征值|）；auto_rollback 1 处——回滚 savepoint 失败后
  results 追加的仍是 should_rollback=True 的原始结果，坏金丝雀继续生产服务。
  本批跳过 11 条并记账（仍留 X 桶，机器不裁、文档裁）：predict 的
  v121/v123 实验路径 2 处（响应置 None，显式不可见）、adapter miss
  （`_incr_counter`→`get_metrics_snapshot()` 的 adapter.miss_count，
  经 /api/v1/metrics 与 monitoring 暴露）、lite 校准 2 处（响应
  `probability_calibrated=False` 且阈值选择已分支）；auto_rollback 6 处——
  5 处已有专用计数器 `canary_rollback_check_lock_total{outcome}`
  （`_bump_lock_counter`，分类器 M 规则不认它故落入 X）、check_error
  分支（结果里显式 `reason="check_error"`）。
  桶计数同步改钉（W=40/X=174）；新增 `TestP235Round13Batch2Wiring`
  （存在性双向核对 + 影子触发/回滚 savepoint 两个运行时计数器断言）。

- 2026-10-15（第十三轮第三批）：#35 X 桶接线 5 处（X 174→169，W 40→45，
  调用点 39→44，扫描器+分类器复跑实测，总数 334 不变）——`tasks/pdf_report.py`
  任务侧 Redis 存取点（第六批只接了写入侧 `save_pdf_bytes_failed`）：

    tasks.pdf_report.save_job_to_redis_failed
    tasks.pdf_report.get_job_from_redis_failed
    tasks.pdf_report.list_jobs_from_redis_failed
    tasks.pdf_report.get_pdf_bytes_failed
    tasks.pdf_report.websocket_progress_notify_failed

  裁定说明：任务状态写失败→用户轮询查不到任务；读失败返回 None 与「任务不存在」
  不可区分（假阴性）；列表读失败返回 []→报告列表页凭空变空（部分数据）；
  字节读失败→下载接口拿不到报告；进度推送 fire-and-forget 丢失→进度条永远卡住
  （保持 debug 日志级别不变，靠计数提供可观测性）。
  本批跳过 1 条并记账：`delete_pdf_bytes_from_redis`（C 型清理路径，删失败
  只留残留字节由 TTL 兜底，不影响业务语义）。
  桶计数同步改钉（W=45/X=169）；新增 `TestP235Round13Batch3Wiring`
  （存在性双向核对 + 一次运行时覆盖四个同步存取点的计数器 +1）。

- 2026-10-15（第十三轮第四批）：#35 X 桶接线 6 处（X 169→163，W 45→51，
  调用点 44→50，扫描器+分类器复跑实测，总数 334 不变）——
  `api/v1/silences.py` 向 AlertManager 的 fire-and-forget 同步
  （失败只记 error 日志，本地照常提交、接口照样 200）：

    api.silences.create.am_sync_failed
    api.silences.create.am_rollback_failed
    api.silences.update.am_delete_failed
    api.silences.update.am_push_failed
    api.silences.enable.am_push_failed
    api.silences.delete.am_sync_failed

  裁定说明：前四条属「静默不生效」（AM 没有这条规则，告警照常推送/通知，
  管理员却以为已静默）；`create.am_rollback_failed` / `update.am_delete_failed`
  / `delete.am_sync_failed` 属**漏预警方向**（AM 侧孤儿/残留静默继续抑制告警，
  其中 update 那条还把 am_silence_id 照样清空，导致再也无法补偿删除）。

  **本批另裁定两簇「0 接线、全部记账跳过」**（仍留 X 桶，文档裁）：
  - `tasks/scheduler.py` 7 条：3 条是 `Sentry capture_message/capture_exception
    自身失败`（提示词明令跳过的类目）；4 条是清理任务 OSError
    （uploads 文件 unlink / 空目录 rmdir、artifacts stat / rmtree）——
    **F 型保守清理**：失败条目本轮跳过、下轮定时任务按同一 cutoff 重试，
    无不可恢复后果（其中 1001 连日志都没有，但后果仅"空目录残留"）。
  - `monitoring/dedup_lock.py` 6 条：2 条 `try_acquire_lock` 的 Redis 不可用
    已有 `_stats["fallback"]` 并由 `flush_lock_stats` 落 OperationLog
    （`dedup_lock_stats`，M 型）；2 条 `release_lock` 仅用于测试/主动清理，
    锁 TTL 5 分钟自动过期兜底（C 型）；1 条 `flush_lock_stats` 是指标/审计
    上报自身失败（S 型）；1 条 `_get_redis_url` 回退环境变量属设计内回退。

  桶计数同步改钉（W=51/X=163）；新增 `TestP235Round13Batch4Wiring`
  （6 对存在性双向核对 + create 端点端到端：patch AM 推送抛异常后接口
  仍返回 200 且计数器 +1）。

- 2026-10-15（第十三轮第四批**修正**）：上条 6 处接线经调用链复核后**只保留 1 处**，
  另 5 处改判 M/V 型移回 X 桶（桶计数回调为 **W=46/X=168**）。复核结论：

  `app/monitoring/am_sync.py` 的 `push_silence` / `delete_silence` 各自
  `except Exception` 捕获 HTTP/连接异常并转成返回值，随后 `_write_sync_log`
  在调用点传了 `db` 的情况下写 `am_sync_failed` OperationLog（含 error 全文）。
  ⇒ silences 侧那 5 处 except 只在「am_sync 调用本身抛异常」的罕见边缘路径才会
  触发，计数器长期为 0，**反而误导运维以为同步健康**。改判移除并留注释说明，防
  后人顺手补回。改判的 5 处：

    api.silences.create.am_sync_failed
    api.silences.update.am_delete_failed
    api.silences.update.am_push_failed
    api.silences.enable.am_push_failed
    api.silences.delete.am_sync_failed

  保留接线 1 处（唯一无 OperationLog 落点者）：

    api.silences.create.am_rollback_failed

  （commit 失败后的补偿删除用 `db=None` 调用 am_sync，`_write_sync_log` 在
  db=None 时直接 return ⇒ 无审计落点；失败后 AM 侧留下孤儿静默，本地规则已回滚
  而 AM 仍按它抑制告警 = 漏预警。）

  闸门改造：`TestP235Round13Batch4Wiring` 的 PAIRS 收为 1 对，新增
  `test_reclassified_five_have_no_counter` **反向钉**（这 5 处不得再出现通用计数器
  接线）；端到端行为断言改为**直接调端点函数 + 假 session**（测试环境
  `get_db` override 把 `session.commit` 绑成实例属性 `= flush`，类级 patch 拦不住，
  走 HTTP 无法让 commit 失败——首版就是这么写成"假绿"的）。变异 3/3
  RED-OK/GREEN-OK（N1 删接线 / N2 把改判处加回来 / N3 删文档登记行），
  日志 `mutate_p2_35_round13_batch4_fix_result.log`。

- 2026-10-15（第十三轮第五批）：#35 X 桶接线 5 处（X 168→163，W 46→51，
  调用点 45→50，扫描器+分类器复跑实测，总数 334 不变）——
  `app/tasks/model_training.py`（Celery worker 侧，与第三批 `tasks/pdf_report`
  同族；**调用链已按第四批教训逐个追过**：四处是叶子级 Redis 调用，
  `register_training_artifact` → `registry.register_model` 亦不吞异常）：

    tasks.model_training.save_job_to_redis_failed
    tasks.model_training.get_job_from_redis_failed
    tasks.model_training.list_jobs_from_redis_failed
    tasks.model_training.update_job_in_redis_failed
    tasks.model_training.artifact_register_failed
    tasks.model_training.artifact_dir_missing

  裁定说明：任务状态写失败→轮询查不到；读失败 None 与"任务不存在"不可区分
  （假阴性）；列表读失败 []→训练任务列表凭空变空；状态更新丢失→进度停在旧值、
  完成状态永不出现；**产物注册失败 = 本批最高价值**——产物已落盘但注册表里没有它，
  该模型无法被激活上线，这次训练等于白跑。另有一条**非 except 路径**：
  `_register_training_artifact` 在产物目录不存在时 `logger.warning` + **提前 return**
  （连 exception handler 都进不去），训练状态已是 completed 而注册表永远没有该模型
  ⇒ 单独接 `artifact_dir_missing`。它不在 X 桶候选里（扫描器只看 except handler），
  是本批顺带发现的漏网路径。

  **本批同时新增一条全仓闸门** `TestP235WiringIsNotDeadCode`：接线语句不得位于
  except handler 内 `return`/`raise` 之后（脚本按"logger 块 + return"做锚点插入时，
  两处接线被插到 `return None`/`return []` 之后——语法合法、py_compile 通过、
  字面量断言也过，但运行时永远执行不到，与第四批 am_sync 同族的假接线）。
  读源码用 `utf-8-sig`（`app/api/v1/__init__.py` 带 BOM）。

- 2026-10-15（第十三轮结案）：`tenant_admin` 4 处**迁移已在第十二轮第六批
  `a9926a1` 完成**（第十三轮提示词该项为 stale，实测结账不改码）：
  4 处 `record_audit` 的 `tenant_id` 实参为 `tenant.id`/`tenant_id`（目标租户，
  非 `current_user.tenant_id`），归属对应关系见 `P2_12_ROUND12_AUDIT.md` §6.3，
  闸门 `test_p2_12_round12.py::TestTargetTenantAttribution`（源码+运行时双钉）
  本轮 121 passed 全绿。第十一轮正文「剩余 54 处分布」中的 `tenant_admin` 4
  为历史快照，按「只追加不改」原则在此结案，不回改上文。

- 2026-10-15（第十三轮第六批）：#35 X 桶接线 4 处（X 163→159，W 51→55，
  调用点 50→54，扫描器+分类器复跑实测，总数 334 不变），**三文件跨层**
  （任务侧快照 + 请求侧 webhook + 观测侧统计）：

    services.model_predict.training_jobs.load_failed
    services.model_predict.training_jobs.save_failed
    api.alerts.webhook.final_commit_failed
    services.observability.aggregate.lock_stats_unavailable

  裁定说明：`training_jobs` 两处——启动快照读失败→`TRAINING_JOBS` 为空，重启后
  所有训练任务在管理端"不存在"（用户以为任务从没跑过）；快照写失败→任务状态只在
  进程内存，重启即丢（用户可见的任务历史凭空清空）。`alerts.webhook` 末尾 commit
  失败→本请求逐条 savepoint 落库的告警随这次 commit 一起回滚，但响应仍是 200 且
  `failed=0`（逐条计数统计不到 commit）——**响应与数据结构双双说谎**，告警审计整批
  丢失。`observability.aggregate` 读 `dedup_lock` 统计失败时回填四个 0，观测页当作
  真实数据展示——**假数据比缺数据更危险**（运维据此判断去重是否正常）。

  同簇 **8 条书面记账跳过**（仍留 X 桶，文档裁）：`training_jobs` 的 get/list/update
  三处失败其实落在第五批刚接线的被调方（`tasks.model_training.*`）或已有
  `storage_degraded` 可见标志；`alerts` 的 detail 解析退化是脏数据且有 warning；
  `model_registry_v2` 的 promote 失败以 None 上抛（调用方可见）、quarantine 失败属
  嵌套清理；`model_engine/inference` 的 persist 失败下轮自愈（R 型）、Prometheus
  上报失败属 S 型（自报失败）。

  闸门 `TestP235Round13Batch6Wiring`（3 条）：4 对 location 双向核对（源码+文档）+
  三处运行时覆盖（`training_jobs` 两处用其可注入的 loader/dumper 触发、`aggregate`
  patch `dedup_lock.get_stats` 触发并验证回填的是全 0 假数据）。`alerts` 的 commit
  失败**未做运行时断言**——它在 FastAPI 端点内，测试环境 `get_db` override 把
  `session.commit` 绑成实例属性（第十二轮第四批同类），无法在不伪造整套依赖注入的
  前提下触发，故只由存在性断言守住并在此记账。

  桶计数改钉：**W=55 / X=159**（总数 334 不变）。变异 M1 删 `training_jobs` 一处
  接线→双向断言 + 运行时断言双红；M2 删 `aggregate` 接线→红；M3 删本附录登记行→
  `test_locations_wired_in_code_and_doc` 红。均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch6_result.log`。
  配套工具：`tests/tools/watch_ci.py` 增 `cancelled` 识别（本仓 workflow 带
  concurrency cancel-in-progress，被后续 push 取代的 job 是 cancelled 而非 failure，
  不再误判为 CI 失败）。

- 2026-10-15（第十三轮第七批）：#35 X 桶接线 2 处（X 159→157，W 55→57，
  调用点 54→56），单文件 `app/core/model_engine/loading.py`：

    core.model_engine.loading.audit_path_resolve_failed
    core.model_engine.loading.keras_compat_load_failed

  裁定说明：`audit_model_integrity_anchors` 里某模型路径解析失败 → 该模型被
  `skipped`，不仅不进 `missing` 清单，调用方（preload）还**丢弃整个 summary
  返回值**，于是它静默逃过完整性审计（锚点是否存在从此无人再问）。
  `_load_model` 的 Keras 兼容重载（quantization_config 兼容路径）二次加载失败
  → 本函数直接 `return None`，调用方按"没有这个模型"走 fallback（分数通道彻底
  缺席，却和"从未配置"无法区分）。

  同簇 **6 条书面记账跳过**（仍留 X 桶，文档裁）：82（侧车不可读）与 425
  （adapter 加载失败）均已被调用方 `_incr_model_fallback` 计数（**M 型**，且
  侧车来源区分 `unreadable`/`absent`）；284（PermissionError）/290（OSError）是
  `preload` 的 **critical 日志**（loud，与既有接线口径缺 `missing_file`/`failed`
  的 warning 级相对）；588 是本地无缓存→Hub 下载的**设计内回退**；704 是
  sklearn 兼容补丁的 **best-effort**（失败后下游 transform 可见）。

  闸门 `TestP235Round13Batch7Wiring`（3 条）：2 对 location 双向核对 + 两处运行时
  覆盖（patch 使用方命名空间 `ld.resolve_model_path` 触发审计路径失败；
  真调 `_load_model` 的 .keras 分支，注入假 `tensorflow`/`keras` 模块使兼容重载
  抛异常）。**patch 踩坑**：`loading.py` 用 `from ... import resolve_model_path`，
  必须 patch 使用方命名空间 `ld`，patch 定义方 `model_registry` 对它不可见（首版
  因此假绿）。桶计数改钉 **W=57 / X=157**。变异 M1 删 audit 接线 / M2 删 keras
  接线 / M3 删登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch7_result.log`。

- 2026-10-15（第十三轮第八批）：#35 X 桶接线 4 处（X 157→153，W 57→61，
  调用点 56→60），单文件 `app/services/anomaly_detection_service.py`：

    services.anomaly_detection.high_frequency_detection_failed
    services.anomaly_detection.off_hours_detection_failed
    services.anomaly_detection.cross_region_detection_failed
    services.anomaly_detection.lateral_detection_failed

  裁定说明：`detect_all` 聚合 4 个**安全**异常检测器（高频撞库 / 非工作时间 /
  异地 / 横向越权），每个各自 try/except 吞掉异常并继续。任一检测器失败 → 该类
  异常**整类漏检**，而调用方（Celery `scan_anomalies`）只拿到合并后的 findings
  列表，"本次没有异常"与"检测器宕机"**无法区分**——静默安全盲区。四处全部接线。

  闸门 `TestP235Round13Batch8Wiring`（2 条）：4 对 location 双向核对 + 一次运行时
  覆盖（四个检测器各 patch 成必炸，断言计数器各 +1 且 `detect_all` 仍返回空列表，
  即"与无异常同形"）。桶计数改钉 **W=61 / X=153**。变异 M1 删任一接线 / M2 改
  location 字面量 / M3 删登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch8_result.log`。
  相邻簇 `monitoring/notifier.py`（5）本轮**未接线、留档**：三处 `send` 失败经
  `_write_channel_log` 落 `alert_channel_failed` OperationLog（M 型），`_dispatch`
  的 except 同样进该落点，`_write_channel_log` 自身失败属上报失败（S 型）。

- 2026-10-15（第十三轮第九批）：#35 X 桶接线 2 处（X 153→151，W 61→63，
  调用点 60→62），单文件 `app/services/canary_fallback_monitor.py`：

    services.canary_fallback_monitor.rollback_check_failed
    services.canary_fallback_monitor.loop_unexpected_error

  裁定说明：本模块是 **Celery 不可用时的最后安全网**（金丝雀自动回滚兜底监控）。
  接管后 `check_all_canaries` 本体失败 → 超阈值金丝雀无人回滚（故障扩大）却只记
  error 日志；循环内未预期异常（含心跳读取失败）→ 本轮接管判定/回滚机会错过而
  循环继续。两者运维不看日志就以为金丝雀有人在管。

  同簇 **2 条书面记账跳过**（仍留 X 桶，文档裁）：67（`_bump_takeover_counter`
  自身失败）是 **S 型**；88（breaker 快照失败）走"附加信号降级为主判据心跳"——
  连心跳也读不到时落在 `get_check_heartbeat_age` 被调方（其自身失败路径见对应
  簇），此处不重复计数。

  闸门 `TestP235Round13Batch9Wiring`（3 条）：2 对 location 双向核对 + 两次运行时
  覆盖（接管后回滚检查抛异常；心跳读取抛异常走外层 except）。**patch 踩坑**：
  `import app.services.auto_rollback_service as ars` 因包 `__init__` 同名
  from-import 单例而拿到**实例**而非模块——patch 模块级函数须
  `importlib.import_module`。桶计数改钉 **W=63 / X=151**。变异 M1 删接线 /
  M2 改 location 字面量 / M3 删登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch9_result.log`。

- 2026-10-15（第十三轮第十批）：#35 X 桶接线 4 处（X 151→147，W 63→67，
  调用点 62→66），单文件 `app/services/shadow_comparison_service.py`：

    services.shadow_comparison_service.fire_no_event_loop_skipped
    services.shadow_comparison_service.shadow_check_failed
    services.shadow_comparison_service.candidate_load_failed
    services.shadow_comparison_service.candidate_predict_failed

  裁定说明：影子对拍是训练产物激活前的**质量门**（样本累积 → 一致率 → 激活
  校验）。四处失败全部只记 debug/warning 日志，样本或整条管线静默丢失，最终
  都收敛到同一种失效：`is_shadow_acceptable` 恒返回 `(True,
  "insufficient_samples(...)")` —— **证据不足放行**，坏模型可直接激活上线。

  闸门 `TestP235Round13Batch10Wiring`（2 条）：4 对 location 双向核对 + 一次
  运行时覆盖四条路径（① `asyncio.to_thread` 丢进无 loop 线程触发 RuntimeError；
  async 测试内直接调反而会成功建 task 是个反直觉坑；② `_load_candidate` 必炸
  穿透到 `_shadow_check` 外层；③ 真实坏 `.pkl` 走 `_load_candidate` except；
  ④ predict 抛异常对象走 `_candidate_predict` except）。桶计数改钉
  **W=67 / X=147**。变异 M1 删任一接线 / M2 改 location 字面量 / M3 删登记行，
  均 RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch10_result.log`。

- 2026-10-15（第十三轮第十一批）：#35 X 桶接线 3 处（实记录 X 147→145、探针 P 16→15，
  W 67→70，调用点 66→69），单文件 `app/services/file_security_service.py`：

    services.file_security.clamav_dependency_missing_fail_open
    services.file_security.clamav_unavailable_fail_open
    services.file_security.clamav_error_fail_open

  裁定说明：上传安全网的 fail-open 降级放行。`scan_with_clamav` 在依赖缺失/
  clamd 不可用/扫描异常且显式开启 `clamav_fail_open` 时返回 `(True, ...)`，
  调用方 `process_uploaded_file` 只看到 True，与"干净"无法区分——未扫描的文件
  被当作已扫描通过保留。注意 118 行（EXIF 剥离失败）返回 `(False, ...)`，
  调用方直接拒绝保留（调用方可见的 V 型），不接线。同查的
  `excel_export_service.py` 3 处全部返回 `success=False + error_message` 结构化
  失败，调用方同样可见，不接线（接线只会给"调用方已处理"的路径加计数，是
  第四批 silences 教训的反例）。

  闸门 `TestP235Round13Batch11Wiring`（2 条）：3 对 location 双向核对 + 一次
  运行时覆盖三条 fail-open 路径（本仓默认无 pyclamd，ImportError 分支真实可达；
  另两条注入假 clamd 模块驱动）。桶计数改钉 **W=70 / X=145 / P=15**（本批首次把
  ImportError **探针记录本身**接线：探针 wired=True → W，P 16→15；总数 334 不变，
  口径变化已在本条记账）。变异 M1 删任一接线 / M2 改 location 字面量 / M3 删登记
  行，均 RED-OK/GREEN-OK，日志 `mutate_p2_35_round13_batch11_result.log`。

- 2026-10-16（第十三轮第十二批）：#35 X 桶接线 3 处（X 145→142，W 70→73，
  调用点 70→73），单文件 `app/core/model_engine/predict.py`：

  > 口径记账：调用点由本轮实测「改前 70 / 改后 73」得出（改前值 = 改后值 73
  > 减去本批新增 3，本批是本轮唯一的源码改动）。第十一批条目登记的「69」与
  > 本轮实测口径相差 1，**属历史快照，不回改**；差异在此记账备查。

    core.model_engine.predict.experimental_v123_unavailable
    core.model_engine.predict.lite_calibrator_unavailable
    core.model_engine.predict.lite_calibration_apply_failed

  裁定说明：三处都是「分数/对照数据看似有效实则失真，且响应形态与正常态同形」。
  v1.23 对照路整路失败时 `experimental_external_*` 保持 None、`available=False`，
  与「该模型未部署」同形；lite 校准产物缺失或执行失败时保底返回未校准概率，
  响应里的 `probability_calibrated=False` 与「校准未启用」同形。同文件另两处
  **不接线**：`_run_adapter` 已有 `adapter_miss` 专用计数器（M 型，不重复接通用
  计数器）；`_run_experimental_v121` 外层实测不可达（`get_model_info(
  "structured_v1.21_binary_lr")` 返回 None —— 注册表已移除 v1.21 四条目），接线
  即死代码（第五批 `TestP235WiringIsNotDeadCode` 同族）。

  闸门 `TestP235Round13Batch12Wiring`（3 条）：3 对 location 双向核对 + 一次
  运行时覆盖三条路径（① `_load_model_async` 必炸驱动 v1.23 整路失败；② 同法驱动
  校准产物加载失败；③ 换成无 `predict_proba` 的假校准器驱动执行失败）
  + 一条反向钉（已裁定不接线的两个 handler 用**日志语义锚点**定位，不得出现
  `record_silent_degradation`）。桶计数改钉 **W=73 / X=142**。变异 M1 删任一接线 /
  M2 改 location 字面量 / M3 删登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch12_result.log`。

- 2026-10-16（第十三轮第十三批）：#35 X 桶接线 5 处（X 142→137，W 73→78，
  调用点实测 73→78），跨三文件：

    monitoring.escalation.notify_failed
    core.idempotency.begin_failed_fail_open
    core.idempotency.settle_failed
    core.idempotency.dismiss_failed
    services.validation_engine.calculate_metrics_failed

  裁定说明：五处都是「安全网失效或部分数据，且调用方从返回值上看不出来」。
  `apply_escalation` 通知失败**不影响本轮提交**（escalation_level 照常推进并
  commit，告警被标成已升级但无人收到通知）；幂等三处分别为 Redis 故障 relinquish
  幂等控制（重复 upsert 写两次）、首次响应没落 Redis（重放丢失）、幂等键没释放
  （修正重试被判处理中）；`calculate_metrics` 中段抛异常时 accuracy/precision 已
  写入，返回残缺但合法的 ValidationMetrics。

  同批裁定**不接线** 2 处（`services/validation_engine.py`）：`_run_model_inference`
  与 `_compute_baseline_metrics` 的失败都由调用方写进 `ValidationResult.errors`
  （调用方可见的 V 型，与第十一批 EXIF 剥离失败同口径）。

  闸门 `TestP235Round13Batch13Wiring`（3 条）：5 对 location 双向核对 + 一次
  运行时覆盖五条路径（① `CompositeNotifier` send 抛异常 + MagicMock 建模
  AsyncSession；② ③④ 注入 `get_redis_client` 返回全抛的假 Redis；⑤ 把模块级
  `roc_auc_score` 换成抛 RuntimeError，穿透内层只吃 ValueError 的 try）+ 一条
  反向钉（两条 V 型用日志语义锚点定位，不得出现接线）。桶计数改钉
  **W=78 / X=137**。变异 M1 删 idempotency.begin 接线 / M2 改 escalation location
  字面量 / M3 删 P2_11 附录登记行，均 RED-OK/GREEN-OK，日志
  `mutate_p2_35_round13_batch13_result.log`。

- 2026-10-16（第十三轮第十四批）：#35 X 桶接线 4 处（X 137→133，W 78→82，
  调用点实测 78→82），跨两文件：

    core.safe_pickle.joblib_env_guard_unavailable
    core.safe_pickle.torch_env_guard_unavailable
    core.model_registry_v2.registry_file_unparsable
    core.model_registry_v2.registry_records_dropped

  裁定说明：四处都是「**保护层的保护罩**掉了，而加载/读取本身照样成功」。
  ISS-006（joblib 生产环境强制哈希校验）与 ISS-046（torch 生产环境强制
  weights_only=True）都靠读 `settings.app_env` 判定，settings 读不到 → 加固整段
  跳过、实参停在调用方传入的不安全值，函数照常返回对象；注册表两处分别是整体
  损坏后旁路并**以空表启动**（与全新注册表同形）、部分记录结构坏后**只加载好的
  那几条**（registry 非空且能用，只是少了几条）。

  同批裁定**不接线** 1 处：`core/safe_pickle.py::_restricted_unpickler_class`
  导入 joblib.NumpyUnpickler 失败返回 None，但唯一调用点在下一句就把 None 翻译
  成 raise（fail-closed，注释明示绝不退回无白名单的 joblib.load）→ V 型。反向钉
  除「不得接线」外还额外钉住该 fail-closed 判据本身，判据一旦被移除，这条裁定
  的前提就没了。

  闸门 `TestP235Round13Batch14Wiring`（3 条）：4 对 location 双向核对 + 一次
  运行时覆盖四条路径（①② 把 `app.core.config.settings` 换成 `app_env` 访问抛
  异常的对象，即可命中两处的环境变量降级分支 —— 不必伪造 import machinery；
  ③④ 在 tmp_path 各造一份损坏/缺字段的注册表 JSON 后构造 ModelRegistryV2）+
  一条反向钉。桶计数改钉 **W=82 / X=133**。变异三条见
  `mutate_p2_35_round13_batch14_result.log`。

- 2026-10-16（第十三轮第十五批）：#35 X 桶接线 3 处（X 133→130，W 82→85，
  调用点实测 82→85），跨三文件：

    main.sidecar_audit_skipped
    services.model_predict.fusion.canary_routing_failed
    services.model_predict.inference.model_fingerprint_failed

  裁定说明：三处都是「**失效的东西是别人判断的依据**」。启动时侧车完整性审计失败
  → 整段跳过，「缺失/陈旧」的可见性消失，与「审计通过、全部一致」同形（侧车是
  strict 环境拒绝加载的依据）；灰度路由决策失败 → `canary_routed` 保持 False，
  本该进灰度的用户静默走 stable 且响应无标记 → 灰度样本分配失真；模型指纹计算
  失败 → 缓存键前缀退化为 `"unknown"`，「换模型即自动失效」机制失效，用户会命中
  上一个模型版本的缓存结果。

  同批裁定**不接线** 12 处，按三类记账（详见 P2_13「一之十五」）：
  ① `core/celery_app.py` 3 条 —— worker / beat 是**独立容器**
  （`docker-compose.yml:201/252`），全仓无 `PROMETHEUS_MULTIPROC_DIR` /
  `MultiProcessCollector` / `start_http_server`，计数只会落在 worker 进程内存，
  `/metrics` 永远读不到（第四批「计数器恒为 0 的指标是误导」同族）；
  ② `ml/unified_model_interface.py` 3 条 —— 唯一引用方 `canary_controller` 自身
  无生产调用者，`ml/__init__.py` 明示「仅标注、不实际导入」→ 生产链路不可达，
  接线即死代码（第十二批 `_run_experimental_v121` 同口径）；
  ③ `services/excel_export_service.py` 3 条 —— 均返回 `success=False` +
  `error_message`，属调用方可见的 V 型。
  另有 `main.py` L216（preload 失败写进 `startup_status`，由 `/health/startup`
  暴露）、`fusion.py` L157/L222、`inference.py` L143（三者均为观测系统自身上报
  失败，S 型）。

  闸门 `TestP235Round13Batch15Wiring`（原 2 条，补钉提交补齐反向钉后为 3 条）：
  3 对 location 双向核对 + 一次
  运行时覆盖两条路径。运行时含一条**防假绿**断言：patch `AsyncSessionLocal` 为可用
  的假会话并断言 `decide_version` 确被调用 —— 否则异常可能来自建会话而非路由
  决策，计数照样 +1 却是假绿。`main.sidecar_audit_skipped` 未做运行时断言（在
  FastAPI `lifespan` 内联，触发需完整启动链路，与第六批
  `api.alerts.webhook.final_commit_failed` 同口径）。桶计数改钉 **W=85 / X=130**。
  变异三条见 `mutate_p2_35_round13_batch15_result.log`。

- 2026-10-16（第十三轮第十六批）：#35 X 桶接线 4 处（X 130→126，W 85→89，
  调用点实测 85→89），跨两文件：

    core.ws.local_send_failed
    core.ws.pubsub_message_handling_failed
    services.shadow_mode.predictor_unavailable
    services.shadow_mode.compare_failed

  裁定说明：四处都是「**旁路失效，而主链路返回值毫发无损**」。ws 两处：本进程
  投递失败 → 该用户这一次推送静默丢失（`send_to_user` 继续走 Redis 发布并正常
  返回）；订阅循环里单条消息处理抛异常 → 该条消息被丢弃、循环照常续跑，而
  投递方早已返回成功。影子两处（`shadow_mode_service` 经 `main._init_shadow_sink`
  注入生产链路，非死代码）：推理器加载失败 → 对拍停用、生产 TF-IDF 链路毫无
  变化，一致率数据从此断流；单次对拍异常 → 该样本从统计中静默消失，切换决策
  依据出现无痕缺口。

  同批裁定**不接线** 9 处，按四类记账（详见 P2_13「一之十七」）：
  ① ws disconnect 的指标 dec 失败（M 型：指标采集自身，主链路不受影响，
  连接上限拒绝对客户端可见）；② `rate_limit.py` 2 条 —— 签名修补回退后
  FastAPI 解析失败会以 500 暴露（V 型）、中间件 RateLimitExceeded→429
  是设计内转换；③ `token_blocklist.revoke_token` 撤销失败（V 型：三个
  调用方均检查返回值并记 ERROR，检查侧 `is_token_revoked` fail-closed
  已堵）；④ `tenant_guard.scan_unscoped_protected_queries` 跳过不可解析
  文件（运行期不可达：全仓 `app/` 无调用方，仅两个测试门禁调用）。
  另有 `status.py` 缓存写失败（无失真：返回实时计算的真数据）、
  `checksum.py` 2 条（fail-closed 判 stale + 启动审计报告可见；清理路径
  仅维护脚本调用）、`risk_service_warning` 事件发布防御层（底层
  `core.event_bus.publish` 已接线且队列满不向上抛，本层为重复层）。

  闸门 `TestP235Round13Batch16Wiring`（5 条）：4 对 location 双向核对 +
  一次运行时覆盖四条路径（各带防假绿断言：假连接 send_text 必炸且确被调用、
  pubsub 假客户端确投递过消息、推理器 predict 确被调用且失败后
  `_predictor_loaded` 仍为 False、对拍失败后统计不涨）+ 五条反向钉
  （8 个行为锚点不得接线 + token_blocklist 的 `return False` V 型判据 +
  tenant_guard 的 `continue` 形状与生产无调用方 + event_bus 底层接线
  仍在）。桶计数改钉 **W=89 / X=126**。变异三条见
  `mutate_p2_35_round13_batch16_result.log`。

- **第十三轮第十七批（X 126→123，W 89→92，总数 334 不变）**：3 处实记录
  X→W。① `core.health.monitor_refresh_failed`（`_health_monitor_loop`
  快照刷新失败 → 缓存留旧值，`/health/ready` 仍以 200 + 陈旧快照应答，
  探针无从得知健康数据已停更）；② `core.middlewares.http_metrics_record_failed`
  （`metrics_middleware` finally 里 `http_requests_total.inc` 失败 → 请求
  照常返回，SLO 可用性数据静默缺口）；③
  `services.registry_auto_rollback.check_failed`（`_rollback_loop` 检查
  失败 → 循环静默续跑，自动回退监控形同停摆，超阈值危险产物滞留
  PRODUCTION）。同批裁定不接线 12 处：`hyperparameter_tuning` 缓存读/写
  失败（结果正确、仅断点续跑失效的性能降级）、`pdf_report_service` 两处
  （success=False + error_message 的 V 型显式失败）、`instance.get_instance_id`
  （降级值 "unknown-<pid>" 形态可辨）、`tasks/observability._flush_lock_stats_impl`
  （返回 False → 上层 retry + FAILURE 事件）、`ml/model_loader._resolve_artifacts_dir`
  与 `ml/scaler.__getattr__`（F 型 fallback，路径不存在时后续加载可见报错）、
  `ml/model_validation._bootstrap_auc_ci_with_count`（degenerate 计数随返回值
  暴露）、`email_service._close_thread_smtp`（C 型清理低价值）、
  `text_tokenizer._get_jieba`（仅日志级别无失真）、`review_service.create_review_task`
  （底层 event_bus.publish 已接线的防御性重复层）。

  闸门 `TestP235Round13Batch17Wiring`（3 条）：3 对 location 双向核对 +
  一次运行时覆盖三条路径（各带防假绿断言：快照 probe 确被调用、假计数器
  inc 确被调用且响应仍 200 交还、check probe 确被调用）+ 一条反向钉
  （12 个行为锚点逐一「未接线 + 锚点仍在」）。桶计数改钉
  **W=92 / X=123**。变异三条见 `mutate_p2_35_round13_batch17_result.log`。

- **第十三轮第十八批（X 123→120，W 92→95，总数 334 不变）**：3 处实记录
  X→W。① `services.auto_rollback_service.check_failed`
  （`check_all_canaries` 单 canary 检查/回滚整体失败 → check_result 被洗成
  `should_rollback=False + reason="check_error"`，两个调用方（scheduler beat /
  fallback monitor）都只按 should_rollback 分支走 debug 级日志——
  「无需回滚」假象下检查根本没跑成，与已接线的
  `rollback_savepoint_failed` 同族）；②
  `services.model_predict.training_jobs.redis_list_fallback`
  （`list_training_jobs` 读 Redis 失败回退内存表，残缺子集经 status.py 的
  `ok({"jobs": ...})` 包进成功响应，Redis 里仍在运行的任务整体消失）；
  ③ `services.model_predict.training_jobs.redis_update_failed`
  （`update_job` 内存表已改而 Redis 持久化失败 → 双写不一致，函数无返回值
  调用方无从得知只写了一半）。
  同批裁定不接线 13 处：`auto_rollback_service` 5 条（`_bump_lock_counter`
  专用计数器全覆盖的 M 型，`get_check_heartbeat_age` 返回 None 时调用方有
  专门接管分支）、`notifier._dispatch`（V 型 success=False + error_msg 随
  results 返回 + alert_channel_failed 审计）、`notifier._write_channel_log`
  与 `am_sync._write_sync_log`（C 型审计写失败）、`am_sync.pull_silences`
  （V 型返回 None 显式失败 + am_sync_failed 审计）、
  `silences.create_silence` 的 AM sync 异常（第四批注释明示不重复计数，
  精细钉：同函数内补偿路径 am_rollback_failed 已接线须仍在）、
  `training_jobs.get_training_job`（V 型 storage_degraded=True + message
  变更显式可辨）、`event_bus._consume_loop` 2 条（handler_errors 专用
  计数器 M 型；loop 级为 queue.get() 异常的防御性不可达路径）。

  闸门 `TestP235Round13Batch18Wiring`（4 条）：3 对 location 双向核对 +
  一次运行时覆盖三路径（各带防假绿断言：check 确被调用且结果确被洗成
  should_rollback=False/check_error、内存表任务确出现在返回里、内存写确已
  生效）+ 两条反向钉（10 个行为锚点逐一「未接线 + 锚点仍在」+ silences
  同函数双 except 反向裁决精细钉）。桶计数改钉 **W=95 / X=120**。
  变异三条见 `mutate_p2_35_round13_batch18_result.log`。

- **第十三轮第十九批（纯裁定批，W=95 / X=120 不变）**：scheduler(7) +
  `core/model_engine/loading`(4) + `core/config`(2) 共 13 条 X 候选逐条
  代码实证后全部裁定不接线，无实记录 X→W。判据四类：① S 型自报失败
  通道自身失败 3 条（scheduler Sentry capture_message/capture_exception
  ——主通道 error 日志或 raise RuntimeError 显式中止已在）；
  ② C 型清理路径 4 条（uploads/experiment 清理的 skip/pass/rmtree 失败，
  失败形状是「少删一些」的磁盘增长而非数据失真，且 celery 跨进程计数
  不可达）；③ V 型显式失败信号 1 条（loading._get_expected_hash 侧车
  不可解析返回带来源标记的 tuple，P0-6 修复的三态可区分）；
  ④ 设计内/低价值/dev-only 5 条（_load_adapter 的 M 型专用计数器、
  _load_model BERT 无缓存回退 Hub 的设计内双路径、_patch_simple_imputer
  补丁失败后续可见 AttributeError、config PII key 文件读/写失败的
  dev-only + warnings.warn）。

  闸门 `TestP235Round13Batch19Declined`（3 条）：函数级反向钉 7 个 +
  except 块级精细钉 2 个（_load_adapter/_load_model 同函数内有其他已
  接线路径，函数级断言会假红，AST 定位目标 handler 并同时钉住见证
  接线 adapter.pkl_fallback / keras_compat_load_failed 仍在）+
  文档登记 1 条（「一之二十」节 + 13 条裁定关键标识 + 纯裁定批账实
  一致）。桶计数不改钉，维持 **W=95 / X=120**。变异三条见
  `mutate_p2_35_round13_batch19_result.log`。

- **第十三轮第二十批（接线 1 处 + 不接线 14 处，W 95→96 / X 120→119）**：
  接 `api.alerts.history_detail_parse_failed`（`api/v1/alerts/__init__.py`
  `list_alert_history`：detail JSON 解析失败 → warning + `detail={}` →
  rule/severity/message 全空的**空壳 item 仍照常入列表**，与正常记录
  同形，告警内容静默丢失）。不接线 14 处：① alerts 4（V 型：
  `_handle_silenced_alert` return False；`_handle_active_alert` 三个
  except 分别注释明示 default-to-send / failed 计数 (0,1,0) /
  notify_failed 计数 (1,0,1)）；② pii_crypto 2（V 型：`_get_previous_fernets`/
  `_get_previous_aes_gcms` 旧密钥派生失败跳过，后果由 decrypt_field
  密钥全耗尽时 raise ValueError + error 日志 exhausted 显式暴露）；
  ③ escalation 2（M 型：`compute_escalation` detail 解析失败已有
  `alert_detail_parse_failed_total` 专用计数器，AUDIT-2026-10-06 P1-6；
  内层计数上传失败只记 debug）；④ drift 2（V 型
  `DriftCheckResult(failed=True)` / S 型 `_push_to_gauge` Gauge 自报
  失败）；⑤ model_registry_v2 2（`_quarantine_corrupt_file` 旁路失败
  上游 registry_file_unparsable/records_dropped 已计数且是最佳努力 /
  `_promote_model_locked` 内存回滚 return None）；⑥ fusion 1（M 型变体：
  `predict_fusion` canary 指标自增失败，主链路无失真且
  `_log_canary_event` 仍写事件）；⑦ main 1（V 型：
  `_preload_models_background` 经 `startup_status.record("model_preload",
  "failed")` 显式记录）。

  闸门 `TestP235Round13Batch20Wiring`（6 条）：location 双向核对 +
  运行时驱动（正常行/损坏行各一条都入列表，空壳同形失真实证 + 计数器
  +1）+ 函数级反向钉 9 个 + except 块级精细钉 5 个（_handle_active_alert
  三个 except 分别钉、escalation 内层计数上传失败、predict_fusion 同函数
  有 canary_routing_failed 见证接线需 handler 级）+ 裁定前提见证钉
  （decrypt_field 的 raise 与上游两条接线仍在）+ 文档登记 1 条。
  桶计数改钉 **W=96 / X=119**。变异四条见
  `mutate_p2_35_round13_batch20_result.log`。
- **第十三轮第二十一批（纯裁定批，0 接线，W=96 / X=119 不变）**：
  `core/model_engine/predict.py` 剩余 6 条未接线候选逐条存在性实测后
  全部裁定不接线。① scaler 加载失败 handler（L178）：初判与第二批
  `experimental_v121_scaler_fallback` 同型（未缩放特征直接算分、响应
  同形），实测发现**双重外部阻断不可达**——`structured_default_model`
  默认 `"v1.23"`（Pipeline 无需 scaler，不进分支）+ `models/*.pkl` 按
  `.gitignore` 有意不入库（tracked pkl 实测 0，v1.20 主模型恒
  FileNotFoundError → model=None），同第十二批 v1.21 外层死代码与
  keras「生产恒 MISSING」先例，解锁条件（切回 v1.20 且 pkl 入交付）
  已记账；② 模型加载失败 handler（L167）：`fallback_reason=
  "model_load_failed: ..."` 显式（V 型，当前形态下真实可达）；
  ③ `predict_lite` L887/L897：`_incr_fallback` + fallback_reason
  显式（V 型）；④⑤ `_run_experimental_v121` 外层（注册表实测仍无
  v1.21）与 `_run_adapter`（adapter_hit/miss 计数器在）为第十二批
  已裁项，本批实测复核维持。连带修复 L147 注释漂移（「v1.20 (默认)」
  与实际默认 v1.23 矛盾，正是初裁被误导的根源）。

  闸门 `TestP235Round13Batch21Declined`（6 条）：scaler handler
  except 块级反向钉 + 模型加载/lite 三条 V 型反向钉（fallback_reason
  与 `_incr_fallback` 显式信号在）+ 已裁维持 1 条（get_model_info
  实测 None + adapter 计数器在）+ 交付形态前提钉 1 条（默认 v1.23 +
  `.gitignore` 排除 + `git ls-files *.pkl` 实测 0）+ 文档登记 1 条。
  桶计数维持 **W=96 / X=119**。变异四条见
  `mutate_p2_35_round13_batch21_result.log`。
- **第十三轮第二十二批（纯裁定批，0 接线，W=96 / X=119 不变 +
  连带修复死计数器）**：health 1 + auto_rollback 5 + pii_crypto 4
  共 10 条 X 桶候选全部裁定不接线（K 型清理 / V 型显式上报 /
  M 型专用计数器——前提经本批修复后真正成立 / V 型回退链中间步），
  8 条已定型项（health 6×H / auto_rollback 2×S）复核维持。
  **核心发现**：`_bump_lock_counter` 与 `_bump_takeover_counter`
  原调用 `canary_rollback_check_lock_total.labels(outcome=...).inc()`
  （prometheus_client 形态），而 `app/core/metrics.py` 的 Counter
  是自研类（`inc(**labels)`，无 `.labels()`），每次 AttributeError
  被 except 吞掉只留 debug 日志 ⇒ 两个计数器**自 e120ce3 引入起
  恒 0**；第二批 1.7 表「已有专用计数器」的 M 型裁定与第十八批
  反向钉均只钉源码字面量、从无运行时计数断言，死计数器活过全部
  往批。已改自研 API 并新增回归测试
  `test_dedicated_counters_actually_increment` + AST 级 `.labels(`
  禁现防回退钉。

  闸门 `TestP235Round13Batch22Declined`（10 条）：health H 型家族
  反向钉 + stop_health_monitor K 型钉 + auto_rollback 家族反向钉
  （7 处 unavailable 计数点 + API 形态钉）+ pii_crypto 回退链钉
  （2+2 个中间 handler 未接线 + 末端 raise×2 + exhausted 日志）+
  轮换探测见证 + 计数器真涨回归 + 运行时四条（锁 fail-open /
  心跳 None / decrypt 耗尽 raise / 健康检查 return False）+
  文档登记。桶计数维持 **W=96 / X=119**。变异四条见
  `mutate_p2_35_round13_batch22_result.log`。
- **第十三轮第二十三批（纯裁定批，0 接线，W=96 / X=119 不变）**：
  `services/validation_engine.py` 5 条未接线 handler 逐条存在性实测
  后全部裁定不接线/复核维持。① L422 `_run_model_inference` /
  L512 `_compute_baseline_metrics`：第十三批已裁 V 型（失败
  `return None` + error 日志，调用方 `validate_model` 显式写
  `result.errors`），本批锚点实测复核维持；② L147
  `_load_csv_dataset` / L207 `calculate_metrics` 内层 auc / L271
  `_calculate_small_classification_metrics`：分类器定型 D（脏数据
  探测，单条解析跳过、数据本来就是坏的），本批首次书面裁定维持——
  非数值特征原样保留字符串、单类标签 AUC 本就无定义（`auc=None`
  诚实且返回值显式）、非数字标签样本跳过后 `sample_count` 更新为
  有效样本数（返回值可核对）；三条均有既有测试钉住设计行为。

  闸门 `TestP235Round13Batch23Declined`（5 条）：D 型三兄弟块级
  反向钉（未接线 + `pass`/`total -= 1`/auc 赋值见证 + 外层
  `calculate_metrics_failed` 互锁）+ X 二兄弟复核维持 + 运行时
  四条（CSV 非数值保留 / 有效样本数 / 单类 AUC=None 零接线 /
  推理不可用写 errors）+ 文档登记。桶计数维持 **W=96 / X=119**。
  变异三条见 `mutate_p2_35_round13_batch23_result.log`。

- **第十三轮第二十四批（接线 1 处，W 96→97 / R 4→3 / X 119 不变）**：
  `app/core/ws.py` 13 条候选逐条存在性实测 + 分类器现场重算。
  ① 接线 `core.ws.pubsub_loop_crashed`：`_pubsub_loop` 外层
  handler 崩溃后 sleep 1s 重启，≥1s 无订阅者窗口内（Redis 持续
  故障时每秒崩溃一次、窗口长期存在）其它 worker 发布到本节点
  用户 channel 的消息被 Redis 直接丢弃，而发布方 `publish` 早已
  返回成功——消息永久丢失且无任何调用方能察觉。原分类器判 R
  （sleep+restart 自愈）本批改判接线：自愈只恢复订阅不恢复消息，
  丢失的是外部输入，与第六批 inference persist 的 R 型先例（下轮
  从进程内内存状态重新生成、无外部输入丢失）本质不同。② 不接线
  12 处：S 型 2（`_inc_ws_auth_failure` / `connect` 指标 inc 失败，
  采集自身）、M 型 1（`disconnect` 指标 dec 失败，第十六批已裁
  复核维持）、K 型 2（两处 CancelledError 正常控制流）、C 型 2
  （stop 关停异常 / finally aclose 清理失败）、D 型 2（畸形
  payload / 非法 channel，数据本来就是坏的）、V 型 3
  （`websocket_endpoint` 三处：close 4001/4503 原因码 + 专用
  计数器 + 日志，失败对客户端显式）。

  闸门 `TestP235Round13Batch24Wiring`（6 条）：接线 location 双向
  核对 + 运行时一条（假 pubsub `psubscribe` 必炸 → 计数恰好 +1，
  防假绿：psubscribe 调用计数 ≥1 + 取消时机压.sleep 内防双计数）+
  反向钉 10 条文本锚点 + K 型函数级锚点（`stop_pubsub_subscriber`
  裸 `pass` 按 enclosing function 定位）+ V 型见证 3 条（close
  原因码 / disconnect 仍在）+ 文档登记。桶计数棘轮实跑改钉
  **W=97 / R=3 / X=119**。变异见
  `mutate_p2_35_round13_batch24_result.log`。

- **第十三轮第二十五批（纯裁定批，0 接线，W=97 / X=119 不变）**：
  `app/tasks/scheduler.py` 9 条候选逐条手工核对——第十九批已裁 7 条
  （L401/L510/L994/L1001/L1054/L1102/L1170），本批 5 条为真新候选。
  分类器现场重算：L81→M、L108→S、L129→M（函数级误并，实为 S 型，
  第十九批③ 同型）、L1134→F、L1150→F；**五条均不在 X=119 内**。
  ① `_notify_warning` L81 重试 except（M 型）：失败先就地重试
  （`_NOTIFY_MAX_ATTEMPTS=2`），耗尽后 error 级完整上下文日志 +
  `warning_notify_failed_total` 专用计数器 + Sentry + `return False`；
  调用方 `_daily_risk_scan_impl` 检查 `ok` 并汇总 error 上报。
  **裁定前按第二十二批纪律实测专用计数器存活**：注入双探针均抛 →
  返回 False + 探针调用 2 次 + 计数器 +1 + 通用计数器零调用。
  L108（指标 inc 失败）/ L129（Sentry capture_exception 失败）为
  S 型：失败的是自报通道自身，主通道已先触发。② `_cleanup_
  experiment_artifacts_impl` L1134/L1150（F 型）：产物目录/文件
  resolve 失败 → AUDIT-P0-3「宁可整个清理中止，也不能带残缺保护集
  继续删」，warning + `is_active = True` 保守跳过删除（文件侧还
  `break` 停止遍历该目录）。

  闸门 `TestP235Round13Batch25Declined`（6 条）：`_notify_warning`
  三 handler 块级反向钉（按注释标记分辨 retry/metric/sentry）+
  终端见证（`return False` + error 汇总 + 专用计数器 + Sentry）+
  调用方汇总见证（`ok` 检查 → `failed_notifications.append` →
  汇总 error）+ 清理两条 F 型块级反向钉 + `is_active = True` 见证
  + `rmtree` 仍在（正常删除路径未被裁掉）+ 运行时两条（推送失败
  实证；清理 resolve 抛 `OSError` 的**差分实验**：对照组删最老
  1 个 / 实验组 removed=0 且目录保留）+ 文档登记。桶计数维持
  **W=97 / X=119**。变异三条见 `mutate_p2_35_round13_batch25_result.log`。

- **第十三轮第二十六批（纯裁定批，0 接线，W=97 / X=119 不变）**：
  `app/core/model_engine/loading.py` 收口（7 条候选）。机器口径：六条仍
  在 X（第七批「跳过 6 条、机器不裁文档裁」的历史写法所致）、L244 判 S。
  ① 首次书面裁定 3 条：L244 `_incr_model_fallback` 指标 inc 失败（**S 型**
  ——指标采集通道自身失败；P0 (2026-09-24) 注释已定性「曲线变平」风险，
  AUDIT-2026-10-05 把日志从 debug 提到 warning + `exc_info=True` 补齐盲区；
  此函数是第二批 L82/L429 两次接线的 M 型理由来源，其自身失败只改变曲线
  形状、不改变调用方返回值）；L288/L294 `preload` PermissionError/OSError
  （**V/M 混合——消费点已接线**）。② 往批已裁 4 条做记账一致性复核
  （`_get_expected_hash` / `_load_adapter` / `_load_model` /
  `_patch_simple_imputer`，第十九批已钉）。

  L288/L294 的裁定依据（替代第七批仅「critical 日志 loud」的软理由）：
  `PredictMixin.predict_structured` 的模型加载 try **只捕获
  (FileNotFoundError, ValueError)**，PermissionError / 一般 OSError
  **不被捕获 → 向调用方传播**（运行时 `pytest.raises(PermissionError)`
  实证）；主消费方 `services/risk_service_assessment.py` 对该调用包了
  `except Exception` 并已接第二批的 `structured_predict_fallback`，返回
  dict 自带 `"error": str(exc)` 与 `"model_used": "heuristic_fallback"`
  ——真降级那一刻已被计数且显式标注，预热期再接会重复计数；诊断侧由
  critical「NON-RECOVERABLE」日志文明。

  闸门 `TestP235Round13Batch26Declined`（7 条）：L244 块级反向钉 +
  warning/`exc_info`/`model_fallback_total.inc` 三见证；L288/L294 块级
  反向钉 + `logger.critical` + `NON-RECOVERABLE` 见证 + 两条既有接线
  互锁（`preload.missing_file` / `preload.failed` 仍在）；**消费点见证钉**
  （`predict_structured` 捕获类型集合恰为 {FileNotFoundError, ValueError}；
  `risk_service_assessment` try→handler 定位 + 专用 location + 返回形态
  显式）+ 往批复核 + 运行时两条（preload 依次抛 PermissionError/OSError
  → 循环继续、零接线调用、critical 日志文明；`predict_structured` 真的
  向上抛——须用完整 14 特征，否则 routing 会在「信息不足」处提前 return
  导致断言假绿）+ 文档登记。桶计数维持 **W=97 / X=119**。变异四条见
  `mutate_p2_35_round13_batch26_result.log`。

- **第十三轮第二十七批（纯裁定批，0 接线，W=97 / X=119 不变）**：
  `app/core/sentry.py`（6 条）+ `app/api/v1/metrics.py`（5 条）收口。
  两簇检索全文**无任何裁定记载**，属真正的新库存（sentry 此前只在
  「scheduler 里的 Sentry 调用点」语境被裁过、本体从未逐条裁；
  metrics.py 的 5 个 `_set_*` 采集器同样从未裁过）。挑簇器前列的
  ws.py/scheduler.py/loading.py 三簇**全部系已裁残留**——挑簇器
  「文档未提及 = 未裁定」信号缺陷第六次实锤。
  机器口径：11 条**全判 S**（两文件均在分类器 `SELF_REPORT_FILES`
  白名单）。逐条独立复核后全部维持不接线：L103 `init_sentry` SDK
  import 失败（S 型——可观测性设施自身启动失败；且 sentry-sdk 是
  `requirements.txt:50` 顶层依赖 + `requirements.lock:323` 硬锁
  `2.71.0` + `Dockerfile:100` pin 清单显式含，生产镜像构建期必装、
  运行期不可达）；L148/L163（S 型——自报通道自身失败，调用方
  `scheduler.py:117-130` 还有第二层 try/except 记 debug）；L27/L36/L47
  `_extract_status_code`（D 型——上游脏数据，`pass` 后穷举下一路径，
  三条全失败才 `return None`）；metrics.py 五条 `_set_*`（S 型——采集
  失败不改 HTTP 状态码，旧 gauge 留存比归零更保守；第二十六批 L244
  同型先例可援引）。

  **运行时实证附带发现（已转独立待办信号）**：`init_sentry` 的两个
  handler 都是 `return` 不抛，调用方 `main.py:249`
  `record_step_sync("init_sentry", _init_sentry, fatal=False)` 因此把
  状态记为 **`ok`**——实测输出
  `init_sentry record -> {"status": "ok", "error_type": "", ...}`，
  即 `/health/startup`（`main.py:543`）**无法区分「Sentry 已初始化」与
  「SDK 根本导不进来」**。`startup_status` 其实有 `skipped` 状态可用
  （`test_iss02_startup_status.py:59` 已有用例），但修它需改
  `init_sentry` 返回契约或让 main.py 显式记 `skipped`，属**行为变更
  而非接线**，超出 #35 范围；R-006 注释亦明示「初始化失败不影响启动
  （仅监控降级）」。

  **文件内正确范式互锁**：同文件 `_set_redis_metrics`（L100-108）失败时
  执行 `redis_circuit_state.set(2)`——把「Redis 不可达」编码进指标值
  本身，是全文件唯一「失败被显式编码」的采集器；与五处「只 warning」
  形成对照，已加互锁钉（改成纯 warning 会打红闸门）。端点鉴权链
  `_require_metrics_token`（L47-68，AUDIT-2026-10-06 P1-3）是
  fail-closed 白名单，无静默口子。

  闸门 `TestP235Round13Batch27Declined`（9 条）：11 处存在性 + 块级反向钉
  （含直调式 `silent_degradation_total` 禁现）+ sentry 三条 warning 文案
  见证 + `_extract_status_code` 三路径结构钉（handler 数=3 / 捕获类型 /
  `pass` 形态 / 三个取值键按 AST 字符串实参断言，**不用文本匹配以免
  引号风格漂移**）+ metrics 五条 warning 文案见证 +
  `_set_redis_metrics` 范式互锁 + 运行时两条（启动状态记 `ok` 实证 /
  非数值 status code 三路径皆 `None` 且合法值仍能提取）+ 既有测试与
  R-006 注释互锁 + 文档登记。桶计数维持 **W=97 / X=119**。变异四条见
  `mutate_p2_35_round13_batch27_result.log`。

- **第十三轮第二十八批（纯裁定批，0 接线，W=97 / X=119 不变）**：
  `app/core/model_engine/fallback.py`（5 条，新库存）+
  `app/services/observability_exporter.py`（4 条，新库存）+
  `app/monitoring/notifier.py`（5 条，复核）。前两簇检索 P2_11/P2_13
  全文**零裁定记载**（`_incr_model_fallback` 的 M 型先例只裁过
  `model_engine/loading.py` L244 与 `predict.py` 侧调用点，从未裁过
  fallback.py 自身的 4 个 inc 失败点；exporter 全文从未逐条裁过）；
  notifier 5 条已由 P2_13 §1.25 + §一之十一⑤⑥ 逐条裁过，本批复核维持。

  **核心发现（分类器粗排需修正）**：分类器把 fallback.py L171/L199/
  L233/L297 判为 **S 型（metrics 自报失败）**，运行时实测证明应为
  **P 型（特性探测）/ 运行期不可达**——`_incr_model_fallback`
  （`model_engine/loading.py:234`）自身内层已有 `except Exception`
  全捕获并 warning，**永不向外抛**（E1b 实测：把 `model_fallback_total.inc`
  打成必抛，该函数仍未外抛）。故四处外层 except 唯一可达路径是
  `from app.core.model_engine.loading import _incr_model_fallback`
  这一行失败（ImportError）。E1a 顺带实证 `model_fallback_total`
  真的增长（`0.0 → 1.0`，第二十二批纪律的执行）；E1c 实证屏蔽该 import
  后 `_text_heuristic_fallback` 返回结构与降级标记仍与正常态同形。
  **纪律意义**：给不可达路径接线＝制造「看起来有降级观测、实际永不触发」
  的假设施，是第二十二批「自出生即死的专用计数器」的**镜像**形态
  （那次计数器活着但恒 0，这次 except 存在但不可达）——共同教训仍是
  **源码字面量在≠ 运行时活着**。L81 `_finite` 的 `float()` 失败为 **D 型**
  （上游脏数据，已warning 且退回既有默认值）。

  `observability_exporter.py` 四条：L136 `stop` 的 `CancelledError` 为
  **K 型**（任务取消的正常配对）；L150 `_wait_for_db_ready` 与 L168 `_loop`
  为 **R 型**（自恢复），其中 L168 有**硬证据 E2**——`_safe_set_alert_total`
  失败时不推进 `_prev_total_fired`，故下轮 delta 会把退避期间新增告警一并
  计入（实测：基线 100 → 失败轮基线仍 100、Counter 无增量 → 恢复轮
  `total_fired=130` 得 delta **= 30**），即自愈不丢外部输入，符合第二十四批
  R 型判据；已加结构钉锁住「`_compute_trend` 调用行号 < `_prev_total_fired`
  赋值行号」，顺序颠倒会让退避期增量永久丢失。L206
  `_record_export_failure` 的计数器 inc 失败为 **S 型**（失败的是
  `observability_export_errors_total` 自身，且注释明示避免递归失败）。

  `notifier.py` 复核维持V/V/V/V/C：E3 实测通道失败既进
  `results{"probe": False}`（调用方可察觉）又落 `alert_channel_failed`
  审计（detail 带 error 原文）⇒ 三处 `send` 与 `_dispatch` 为 **V 型**；
  `_write_channel_log` 审计写失败为 **C 型**。复核钉同时确认
  `monitoring.escalation.notify_failed`（第二十四批已接）与
  `alerts._handle_active_alert` 的 `return 1, 0, 1` 失败形态仍在。

  闸门 `TestP235Round13Batch28Declined`（10 条）：14 处存在性 + 块级反向钉
  （含直调式 `silent_degradation_total` 禁现）+ 四处 import 首行结构钉 +
  `_incr_model_fallback` 内层全捕获结构钉 + `_safe_set_alert_total` 基线推进
  顺序钉 + `observability_export_errors_total` 调用见证 + notifier 复核钉
  + 运行时三条（E1a/E1b/E1c 合一、E2、E3）+ 文档登记。桶计数维持
  **W=97 / X=119**（分类器现场重算 14 条**无一条在 X 桶内**）。变异四条见
  `mutate_p2_35_round13_batch28_result.log`。挑簇器「文档未提及 = 未裁定」
  信号缺陷**第七次**实锤。
  **测试污染事故（已修）**：E3 首版直接赋值 `notifier.record_audit = _fake`
  且未还原，合并跑时把 `tests/test_notifier.py` 四条通道审计用例打红，
  而单跑该文件 55 passed 全绿 —— 「单跑绿 / 合并跑红」是测试间污染的可客
  signature。已改 `monkeypatch.setattr`，复跑 7 个受影响文件**405 passed**。

- **第十三轮第二十九批（纯裁定批，0 接线，W=97 / X=119 不变）**：
  `app/core/otel.py`（7 条）+ `app/api/v1/model_predict/_common.py`（6 条）。
  两簇函数名级零记载（`init_otel` / `_instrument_fastapi` /
  `_instrument_sqlalchemy` / `_instrument_redis` / `instrument_app` /
  `shutdown_otel` / `_generate_*_factors` / `_save_assessment_sync`
  在 P2_10+P2_11+P2_13 全文一次都未被登记）。

  **检索口径修正（本批方法论级）**：裁定记载的检索单位由「文件名」改为
  **「函数名」**。basename 口径实测失效——去掉 `.py` 的短名会被别的句子
  误命中，「零提及簇」被压到只剩 4 个、>=3 条的 0 个；而挑簇器「文档未提及
  = 未裁定」已连续七次误报。函数名才是 P2_13 各节真实的登记单位
  （「文件 L号（函数名）」格式）。工具 `probe_p2_35_batch29_unjudged.py`入库，
  产出全仓 **99 条**真新库存候选清单（JSON 落盘），整簇零记载的 6 个簇中
  本批取前两簇。

  **发现一：`otel_enabled` 是死配置**。`config.py:427` 声明了
  `otel_enabled: bool = False`，但**全仓 AST 零消费点**——唯一命中是
  `otel.py` 模块 docstring 的说明文字。`main.py:253` 的 `_init_otel` 只透传
  `settings.otlp_endpoint`（默认 `""`），从不读 `otel_enabled` ⇒ 运维改
  `OTEL_ENABLED=true` 不会有任何效果，而配置项存在本身让人误以为「关着是
  配置问题」。

  **发现二：otel 依赖双重不可达（方向与往批相反）**。`requirements.txt`
  零 opentelemetry 条目；`requirements.lock` 只有间接依赖
  `opentelemetry-api==1.45.0`（无 sdk/exporter/instrumentation/distro）；
  实测 `_check_otel_available()` → False、`init_otel(endpoint="")` → False
  （走 L71 提前 return）⇒ **7 条 handler 在交付形态下全部不可达**。
  这与第二十一/二十二批「双重外部阻断」同型但**方向相反**：那批是
  「接线即恒 0」，这批是「handler 永不触发，接线即假设施」。**判据修订**：
  给不可达路径接线不只是无价值，而是**制造「看起来有降级观测、实际永不触发」
  的假设施**——比不接线更危险，会让后续维护者误以为该路径已被覆盖。

  **发现三：`/health/startup` 把 OTel 失败记为 `ok`**。`main.py:253-262`
  的 `_init_otel` 调用 `init_otel(...)` 但**不return**，而 `init_otel` 所有
  失败路径都只`return False` 不抛 ⇒ `record_step_sync(..., fatal=False)`
  记为 `ok`（实测 `status='ok' error_type=''`）。这是第二十七批
  `init_sentry` 同型信号的**第二次出现**（共同模式：「调用方不检查返回 bool +
  被调用方只 return 不抛」），两次都属**行为变更而非接线**，已并入独立待办。

  裁定：otel.py S3（S 型：自报设施自身失败）+ P4（`ImportError`：三处
  `_instrument_*` 只 debug、`instrument_app` 是 `pass`，instrumentation 缺失
  只少一段 trace）；`_common.py` L184 为**第六批已接线的复核**（钉完整
  location 字面量防 `_typo` 型变异）+ D5（`float()` 脏数据探测，
  `continue` 跳过；E4 实证返回结构与正常态同形、`data_quality=="poor"`
  兜底因子仍在）。

  闸门 `TestP235Round13Batch29Declined`（12 条）：13 处存在性 + 12 处块级
  反向钉（已接线那条排除）+ 完整 location 字面量互锁 + `otel_enabled`
  **死配置 AST 钉** + 依赖未交付源码钉 + 三处 warning 文案见证 + 三处
  debug-only 钉 + 运行时四条（E1/E2/E3/E4）+ 文档登记。桶计数维持
  **W=97 / X=119**（分类器现场重算 13 条为 S3+P4+D5+W1，**无一条在 X 桶内**）。
  变异四条见 `mutate_p2_35_round13_batch29_result.log`。
  **M3 假绿事故（已修，方法论级）**：M3 把结构化因子的 `continue` 改成
  `break` 后闸门**竟全绿**——原 E4 只投单个脏值，两种实现行为完全相同，
  断言没覆盖「脏特征之后的正常特征是否仍被产出」这一真正的风险面。
  **根因：变异只翻转了实现，没翻转断言的真值空间**。已补①混合输入用例
  （脏 `stress_level` + 正常 `anxiety`，后者必须仍产出因子）②`continue`
  结构钉（AST 断言 handler 有 `continue` 且无 `break`/`return`）
  ③变异脚本 `mutate()` 加 `try/finally`——**无论 RED 还是假绿都必须还原**，
  否则残留变异污染工作树（M3 中断时确实在 `_common.py` 留下 `break`，
  靠 `git checkout --` 挽回）。
  **检索口径再次记账**：本批先试 basename 口径也失效（短名误命中，
  零提及簇被压到 >=3 条的 0 个），最终确立**以函数名为裁定检索单位**。
  **⚠️ 本条目的「发现二」已被第三十批推翻并重写**（见下条），原文保留作历史
  快照：错在把**本机 venv 的环境状态**当成交付形态。

- **第十三轮第三十批（第二十九批 CI 红事故复盘批，纯裁定，W=97 / X=119 不变）**：

  **事故**：HEAD `7bd9bcc` 的 `backend-coverage` **failure**（1 failed /
  6901 passed / 68 skipped），唯一红项是 E2
  `test_runtime_e2_otel_unavailable_and_returns_false`。

  **根因（第三条同族纪律）**：`opentelemetry-api==1.45.0` 在 lock 里的
  `# via` 是 **`fastapi`**（不是第二十九批文档写的 prometheus 链路）⇒
  **任何装了 fastapi 的环境（含 CI）顶层包都可导入**，而
  `_check_otel_available()` 只做 `import opentelemetry` ⇒ **这道门在交付形态
  下是开着的**。本机 venv 恰好没装 api（fastapi 0.135.3）⇒ 我测到 `False`
  并把它写成断言。
  **纪律：断言钉的必须是「交付形态下不变的事实」，不是「我这台机器上碰巧
  成立的状态」。** 这是继「源码字面量在 ≠ 运行时活着」「变异只翻转实现 ≠
  翻转真值空间」之后的第三条同族教训——三者都源于「把一个偶然成立的观测
  当成了不变量」。

  **裁定修正**：在 tempdir 造CI 等价环境（顶层 otel 可导入、sdk/exporter/
  instrumentation 全缺）逐条重算五项证据——①依赖门 → `True` ②空 endpoint
  → `False`（阻断在 L77，不是依赖门）③**配 endpoint 后 `otel.py:133` 的
  外层 except 真实可达**（V 型：`return False` + warning，失败如实上报）
  ④三处 `_instrument_*()` 调用行号**全部晚于** `_otel_initialized = True`
  ⑤`instrument_app`/`shutdown_otel` 在 `_otel_initialized=False` 时零日志、
  置 `True` 后有日志（反证闸门生效）。
  ⇒ **7 条不是「全部不可达」：L133 = V 型可达，其余 6 条 = P 型不可达**
  （被 `_otel_initialized` 闸门保护，而非被自己的 except 保护）。
  **净结果仍是 0 接线、桶计数不变**，但理由已换。
  **判据修订（取代第二十九批那条）**：不可达性**不能**由「依赖没装」推出，
  必须**逐条问它的进入路径被什么挡住**。

  **闸门修正（13 → 16 条）**：E2 重写为「tempdir 自造 CI 等价环境 + 断言
  依赖门为 True 与空 endpoint 返回 False 两条与运行环境无关的事实」；
  新增 E2b 反向钉（配 endpoint 必须命中 L133 并 warning，否则裁定需重估）、
  `test_instrument_calls_only_on_success_path`（顺序结构钉）、
  `test_instrument_app_and_shutdown_gated_by_initialized_flag`（闸门结构钉 +
  运行时反证）；`test_otel_dependency_not_delivered` 结论不变但**推理链换掉**，
  并新增钉「api 的 `# via` 是 fastapi」与「依赖门只 import 顶层包」两条。

  **变异四条**（`mutate_p2_35_round13_batch30_result.log`）：M1 把
  `_instrument_fastapi()` 提到成功标记之前 → **1 红**（正是新加的顺序钉，
  旧断言集对这次变异完全无感 ⇒ 证明「结构顺序」是原测试集缺的维度）；
  M2 删 `instrument_app` 闸门 → 3 红；M3 依赖门收紧为同时 import sdk → 5 红；
  M4 绕过空 endpoint 提前 return → 3 红。变异后 blob 哈希核对 `otel.py`/
  `_common.py` 与 HEAD 一致（无残留）。

  **历史快照不改**：P2_13 第二十九批节原文保留并加更正标记，符合「历史快照
  只追加、不篡改」。纯裁定批，`app/` 生产代码零改动。

- **第十三轮第三十一批（第三十批 CI 红事故复盘批，纯裁定，W=97 / X=119 不变）**：

  **事故**：HEAD `b1d4493` 的 `backend-coverage` **failure**（1 failed /
  6904 passed / 68 skipped），唯一红项是本批**新增**的
  `test_instrument_app_and_shutdown_gated_by_initialized_flag`。

  **根因：同一条纪律在同一批测试里被违反两次**。上一批刚把 E2 从「断言本机
  环境」改成「tempdir 造交付形态」，紧接着 E5 又写回「环境状态」——用
  「`_otel_initialized=True` 时日志数 > 0」反证闸门生效。本机未装 otel ⇒
  `from opentelemetry import trace` 失败 ⇒ `except Exception` ⇒ 1 条 warning；
  CI 经 fastapi 装了 api ⇒ import 成功 ⇒ 走 `hasattr(provider,"shutdown")`
  而 `ProxyTracerProvider` 无 `shutdown` ⇒ **零日志** ⇒ 断言红。
  **「刚立完的纪律在下一条测试就违反」本身是信号：纪律只停在文字层面，没有
  机制兜住。**

  **修法一（反证去环境依赖）**：不再数日志，改为自造 otel 包并让
  `trace.get_tracer_provider()` 记录调用次数——闸门生效时 provider 一次都不该
  被取，置 `True` 后必须被取。两条在装/不装 otel 的机器上都成立。

  **修法二（把 CI 变成本机可复现，机制兜底）**：新增
  `probe_p2_35_batch31_ci_env.py`，用 `PYTHONPATH` 注入 fake otel 让 pytest
  **进程启动起**就认为 otel 可导入，跑四轮：A 本机默认 17 passed / B CI 等价
  17 passed / **C 故意注入一条环境依赖断言 → 1 failed**（证明该环境**真能
  识别**环境依赖断言，B 的结论因此可信）/ D 还原后 17 passed。
  **C 轮是关键**：没有它，「B 全绿」可能只是探针失真。

  **修法三（形态构造本身也不能依赖环境）**：初版形态 A 用「过滤 sys.path 里的
  site-packages」屏蔽 otel，自验证 B 轮立刻红——屏蔽不了 `PYTHONPATH` 注入的。
  改用 `sys.meta_path` 拦截器抛 ImportError，与安装位置无关。

  **附带发现（裁定层面）**：「L133 可达」是**条件结论**。双形态实测：形态 A
  （完全没装）依赖门 False ⇒ 走 L71 提前 return，**进不去 L133**；形态 B（交付
  形态，顶层包在、sdk 不在）依赖门 True ⇒ 配 endpoint 后**命中 L133**。
  ⇒ 第三十批那句 V 型判定**以交付形态为前提**（该前提已由「api 的 `# via` 是
  fastapi」钉住）。**新纪律：可达性结论若依赖依赖形态，必须把那个形态钉成
  断言的前提，并在文档写明它是条件结论。**

  **读数**：闸门 16 → 17 条；变异四条重跑全 RED-OK/GREEN-OK（M1 1 红 /
  M2 删闸门 **3 红** / M3 依赖门收紧 **6 红**，比上轮多 1 正是新形态测试 /
  M4 3 红）；受影响测试合并跑（6 文件）**253 passed**。纯裁定批，`app/`
  生产代码零改动。

  **CI 结果**：`backend-coverage` **failure**（1 failed / 6905 passed /
  68 skipped，609s），唯一红项是 `tests/performance/
  test_observability_perf.py::test_response_time_7d_under_300ms`
  （`assert 421.86 < 300`）。判定**与本轮无关**：①失败项与前两批完全不同，
  说明本批修复已生效；②该文件自 `341f22c` 以来未被本轮改动，断言的是 5000 行
  聚合查询的墙钟耗时；③本机单独复跑 **1 passed**（8.08s）。转独立待办。

- **第十三轮第三十二批（1 接线，W=97→98 / S 36→35 / X=119 不变，总数 334 不变）**：

  **簇**：四簇 15 条，函数名级零记载 —— `app/api/v1/metrics_helpers.py` 4 +
  `app/core/celery_breaker.py` 4 + `app/services/user_data_service.py` 4 +
  `app/core/idempotency.py` 3。

  **接线 1 条**：`metrics_helpers.py:116` `_load_json` → `"api.metrics_helpers.
  load_json"`（S → W）。判据是**可客断言的同形性**（不是「日志不够响」）：
  产物损坏与产物不存在都返回 `None`，下游 `_extract_*` 都得 `{}` ⇒ Prometheus
  序列消失，Grafana 无法区分「没训过」与「产物坏了」。且与同文件
  `collect_ml_quality`/`drift`/`canary` 三处已接线路径**同族**（语义都是
  「真实产物读不到 ⇒ 序列消失」），本处不接即自相矛盾。
  **可达性按第三十批纪律核实**：`docker-compose.yml:155` 只读挂载
  `./backend/models`，实测该目录有 3 个真实 `metrics.json` ⇒ 文件存在 ⇒
  `OSError`/`JSONDecodeError` 可达（与第二十一批 scaler 相反）。

  **不接 14 条**：
  - `celery_breaker.py` 4 条 **P 型不可达** —— `requirements.txt` 有
    celery/redis、lock 有 celery/kombu/redis，实测 `_INFRA_EXCEPTIONS` 已含
    四类可选异常 ⇒ 四条 `except ImportError` 永不触发。这是第二十九批 otel
    同族但**方向相反**：那次我错把「本机没装」当交付形态，这次是「依赖已交付」
    真的不触发。
  - `user_data_service.py` 4 条 **D 型脏数据** —— 混合输入实测（脏
    `sleep_hours` + 正常 `heart_rate`/`steps`/`exercise_minutes`）脏字段只跳过
    自己，其余三项全部仍产出。这是第二十九批 M3 假绿教训的直接应用：只投单个
    脏值无法区分 `continue` 与 `break`。
  - `idempotency.py` 3 条 **W 复核** —— 三个 location 字面量齐全。

  **闸门**：新增 `TestP235Round13Batch32Wiring`（9 条），含 15 处存在性 +
  所属函数未漂移 + **块级反向钉**（8 条不得接线路径内禁现
  `record_silent_degradation`）+ location 完整字面量 + 交付物依赖钉 +
  运行时 E1/E2/E3 + 文档登记。桶计数棘轮断言同步 W 97→98、S 36→35。

  **读数**：见 `verify_p2_35_batch32_candidates.py`（MISSING=0）与
  `probe_p2_35_batch32_runtime.py`（四项证据全成立）；变异四条见
  `mutate_p2_35_round13_batch32_result.log`。

- **第十三轮第三十三批（1 接线，W=98→99 / G 8→7 / X=119 不变，总数 334 不变）**：

  **挑簇信号本批更换**：函数名级零记载只是粗排（`tasks/pdf_report.py` 的三个
  函数至今报零记载，但该文件早在 §1.9 就整簇裁过）。改用「候选文件 basename
  在三份审计文档全文出现 **0 次**」⇒ 12 个文件 15 条。

  **接线 1 条**：`user_upload.py:162` `_validate_mime_type` →
  `"api.user_upload.validate_mime_type"`（G → W）。判据是**同形性实测**：
  libmagic 抛异常时 MIME 校验被静默跳过，`_process_batch_file` 仍返回带 `url`
  的成功结果，只剩扩展名白名单兜底；对照组（MIME 不匹配）会返回 error ⇒
  断言有区分力。**同族互锁**：第十一批已为
  `services.file_security.clamav_dependency_missing_fail_open` 接线，语义完全
  相同（安全校验 fail-open 跳过 = 未校验按已校验处理）。分类器按「返回 None」
  把它粗判 G 属误判 —— 这里的 `None` 是**放行**不是拒绝。

  **不接 14 条**：`fire_forget_metrics.py` 2 条 S 型（可观测设施自身故障；且
  `record_silent_degradation` 与它**同走** `app.core.metrics`，实测阻断后计数
  0→0 ⇒ 接线即恒 0 假设施）；`db_breaker` 2 / `smtp_breaker` 1 / `ml_breaker` 1
  / `drift_detector` 1 共 5 条 P 型（sqlalchemy/asyncpg/fastapi/scipy 交付形态
  齐备）；`email_service.py:164` 分类器判 R、**人工裁定 V**（重试耗尽后
  `raise last_exc` 向上传播，实测抛 `SMTPException`）；`logging_config.py:235`
  S 型（日志设施自身启动失败，warning 已自报）；`_schemas.py` 2 / `deps.py` 1
  共 3 条 G 型 fail-closed（其中 `_schemas.py:63` 实为正常控制流）；两个
  job_store 的 `_cleanup_expired` 2 条 D 型（混合输入实测脏条目只跳过自己）。

  **闸门**：新增 `TestP235Round13Batch33Wiring`（11 条），含 15 处存在性 + 块级
  反向钉 + location 完整字面量 + **ClamAV 同族互锁** + 同源结构钉 + 运行时
  E1~E5 + 文档登记。桶计数棘轮断言同步 W 98→99、G 8→7。

  **读数**：见 `verify_p2_35_batch33_candidates.py`（MISSING=0）与
  `probe_p2_35_batch33_runtime.py`（E1~E6 六项证据全成立，含 E6 计数 0→1）；
  变异见 `mutate_p2_35_round13_batch33_result.log`。
  桶计数 **W=99 / X=119**。CI 10/10 success（含 backend-coverage）。

- **第十三轮第三十四批（1 接线，W=99→100 / X=119→118，总数 334 不变）**：

  **挑簇信号本批再换**：第三十三批的 basename 零记载口径**已耗尽**（剔除当批
  12 文件后剩 0 条），且它是**反向失效**——`cache.py`/`reports.py`/
  `inference.py` 这类短名被文档别处的同名串命中 ⇒ 假负。改用**函数名级
  零记载 − 第二十至三十三批已处理簇**并逐簇人工核对，剔除
  `core/model_engine/predict.py`（9 条，第十二批 + 第二十一批已裁）与
  `services/canary_fallback_monitor.py`（5 条，第九批已裁）⇒ 10 文件 12 条。

  **接线 1 条**：`aggregate.py:38` `_parse_detail_json` →
  `"services.observability.aggregate.detail_json_parse_failed"`（X → W）。
  判据：① **同形性（源码明文）** L37 `if detail_json else {}` ⇒ 损坏与
  「本来就没有 detail」返回完全相同的 `{}`；② **假数据**——脏条目**进入
  输出**而非被跳过（与 D 型的分水岭），实测 1 坏+2 好+1 空 ⇒ 输出 4 条、
  `totals.acquired` 只统计到 10；③ **可达性**——`OperationLog.detail` 是
  `Text, nullable=True` 且无 JSON 合法性 CHECK（同表其他四列都有 CHECK
  作对照）⇒ 非 JSON 可入库，**对称于第二十一批 scaler**；④ **同族互锁**——
  同文件 `_fetch_lock_memory_stats`（第六批）语义相同。

  **不接 11 条**：`aggregate.py:484` W 复核；`dedup.py:95` **M 型**（专用
  计数器 `alert_detail_parse_failed_total.inc(1, stage="dedup")` **实测真涨**
  0→1）；`dedup.py:103` **S 型**（保护该计数器自身，且与之同源）；
  `inference.py:348` **P 型**（九个 Gauge 全部定义在 `metrics.py` L538-567，
  交付形态齐备）；`inference.py:362` 与 `registry_auto_rollback.py:136` K 型；
  `kill_switch.py:109` S 型（可观测设施自身）；`registry_auto_rollback.py:138`
  C 型（清理路径已有 `exc_info=True` 自报）；`admin.py:619` S 型（
  `logger.exception` + `log_id=` 可追溯）；`rate_limit.py:142` F 型（回退原始
  签名是保守行为）；`rate_limit.py:198` 正常控制流（限流生效 → 429）。

  **闸门**：新增 `TestP235Round13Batch34Wiring`（13 条），含 12 处存在性 +
  块级反向钉 + location 完整字面量 + 同族互锁 + 结构钉（detail 列无 JSON
  约束 / 九个 Gauge 齐备 / 自研 Counter 形态）+ 运行时 E1~E5 + 文档登记。
  桶计数棘轮断言同步 W 99→100、X 119→118。

  **读数**：见 `verify_p2_35_batch34_candidates.py`（MISSING=0、FUNC-DRIFT=0）与
  `probe_p2_35_batch34_runtime.py`（E1~E6 全成立，E5 计数 3→4）；
  变异 7 条全 RED-OK/GREEN-OK（M1 4红 / M2 2红 / M3 1红 / M4 3红 /
  M5 1红 / M6 1红 / M7 2红），见
  `mutate_p2_35_round13_batch34_result.log`；受影响 19 个测试文件 504 passed。
  桶计数 **W=100 / X=118**。
