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
