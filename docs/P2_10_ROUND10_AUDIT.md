# P2 第十轮审计清单（#37 + #32 角色余量 + CSV 三处 + #38）

- 生成时间：2026-10-14（无变异窗口内生成，脚本 `backend/scripts/scan_p2_10_roles_be.py` / `scan_p2_10_fe38.py`）
- 判定标准：内容集合完全相同才算重复；仅重叠词不算；路由/类型/模板/CSS/存储键字面量与角色语义不同，不收编

## 汇总

| 项 | 规模 | 结论 |
|---|---|---|
| #37 前端 helper | 行为判定 15 语句 / 14 文件 | 新建 `isAdminRole/isStaffRole/isUserRole`，改调；类型/模板/CSS/path 豁免 |
| #32 后端收编 | 25 处 | 服务层 `operator_role=`/`==`/SQL filter/`seed` 改调 `USER_ROLE_*` |
| #32 CSV 三处 | 3 文件 | 改调 `csvEscape`（纯去重，无注入面） |
| #38 全称注释 | BE 507 / FE 290 标记注释中筛全称子集 | 清单逐条验证测试/调用点 |

## #37 前端裸判定收编集（15 语句）

| 文件 | 行 | 原写法 | 改法 |
|---|---|---|---|
| `App.vue` | 31 | `['user','counselor','admin','super_admin'].includes(role)` | `isKnownRole(role)`（白名单语义，新增） |
| `BottomNav.vue` | 53/62 | `role==='admin'\|\|'super_admin'` / `==='counselor'` | `isAdminRole` / `isUserRole` 取反链 |
| `HelpCenter.vue` | 203-204 | 同上三段式 | `isAdminRole` / `role==='counselor'`→helper |
| `useLayoutMenu.ts` | 136-138 | 三个 `===` | helper 三连 |
| `MainLayout.vue` | 111/112/127 | 路径选择三段式 | helper（路径字面量保留） |
| `router/guard.ts` | 18-20 | 四个 `===` | helper |
| `ForbiddenPage.vue` | 36-38 | 三段式 | helper |
| `CounselorReviewListPage.vue` | 285 | `==='admin'\|\|'super_admin'` | `isAdminRole` |
| `EvalResultCard.vue` | 200 | `==='admin'\|\|'counselor'` | `isStaffRole`（新增：admin+counselor） |
| `useModelTrainingData.ts` | 28 | `==='admin'\|\|'super_admin'` | `isAdminRole` |
| `ProfileCard.vue` | 73-75 | 三个 `===` | helper |
| `BindingCard.vue` | 94 | `!== 'user'` | `!isUserRole` |
| `UserSettingsPage.vue` | 8/12 | `=== 'user'` ×2 | `isUserRole` |
| `useOnboarding.ts` | 92-96 | `case 'user'/'counselor'/'admin'` | 保留 switch（分支体不动，仅 case 值改常量？——决定：case 标签改常量，行为不变） |
| `LayoutHeader.vue` | 136 | `props.currentRole \|\| 'user'` | `USER_ROLE_USER` 常量 |
| `LoginPage.vue` | 261 | `role: 'user' as const` | `USER_ROLE_USER` 常量 |

豁免（登记）：`types/auth.ts` 类型并集、`api/auth.ts` 类型、`stores/auth.ts` storage key + 类型、`router/index.ts` path/`meta.role` 数组（守卫消费端已用 helper）、模板 `value="user"`（表单选项值，后端枚举对齐）、`data-role` CSS、`EmptyState` 变体名、`CounselorUserDetailPage v-if="user"`（变量名非字面量比较）。

## #32 后端收编集（25 处）

- `counselor_service_binding.py:70/84/131/147` `operator_role="counselor"`、`211` `!= "counselor"`、`262/346` `="user"`（7）
- `counselor_service_consultation.py:61/105`、`group.py:41/144`、`warning.py:170/231`（6）
- `intervention_service.py:352/393`、`warning_service.py:155/180/278` `operator_role="user"`（5）
- `review_service.py:320` 三元 `"admin"/"counselor"`（2 值 1 处）
- `admin_service_log.py:135/137/139/141` SQL filter 比较（4，`.label()` 别名不动）
- `admin_service_stats.py:48` SQL where（1）
- `anomaly_detection_service.py:323` `in_(["admin","counselor"])`（1）
- `admin_service_template.py:56/109` 默认值 `operator_role="admin"`（2，改常量默认值）
- `auth_service.py:83` `role="user"`（1）
- `tasks/scheduler.py:184` `User.role=="user"`（1）
- `seed.py:598/605/614/664/804/808`（6，造数脚本：改调常量，行为不变；`"username":"admin"` 非角色不改）
- 合计：7+6+5+1+4+1+1+2+1+1+6 = 35？——去重 `review 320` 计 1 处双值、`anomaly 323` 计 1 处双值，`seed 664/804/808` 比较 3 处 + 传参 3 处。最终以闸门扫描归零数为准，此处记 35 hits / 约 30 语句（提示词"25 处"为第九轮人工口径，机器口径略大，差异来自 `intervention/warning/scheduler/auth` 几处第九轮未计入——本轮一并收编，不缩范围只扩）。

豁免（登记）：`require_role("…")` Depends 参数（API 层 50+ 处，装饰器参数语义，动则全端点签名，移 #34/#36 治理轮）；`target_type="user"`（审计目标类型）；`.label()` 别名；响应 dict 键（`admin_service_log 147-150` 行的 `"user": int(...)`、`anomaly 89-90` 阈值表键、`auth 172` —— 键名是 API 响应字段/查找键，不是角色判定）；`prefix/tags`；`tenant_query.py` doctest 示例；`tenant_context.py:80` 子域名集合；`counselor_service_user.py:35` 注释内字面量。

## #32 CSV 三处（纯去重）

- `views/user/components/PhysioTab.vue:314`、`views/user/components/composables/useTextPredictionHistory.ts:130`、`views/user/components/structured-steps/usePredictionHistory.ts:74`：均已调 `sanitizeCellForExcel` + 引号转义，与 `csvEscape` 语义等价 → 改调 SSOT。安全面无变化，报告不写"修复注入"。

## #38 全称语义注释（筛选中，方法）

- 全集 BE 507 / FE 290 标记注释太多，收敛到含全称词（必然/恒/永远/不会/保证/一定/所有/仅）且描述行为的子集，逐条验证"测试或调用点"。清单见本文件附录（扫描脚本第二版产出后补）。
- 已知书面保留：RES-P1-004（`_flushed_buffer`）、`bertDisabled` 下线 UX——有注释有依据，不动。

## 附录：扫描器自证（防假闸门）

- 后端扫描器命中 128（含 SSOT 定义 4 + 豁免类约 90），收编集 35 hits 非零 → 非"报 0"情形。
- 前端扫描器命中 100，行为判定 15 语句非零。
- 变异自证（回退实验时做）：临时加回一处裸字面量 → 闸门必须红。

## 附录：全称注释清单同步（95→96，第十二轮第四批）

- 新增 1 条：`backend/app/core/audit.py:66`
  `# P2-33 第四批修复：tenant_id 必须落列。修前只进 detail，列恒为模型默认，…`。
- 含全称词“恒为”，其语义为陈述修复前后的确定性行为差异（列恒为默认 vs 落列），有行为闸门 `TestRecordAuditTenantColumn` 作证，非空断言。
- 闸门 `test_inventory_ratchet_be` 同步 95→96。

## 附录：全称注释清单同步（96→97，第十二轮第六批）

- 新增 2 条（均在 `backend/app/core/audit.py`，因给 `record_audit` 补
  `default=str` 容错而引入）；同时 `backend/app/tasks/scheduler.py` 少 1 条
  （原「default=str 只会让异常值退化成其字符串形式」注释被改写），净 +1：
  - `backend/app/core/audit.py:73`
    `# default=str 只会让异常值退化成其字符串形式，详情仍可人工复盘」）；`
    （引用 scheduler 原注释，陈述 `default=str` 的降级语义）
  - `backend/app/core/audit.py:75`
    `# TypeError 冒泡到调用方。detail 仍是 JSON 对象（调用侧闸门保证）。`
- 行为闸门作证（非空断言）：
  - `:73` 的「只会让异常值退化成字符串」由
    `tests/tasks/test_scheduler.py::TestStaleWarningReminderImpl` 三个用例作证
    （它们传 MagicMock 值，无 `default=str` 会直接 TypeError——本批实锤 3 failed）；
  - `:75` 的「detail 仍是 JSON 对象」由
    `tests/test_p2_12_round12.py::TestAuditDetailJsonDownstream::
    test_record_audit_detail_is_never_a_string` 作证。
- 闸门 `test_inventory_ratchet_be` 同步 96→97。

## 附录：全称注释清单同步（97→98，第十三轮第一批）

- 新增 1 条：`backend/app/core/cache.py:152`
  `# 各消费点只会看到"没有客户端"而不知根因，必须在此计数。`
  （`_get_redis_client` 初始化失败 handler 内，含全称词"只会"）。
- 两侧账：新增 +1，无删除，净 +1（97→98）。
- 语义与作证（非空断言）：该注释陈述"客户端初始化失败时，各消费点
  （观测缓存/告警去重/任务存储/ws 推送）只能看到 `get_redis_client()`
  返回 None，拿不到根因"，因此根因信号必须在 cache 层计数。行为闸门：
  `tests/test_p2_11_round11.py::TestP235Round13Batch1Wiring::
  test_cache_client_init_failure_increments_counter`（`from_url` 抛异常 →
  `core.cache.redis_client_init_failed` 计数器 +1，真实变异红过）。
- 闸门 `test_inventory_ratchet_be` 同步 97→98。

## 附录：全称注释清单同步（98→99，第十三轮第十四批）

- 新增 1 条：`backend/app/core/model_registry_v2.py:189`
  `# registry，训练资产的丢失不会体现在任何接口返回值上。`
  （`_load_registry` 的整体损坏 handler 内，含全称词"不会"）。
- 两侧账：新增 +1，无删除，净 +1（98→99）。
- 语义与作证（非空断言）：该注释陈述"注册表整体损坏时 `ModelRegistryV2` 以空
  dict 启动，而 `ModelRegistryV2.registry` 之外没有任何返回值/标志能表明历史记录
  曾经存在"。行为闸门：
  `tests/test_p2_11_round11.py::TestP235Round13Batch14Wiring::
  test_four_paths_increment`（写入非法 JSON 后构造实例 → 断言
  `registry == {}` 且 `core.model_registry_v2.registry_file_unparsable` 计数 +1；
  真实变异 M1/M2 红过）。
- 同批另三条注释（safe_pickle 两条环境加固、registry 部分加载）经副本差分复核
  **零命中**（用词未触发检测器），非漏账。
- 闸门 `test_inventory_ratchet_be` 同步 98→99。

## 附录：全称注释清单同步（99→100，第十三轮第十五批）

- 新增 1 条：`backend/app/services/model_predict/fusion.py:84`
  `# stable 版本，且响应里不会带 canary_routed 标记 —— 与「路由决策就是`
  （`predict_fusion` 的灰度路由 except 内，含全称词"不会"）。
- 两侧账：新增 +1，无删除，净 +1（99→100）。
- 语义与作证（非空断言）：该注释陈述"灰度路由决策失败时 `canary_routed` 保持
  False，响应体因此**不会**携带 `canary_routed` 标记"，即失败态与「路由决策本来
  就是稳定版」在响应层面不可区分。行为闸门：
  `tests/test_p2_11_round11.py::TestP235Round13Batch15Wiring::
  test_two_paths_increment`（patch `canary_manager.decide_version` 抛异常 +
  可用的假 `AsyncSessionLocal`，断言计数器 +1 且 `decide_version` 确被调用；
  真实变异 M2 红过）。
- 同批另两条注释（main.py 侧车审计、inference.py 模型指纹）经副本差分复核
  **零命中**，非漏账。
- 闸门 `test_inventory_ratchet_be` 同步 99→100。

## 附录：全称注释清单同步（100→102，ROUND_16 模型验证证据补强）

- 新增 2 条，无删除，净 +2（100→102）。均为 ROUND_16 新增模块的行为断言注释：
- ① `backend/app/ml/fusion_ablation.py`（配对 bootstrap 内）
  `# 成对重采样：两臂用同一套索引，保证配对结构`。
  含全称词“保证”。行为依据：实现为**同一组** `rng.choice` 索引同时施加于两臂
  （`paired_delta_auc_ci`），配对结构是 ΔAUROC 配对 CI 的定义性要求；行为闸门
  `tests/test_p2_40_model_validation_round16.py::TestT2FusionAblationGuards`
  （`test_paired_delta_zero_when_arms_identical` 同臂 Δ 恒 0 +
  `test_paired_delta_excludes_zero_on_consistent_gap` 一致缺口 CI 不覆盖 0）。
- ② `backend/app/ml/model_validation.py`（DCA 区间过滤）
  `# 区间判定用**原始 t**（不被 round 扰动），自定义网格的边界点才不会被
  四舍五入挤出临床区间`。
  含全称词“不会”。行为依据：区间过滤改用循环内原始 `t` 而非 curve 行的
  round 后值（ROUND_16 修复的舍入边界缺陷）；行为闸门
  `TestT1DcaEce::test_dca_bad_clinical_range_raises`（区间非法显式抛错）
  与 `test_dca_empty_range_reports_false_not_pass`（无点可查时汇总为 False，
  不默认放行）。
- 变异见证：上述两条所属闸门族在 `mutate_p2_40_round16.py` 中被真实变异
  打红（M6 DCA 公式符号翻转、M8 ΔCI 判据恒真均 RED-OK）。
- 闸门 `test_inventory_ratchet_be` 同步 100→102。
