# 变更日志

本文件记录项目的显著变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **纪事说明**：本仓库以里程碑方式聚合记录，所有日期均取自 git 提交历史
> （`git log --date=short`），非发布日历。当前版本号唯一权威源为
> `backend/app/core/config.py`（`app_version` 与 `RELEASE_CODENAME`）。

## [Unreleased]
### ROUND_44 · 配置来源唯一性：两处兜底默认值归一到 `Settings` + 同名 env 直读显式登记

- **背景**：ROUND_43 之后对 `backend/app` 全量 AST 扫描
  `getattr(settings, "<field>", <literal>)`，13 处中有 2 处兜底值与
  `Settings` 声明默认值分叉：`predict_structured` 的
  `structured_default_model` 兜底 `v1.20`（声明 `v1.23`）、`_model_roots`
  的 `model_dir` 兜底 `None`（声明 `models`）。settings 属性缺失或被替换时
  会静默使用第二个默认值，与声明值分叉——同一配置出现两个来源。
- **修复**：两处改为直接读取 `settings.structured_default_model` /
  `settings.model_dir`（`if raw:` 保留，空串行为不变）。真实 `Settings` 恒有
  这两个字段，故生产行为不变；剩余 11 处 `getattr` 兜底实测全部等于声明默认值。
- **第二来源登记**：与 `Settings` 字段同名的环境变量直读全仓共 3 处
  （`core/cache.py` 与 `monitoring/dedup_lock.py` 的 `REDIS_URL`、
  `core/sentry.py` 的 `SENTRY_DSN`），均为有意兜底；闸门内
  `ALLOWLIST` 显式登记理由，并钉「settings 优先」与
  「main 始终透传 `settings.sentry_dsn`」。
- **闸门** `backend/tests/test_p2_67_round44_config_source_uniqueness.py`
  15 例：兜底默认值无分叉（扫描器自证 ≥11 处可见）、两漂移点直接读取且
  禁止回退 `getattr`、声明默认值钉（`v1.23` / `models`）、同名 env 直读集合
  恰好等于 ALLOWLIST（精确 3 项、理由非空、过期豁免报错）、扫描器三读法自证、
  已知 env 读取可见、非 Settings 名不误报、redis settings-first 顺序、
  sentry 库级兜底 + main 透传。
- **变异** `backend/tests/tools/mutate_round44_config_source_uniqueness.py`
  9/9 被杀死（两处兜底回退、新增同名直读 ×2、允许项变过期、兜底值 20→21、
  main 透传断开、settings 优先失效、声明默认值被改），每条还原 sha 一致，
  恢复后 15 passed（log 已 `git add -f`）。
- **连带**：两处均为单行替换（行数不变），p2_11 锚点无平移；无新增 `raise`
  （`other_raise=356` 不变），#35 桶计数不变。README 后端用例
  7,705→7,720（新增 15 例）。
- **CI 读数**：`77e7aa8` 7 个 push workflow / 10 个 check-run 全 success；Coverage
  `40174215047`（07:49:10Z→08:06:03Z，16m53s）：backend-coverage **7365 passed /
  77 skipped / 278 deselected**（与收集数 7,720 自洽），覆盖率 **86.46%**
  （门槛 60%，TOTAL 25236 语句 / 3416 未覆盖），测试步 799.64s / 13:19，
  job 16m42s；frontend-coverage 1m48s、coverage-summary 6s。另有**定时**任务
  `Container Image Security Scan`（schedule，非 push 闸门）在同一 SHA 失败：
  `Scan Backend Image` 的 Trivy 扫描 exit 1；该任务自 2026-10-04 起连续失败
  （2026-10-11 / 10-18 同一 job 同样失败），属既有基线镜像漏洞，与本次改动无关。

### ROUND_43 · 配置消费真实性：两处路由阈值接线 + window 项裁定为显式预留

- **背景**：ROUND_42 之后对 `Settings` 做全字段 AST 消费面实测（119 个字段），
  仍有 3 项在 `backend/app/` 零消费。其中 `route_feature_coverage_threshold`
  （0.80）与 `route_lite_min_text_length`（20）在 `app/core/config.py` 声明为
  「v1.25 路由配置」，代码却硬编码同值——路由层一处、`predict_lite` 一处，
  改环境变量无效，与 ROUND_42 同类缺陷。第三项
  `registry_auto_rollback_window_seconds` 的「窗口」语义从未实现。
- **接线**：`_route_structured` 的覆盖率分支改读
  `settings.route_feature_coverage_threshold`，lite 文本门槛改读
  `settings.route_lite_min_text_length`；`predict_lite` 的短文本早退改读同一
  配置（第二处 20 硬编码）。默认值 0.80 / 20 不变 ⇒ 生产行为不变；
  `backend/.env.example` 登记两项。
- **预留裁定**：`registry_auto_rollback_window_seconds` 不实现窗口语义（会改变
  回退判定行为），也不删除（避免破坏运维配置面），改为显式预留：`config.py`
  注释与 `shadow_comparison_service.should_auto_rollback` docstring / 健康统计
  注释均改写为「进程内累计，窗口语义未实现」，回退判定逻辑零改动。
- **闸门** `backend/tests/test_p2_66_round43_config_consumption_truthfulness.py`
  16 例：默认值钉（`model_fields`，环境无关）、目标函数内不得再出现字面量
  0.80/20、运行时两态（覆盖率阈值 0.99→lite / 0.05→structured；文本门槛
  100→anxiety_only / 5→lite）、`predict_lite` 两态（高门槛走长度不足分支，
  低门槛进入模型装配并因假 `_load_model_async` 抛错落到
  `lite_model_unavailable`）、window 预留文档 + 零消费、全仓「Settings 字段
  零消费」棘轮（实测集合恰好等于 ALLOWLIST；扫描器自证可见 `otel_enabled`
  与两项已接线字段）、`.env.example` 登记。变异脚本 9/9 RED + 恢复绿。
- **连带**：`inference.py` 新增 `from app.core.config import settings`，使
  p2_11 batch34 候选表的 handler 锚点 348/362→350/364，同步
  `test_p2_11_round11.py` 正文与 batch34 校验工具；无新增 `raise`
  （`other_raise=356` 不变），#35 桶计数不变。README 后端用例
  7,689→7,705（新增 16 例，既有测试仅平移锚点、用例数不变）。
- **CI 读数**：`4554ff3` 7 个 workflow / 10 个 check-run 全 success；Coverage
  `40159553886`（03:48:17Z→04:12:52Z，24m35s）：backend-coverage **7350 passed /
  77 skipped / 278 deselected**（与收集数 7,705 自洽），覆盖率 **86.47%**
  （门槛 60%，TOTAL 25236 语句 / 3415 未覆盖），测试步 1245.37s / 20:45，
  job 24m25s；frontend-coverage、coverage-summary 亦 success。

### ROUND_42 · OTel 配置面真实性：`otel_enabled` 由死配置接线为真开关

- **背景**：`backend/app/core/config.py` 的 STAB-P2-009 配置块中，`otel_enabled`
  与 `otel_resource_attributes` 全仓零消费（AST 实测）。运维改环境变量毫无效果，
  属于已定性的缺陷类「配置项存在 ≠ 被消费 ⇒ 误导运维」。第二十九批把它记为
  独立待办 E1，本轮关闭。
- **接线**：`app/core/otel.py:init_otel` 新增 `enabled: bool = True`（保持库级
  直调既有行为）与 `resource_attributes: str = ""`；判定顺序 `enabled` →
  已初始化幂等 → 依赖门 → endpoint 空。`enabled=False` 打印独立文案
  `OpenTelemetry disabled by configuration (otel_enabled=False)` 并返回
  `SKIPPED`；三条跳过路径均不置 `_otel_initialized=True`。`app/main.py:_init_otel`
  透传 `enabled=settings.otel_enabled` 与
  `resource_attributes=settings.otel_resource_attributes`。
- **资源属性**：`"k=v,k2=v2"` 解析后注入 `Resource.create(resource_attrs)`；
  畸形项（缺 `=`、空 key）逐项跳过并 `logger.debug`，解析问题不把装配打成 `FAILED`。
- **行为变更（显式声明）**：运维「只配 `OTLP_ENDPOINT`、不设 `OTEL_ENABLED=true`」
  的部署由「追踪开启」变为「追踪关闭」。`backend/.env.example` 已按 `SENTRY_*`
  写法登记五个有消费的 OTel 项，并注明默认关闭与「需另装 SDK/exporter」。
- **闸门** `backend/tests/test_p2_65_round42_otel_config_truthfulness.py` 16 例：
  默认值、开关关（endpoint 非空 + SDK 全装仍不装配）、开关开 + endpoint 空、
  成功 / 装配失败、`/health/startup` 三态（skipped 不进 `failed_components`）、
  资源属性正常/畸形/注入 `Resource.create`、main 透传 AST、`.env.example` 登记、
  全仓消费点恰好 `main.py` 一处。变异脚本 8/8 RED + 恢复绿。
- **连带**：`test_p2_11_round11.py` 第二十九批 E1 结构钉反转为
  「消费点集合恰好等于唯一位置」，运行时钉改为开关两态；`otel.py` 行号锚点
  150/168/183/197/220/222/245 → 193/211/226/240/263/265/288，`main.py` 396→401；
  `test_p2_64` 的 `TestBoundaryInterlock` 反转为唯一消费位置互锁；batch29
  probe/mutate 同步（M1 换臂）。无新增 `raise`（`other_raise=356` 不变），
  #35 桶计数不变。README 后端用例 7,673→7,689。
- **CI 读数**：`fbcbce9` 7 个 workflow / 10 个 check-run 全 success；Coverage
  `40155324311`（02:40:07Z→03:04:49Z，24m42s）：backend-coverage **7334 passed /
  77 skipped / 278 deselected**（与收集数 7,689 自洽），覆盖率 **86.43%**
  （门槛 60%，TOTAL 25235 语句 / 3425 未覆盖），测试步 1237.23s / 20:37，
  job 24m32s；frontend-coverage、coverage-summary 亦 success。

### ROUND_41 · 论文增补 §0 检测目的论（根因未明的前置边界）

- **改动**：`docs/thesis/LIMITATIONS.md` 顶部新增 §0「检测的目的论：先于一切数字的
  边界声明」，把四条立场固化为可引用前提：检测 ≠ 诊断 ≠ 解释（输出仅作人工复核队列
  前置过滤）；只认最保守口径（文本泛化只认 groupwise [C-22]，泄漏 [C-19] 与
  `stress_only` [C-12 等] 禁作效果主张）；漏报优先（Recall 及 CI 与 F1 同权报告，
  双阈值安全网成本见 §3ter [C-34 ~ C-38]）；阈值 0.5 是价值承诺而非调参
  （拒绝挑优，保守校准 [C-28] 公开为诊断）。
- **不引入新数字、不改任何指标**；`verify_thesis_numbers.py` rc=0（台账 55 条 +
  引用纪律），本地复跑确认。
- **CI 读数**：`28c4d0e` **7/7 workflow success**；backend-coverage **7318 passed /
  77 skipped / 278 deselected**（与 7,673 收集数自洽），覆盖率 **86.41%**
  （TOTAL 25,218 语句 / 3,428 未覆盖），测试步 986.00s（16:25），job 20m16s，
  Coverage workflow 20m25s；frontend-coverage、coverage-summary 亦 success。

### ROUND_40 · OTel 启动自检真实性：三态可比，失败不再伪装成 ok/未启用

- **背景**：ROUND_39 收口时如实记账的同型缺陷——`main.py` 的 `_init_otel` 丢弃
  `init_otel` 返回值，而 `init_otel` 的 bool 同时表示「未启用」与「初始化失败」。
  后果是 `/health/startup` 无法区分「追踪已就绪」「SDK 没装 / endpoint 未配」
  「装配失败」，`/health/ready` 也不会因追踪失败降级。本轮只修这一条。
- **契约**：`app/core/otel.py` 的 `init_otel` 改为三态 `OtelInit.OK / SKIPPED / FAILED`。
  `SKIPPED` 只给两条前置未启用路径（顶层 `opentelemetry` 不可导入、`otlp_endpoint`
  未配置）；配置了 endpoint 但装配抛异常 → `FAILED`；已初始化幂等 → `OK`。
  失败 / 跳过路径均不置 `_otel_initialized=True`。
- **接线**：`main._init_otel` 提为模块级——`OK`→`None`、`SKIPPED`→`SKIPPED` 哨兵、
  `FAILED`→抛 `OTelInitError`；lifespan 仍以 `record_step_sync(..., fatal=False)`
  登记，失败被记 `failed` 但不阻断启动（R-006 同语义）。`/health/startup` 由此
  如实暴露 ok / skipped / failed；`FAILED` 使 `/health/ready` 显示 `degraded`
  （HTTP 仍 200），`SKIPPED` 不进 `failed_components`、不降级。
- **闸门** `backend/tests/test_p2_64_round40_otel_startup_truthfulness.py` 16 例：
  三态契约（空 endpoint / 依赖缺失 / 装配异常 / 成功 / 幂等）+ main AST 接线
  （模块级、SKIPPED 哨兵、FAILED 必须抛、`fatal=False`）+ 运行时驱动真实
  `main._init_otel`（failed / skipped / ok）+ `/health/startup` 序列化 +
  `/health/ready` 降级边界 + `otel_enabled` 死配置互锁。变异脚本 8/8 RED + 恢复绿。
- **连带**：`test_p2_11_round11.py` 第二十九批见证改钉三态（原 `is False` 断言）、
  E3 运行时从「记 ok」反转为「failed / skipped」；`otel.py` 行号锚点
  133/151/166/180/203/205/228 → 150/168/183/197/220/222/245，`main.py` 模块级
  OSError 379→396。`test_sec_p2_003...` 的三个旧 bool 契约用例同步更名/改断言；
  batch29/30 probe 与 mutate 脚本随契约更新。新增 raise 使 #34 `other_raise`
  355→356，已按棘轮同步 `docs/P2_11_ROUND11_AUDIT.md`。
- **边界**：`otel_enabled` 死配置（E1）保持零消费，未接线；Sentry 契约、
  `SKIPPED` 哨兵机制与 p2_63 闸门未改；instrumentation 内部 handler 裁定未动。
- **CI 读数**：`b101cd7` 的 7 个 workflow 全 `success`（Secret Scan / deployment-window-check /
  contract-tests / harness-tests / e2e-tests / Lighthouse CI / Coverage）；`backend-coverage`
  **7318 passed / 77 skipped / 278 deselected**（与 7,673 收集数自洽），覆盖率 **86.41%**
  （门槛 60%），job 24m40s（workflow 24m49s）；frontend-coverage 与 coverage-summary 亦 success。

### ROUND_39 · 启动自检真实性：Sentry 未启用不再谎报 ok

- **背景**：ROUND_13 第二十七批审计发现 `init_sentry` 的两条降级路径（未配置 DSN、
  `sentry_sdk` 不可导入）都是 warning + `return`，调用方 `record_step_sync(...,
  fatal=False)` 因此把启动状态记成 **`ok`** —— `/health/startup` 无法区分「Sentry 已就绪」
  与「Sentry 根本没启用」。该信号自第二十七批起作为独立待办挂账，本轮关闭。
- **机制**：`app/core/startup_status.py` 新增 `SKIPPED` 哨兵（`SkippedStep` 单例）；
  `record_step_sync` / `record_step_async` 见到哨兵即记 `skipped`
  （不进 `failed_components`、不触发 fatal），普通返回值仍记 `ok`。
- **契约**：`init_sentry` 返回 `bool`（True 已初始化 / False 未配置 DSN 或 SDK 不可用）；
  `app/main.py` 的 `_init_sentry` 提到模块级（可测），False 时返回 `SKIPPED`。
  `fatal=False` 与 R-006「监控降级不阻断启动」语义不变。
- **闸门** `backend/tests/test_p2_63_round39_startup_truthfulness.py` 15 例：哨兵机制
  （sync/async × skipped/ok、skipped 不进失败清单）、sentry 返回值三路径、
  main 接线（AST 返回 SKIPPED + 运行时 False→skipped / True→ok，并经
  `startup_check()` 验证 `/health/startup` 序列化结果）。变异脚本 8/8 RED + 恢复绿。
- **连带**：`test_p2_11_round11.py` 第二十七批见证改名为
  `test_runtime_init_sentry_failure_records_skipped`（原断言「记 ok」正是被修掉的缺陷），
  `sentry.py` 行号锚点 103/148/163 → 107/153/168（docstring 增 5 行）。
- **CI 修复（`2eab986` 红灯）**：`test_p2_11_round11.py` 的 batch36/37 仍用硬行号锚点，
  本轮源码改动使 `startup_status.py` 的 except handler 100→118、`main.py` 模块级
  OSError 371→379；同步候选表与 verify/probe/mutate 工具（`dff864b`）。
  本地全量 p2_11 233 例绿。
- **CI 收口**：`dff864b` **7/7 workflow success**（Coverage 24m32s；
  backend-coverage 7302 passed / 77 skipped / 278 deselected，总覆盖率 86.32%）。
- **未覆盖如实记账**：`init_otel` 有同型缺陷（`main.py` 丢弃返回值，且 False 同时表示
  「未配置」与「初始化失败」，语义需先拆分），留待后续单独立项。

### ROUND_38 · 排序确定性收口（ROUND_23b 同型风险清零）

- **背景**：ROUND_23b 修预警分页时记账「全仓另有 10+ 处单键排序同型风险」。ROUND_24/25
  已把 LIMIT/OFFSET 分页补齐唯一次级键；本轮清掉剩余**非分页但影响「选哪条 / 输出顺序」**
  的单键排序——13 个函数、16 处排序点。
- **生产修复**（统一补 `id` 次级键）：咨询师用户详情三条时间线（风险/评估/干预）、危机事件
  CSV 导出、活跃干预计划选取与任务顺序（`sort_order, id`）、风险报告近 20 条、预警判定
  「上一条评估」、内容审核历史、运维看板近期审计、异常检测「每用户最新样本」窗口、
  告警升级批处理、告警归档批处理、可观测性近期失败/flush/fired、生效静默列表、偏好品类
  top3（并列按品类升序）。
- **语义安全豁免**（不改，理由登记在测试）：`SystemConfig.config_key` /
  `WarningThreshold.level` 唯一列；`review_service` / `drift` 的存在性查询；anomaly
  扫描分组 cap。
- **闸门** `backend/tests/test_p2_62_round38_order_determinism.py` 22 例：6 个行为型
  （捕获生产方法真实下发的 SQL）+ 14 个 AST 结构见证（API 层难直接调用）+ 2 个豁免前提
  锚定（唯一约束被删即红）。变异脚本 9/9 RED + 恢复绿（含 M1–M4 行为+结构双杀）。
- 更正 ROUND_23b 测试 docstring 的「10+ 处待办」记账为「已清零」。
- **CI 修复（`3546235` 红灯）**：p2_51 分页闸门抓出两处本批自身缺陷——① 已修复的
  12 个站点仍留在 `PAGING_WHITELIST`（腐烂条目），全部移除；②
  `get_recommendations` 的 `GROUP BY category` 查询被单键判据命中，登记白名单并写明
  「分组后每组一行，`cnt DESC, category ASC` 已全序，`.limit(3)` 单页」。
  本地补跑 p2_51 + p2_50 + p2_62 共 48 例全绿。
- **CI 收口**：`2fe2249` **7/7 workflow success**（Coverage 24m17s；
  backend-coverage 7287 passed / 77 skipped / 278 deselected，总覆盖率 86.32%）。

### ROUND_35 · B1–B5：ROUND_00 审计遗留的测试/脚本缺陷收口

- **B1 跨平台写盘**：`v1_30/groupwise_ci.py` 写 json 固定 `newline="\n"`，消除
  Windows（CRLF）与已提交 LF 产物的字节差，sha256 口径恢复跨平台一致。
- **B2 恒真断言**：`test_p2_47_round19_m_batch2.py` 的「匿名化触及模型 ⊆ 导出清单」
  原实现拿全部 `ast.Name` 与对照表取交集，断言恒空（无效闸门）。改为从匿名化模块
  **AST 抽取 `app.models` 导入**做对照。新断言立即暴露未登记模型
  `RefreshTokenSession`——经查其仅含 `jti/expires_at/revoked_at`（安全凭证，无 PII），
  匿名化吊销会话是安全动作而非擦除个人数据；以显式 `security_only` 豁免登记，
  并加「豁免项必须真被导入」防陈旧豁免。
- **B3 断言生产实现**：`test_p2_50_round23b_warning_order_stability.py` 前两例不再
  自建 SQL 断言自己，改为用捕获型 DB 替身调用 `list_warnings` 生产方法，对**实际
  下发语句**断言 `ORDER BY created_at DESC, id DESC` 与 LIMIT/OFFSET 下推。
- **B4 显式降级**：`test_p2_56_round29_scaler_consistency.py` 的 artifacts 缺失 skip
  改为 `reason` 明写 data-machine-only gate（CI 跳过原因可见、不静默）；审计文档同步。
- **B5 数据不入库**：`test_p2_58_round31_eatd_scaffold.py` 新增
  `test_eatd_raw_data_not_tracked`，断言 `git ls-files data/external/eatd` 为空
  （预注册承诺：只登记形态、不分发数据）。
- README 后端测试计数校准 7,582→**7,620**（ROUND_36/37 新增 37 例 + 本轮 B5 的 1 例）。
- **CI 收口**：`2546cb2` **7/7 workflow success**（Coverage 23m08s；
  backend-coverage 7265 passed / 77 skipped / 278 deselected，总覆盖率 86.32%）。

### ROUND_37 · P1 融合消融（模态缺失下的等级翻转）

- 新增 `backend/scripts/modeling/eval/v1_37/fusion_ablation.py`：在**确定性分数网格**
  （三模态各 0/10/…/100，1331 组合，穷举）上用**真实生产 `FusionEngine`** 评估
  leave-one-modality-out 的 risk_level 翻转。产物 json + 脚本生成报告
  `docs/model-evaluation/FUSION_ABLATION_REPORT.md`。
- **数据基础诚实记账**：三模态无对齐真实数据（文本 MMPsy 8379 / 生理 depresjon 157 /
  结构化 PHQ-9 且即训练标签母体）⇒ 端到端融合消融**没有数据基础**，本轮明确不做；
  合成网格只验证融合层规则行为，禁作性能/贡献度证据。
- **三条发现**：① 三模态一致时消融稳健（翻转 ≤0.23、最大 1 级 [X-07]）；
  ② 分歧时剧烈，仅剩生理模态冲突层翻转率 0.86、最大 **4 级** [X-08]
  （redistribute_weights 把 0.15 权重的生理放大到 1.0）；③ worst case
  `(0,0,90)`：完整判 0 级（无风险）、仅生理判 4 级（危机）[X-09]。
  ⇒ 工程含义：单模态请求应降级处理，未改生产代码。
- **实测发现（死分支）**：`redistribute_weights` 的「权重全零时均分」分支不可达——
  `__init__` 先除零（ZeroDivisionError）。已写成钉死该事实的测试。
- 台账新增 X-07~X-09；闸门加独立复算（调生产引擎重算 + 分层/worst case 对拍 +
  「合成非性能」口径边界断言）。论文回填 RESULTS_CHAPTER §5bis、LIMITATIONS §3quater。
- 测试 `backend/tests/test_p2_61_round37_fusion_ablation.py` 18 例；
  变异 `backend/tests/tools/mutate_round37_ablation.py` **7/7 RED + 恢复绿**
  （含 5 个**生产代码**变异：redistribute 归一化/过滤、NaN 拦截、bool 拦截、空输入默认值）。

### ROUND_36 · P1 漏报安全网（双阈值规则评估）

- 新增 `backend/scripts/modeling/eval/v1_36/`（`safety_net_lib.py` 纯函数 +
  `safety_net_analysis.py` CLI）。规则：`p>=t_high` 直接预警、`t_low<=p<t_high`
  安全网强制复核、`p<t_low` 阴性；净 Recall 把安全网捕获的阳性计入「抓到」，
  复核负担单列，预警精确率只对直接预警负责。工作点标准**先定后扫**
  （净 Recall ≥ 0.80 且复核负担最小）。
- **三条结构性发现（本轮核心）**：① 漏报率与总负担只由 `t_low` 决定，
  `t_high` 完全不参与（恒等式 `负担 = P(p>=t_low)`、`净 Recall = 1 − FN率`，
  已数值核验）；② 因此双阈值成本与「单阈值直接下调到 t_low」**恒等**，
  唯一增益是预警精确率更高（0.6815 vs 0.2620）而非更省钱；
  ③ 安全网区间 `[0.11, 0.60)` 阳性率 0.1905 **低于**基准率 0.2163 ⇒ 无判别力。
- **诚实结论**：净 Recall 0.9845 的代价是 81.25% 样本进入人工流程，
  接近全员初筛 ⇒ **单独使用文本模态做漏报安全网在成本上不成立**；
  根因是文本概率低分区间信息量不足，可行方向是把安全网做在融合层（未做）。
- 台账新增 C-34~C-38；闸门 `verify_thesis_numbers.py` 加独立复算
  （flatnonzero 路径 + 恒等式/成本等价校验 + posix 路径断言）；
  论文回填 RESULTS_CHAPTER §4quater、LIMITATIONS §3ter、REVIEWER_QA Q11。
- 测试 `backend/tests/test_p2_60_round36_safety_net.py` 19 例；
  变异 `backend/tests/tools/mutate_round36_safety_net.py` **7/7 RED + 恢复绿**
  （含「NaN 逃逸」真缺陷：`NaN < target` 为 False 会让无阳性配置混进可行集）。


### ROUND_33 · P1 校准分析（Brier / ECE / MCE / calibration slope / DCA）

- 新增 `backend/scripts/modeling/eval/v1_33/calibration_lib.py`（纯函数库）与
  `calibration_analysis.py`（四单元 CLI）。**只读已落盘的逐样本 csv**，不跑模型、
  不读 metrics.json / registry 旧值；点估计与 bootstrap CI 共用同一套实现，避免
  「CI 一种算法、点估计另一种」的隐性不一致。
- 口径边界按 ROUND_27/30 的裁定保持：主口径 = 文本 groupwise OOF（n=8379 / 1277 组，
  唯一可引用泛化口径）；生理切分 n=157 为次级（小样本，引用处同句标注 n）；
  两个 transfer 单元（文本×OOD 2523、生理×Kaggle 10000）**仍为压力测试**，
  禁作外迁引用。
- 主要读数：文本 groupwise Brier 0.1280 [0.1184, 0.1376]、ECE 0.0855 [0.0710, 0.1069]、
  校准斜率 1.3466（>1 ⇒ 概率偏保守/欠自信，与阈值读数 Recall 0.5375 自洽）；
  DCA 显示模型净获益在阈值 [0.03, 0.99] 优于「全员干预」。
- 接入台账 C-26 ~ C-33 与论文素材包（RESULTS_CHAPTER §4ter、LIMITATIONS §3bis、
  REVIEWER_QA Q9/Q10）；`verify_thesis_numbers.py` 增加校准/DCA 的**独立复算**
  （ECE 用显式区间遍历、slope 用 Nelder-Mead 最小化 logloss，与库的 Newton 路径不同）。
- 测试 `backend/tests/test_p2_59_round33_calibration.py` 16 例；变异
  `backend/tests/tools/mutate_round33_calibration.py` **7/7 全部 RED + 恢复绿**
  （含「DCA 符号翻转在 FP=0 时测不出」这一测试覆盖缺陷的修复记录）。

### ROUND_33 修复 · 跨平台路径缺陷（CI 抓出）

- **缺陷**：首版提交（`09564c5`）的 `calibration_analysis.json` 的 4 个 `source`
  字段在 Windows 上生成（`str(Path)` ⇒ 反斜杠），Linux CI checkout 下 4 个 calib
  单元全部误报「source 不存在」⇒ `backend-coverage` **3 failed / 7224 passed**
  （该 job 首轮被并发 push 取消，重跑后才暴露；本地 Windows 全绿是假象——
  路径分隔符属于交付形态）。
- **修复**：生成端 4 处改 `.as_posix()` 并重生成 json（数值零漂移，仅 4 行路径）；
  闸门与测试的路径解析做反斜杠归一化；测试新增形态钉断
  `assert "\\" not in u["source"]`。
- **验证**：p2_59+p2_55 20 passed；`verify_thesis_numbers.py` rc=0；新闸门
  变异（生成端退回 `str()`）RED→字节还原→GREEN，日志
  `backend/tests/tools/mutate_round33_pathfix_result.log`。
- **CI 结果**（修复提交 `d93e23b`）：**10/10 success**（24m39s）——
  `backend-coverage` 由 3 failed/7224 passed 转绿，缺陷闭环。

- 待发布内容在此累积。

---

## 2026-09：工程治理与供应链收敛（2026-09-01 ~ 2026-09-30）

>补记说明：本段于 2026-10-05 补记，起点为 `986b9d1`（2026-08-24）。
> 此前 CHANGELOG 自该提交起未收口，9 月共 48 笔非 merge 提交首次入库。
> 日期取自 `git log --date=short`，非发布日历。

### 供应链与依赖治理

- 安全扫描红灯清零：定位 trivy 告警真实根因为基础镜像自带
  setuptools/msgpack 旧版元数据，升级后清零剩余 HIGH（09-15）；
  容器扫描告警按风险接受处理并记录论证（09-15）
- Dependabot 忽略 pip/npm 大版本升级，并记录 `requirements.txt` 被整段重写的
  限制；关闭 pip 版本更新（09-16）
- 修复 dependency-scan 假门禁（空扫描即通过 + 退出码不可用）（09-16）
- `requirements.in` 下限对齐至 `requirements.txt` 的 CVE 修复下限（09-16）
- 锁定 SQLAlchemy <2.1 + 建库显式 psycopg2 驱动（09-26）
- 前端依赖批量升级（Dependabot 合入，09-16 ~ 09-17）：element-plus 2.14.5、
  vite 6.4.3、vitest 4.1.11、dompurify 3.4.15、@playwright/test 1.63.0、
  @types/node 22.20.2、workbox-window 7.4.1、puppeteer 24.43.1
- 后端覆盖率门禁 40% → 60%（09-24）

### CI 门禁修复

- 修复 v1.39-alerting-e2e 端口漂移：改为从 compose 动态解析宿主端口，
  消除硬编码端口与 compose 两套事实导致的持续红灯（09-16）
- 修复 db_breaker 单例分裂及 5 项过期/环境依赖测试（09-12）
- 显式声明 starlette-testclient 依赖，修复 contract-tests / Coverage 失败（09-12）
- 修复重构后失效的源码结构断言与返回值解包（09-12）

### 审查整改

- 第三轮审查收口：GDPR 存在性误判、日志注入、**生产弱 JWT 密钥**
  （引入 `_validate_jwt_secret_strength`，生产要求 ≥32 字符且字符类别 ≥2）（09-30）
- 修复审查发现的 5 项 P0 与 3 项 P1（09-30）
- P0-P3 工程硬化（09-23）

### 模型与可观测

- 双语文本模型兄弟泄漏定量 + 组级去泄漏真口径；回退模型按组级真口径重训
  并刷新评估元数据（09-08）
- 模型评估证据与降级可观测性（09-30）

## 2026-10：安全与可观测性收口（2026-10-01 ~ 2026-10-05）

> 本段随开发滚动补记。
> 里程碑收口日定为 **2026-10-31**：CHANGELOG 自 `986b9d1`（08-24）起未收口，
> 积压 122 笔提交、6 周（节奏 2.9 提交/天）。按 4 周窗口收口，避免继续积压。
> 跨到 10-06 的进展见下节。

### 依赖漏洞清零

- 重生成 `requirements.lock` 清零 **68 条依赖漏洞**；
  补漏 `requirements-dev.lock`（20+ 条 → 1 条无修复版）；记录SEC-DEP 清零台账（10-04~ 10-05）
- `dompurify` 3.4.15 → 3.4.16修补 XSS（GHSA-p98j-92pf-mc4p）。
  按`dependency.scope` 取证确认 54 条 Dependabot 告警中 **52 条为 development
  scope（不进生产产物）**，仅 2 条 runtime需处理（10-05）
- axios 升出 GHSA 漏洞区间（09-24，见上）

### CI 门禁修复

- **v1.39-alerting-e2e 红灯闭环**（09-23 起的持续红灯，非间歇故障）：
  根因为 workflow 占位 `JWT_SECRET_KEY` 仅 26 字符，低于 09-30 新增的
  生产强度下限（32）→ `Settings()` 抛错 → `alembic_migrate` exit 1。
  修复密钥 + 补失败取证（原先只抓 backend/grafana 日志，漏掉唯一报错的
  migrate 容器，artifact 仅 254 字节）；新增 8 条闸门测试（10-05）
- 修复 Lint 与 E2E Smoke 门禁失败（10-05）

### 阻断项与严重项修复（代码审查驱动）

- **PII 盲索引迁移**引用不存在的 `app_config` 表 → 改用应用层
  `compute_blind_index`；空 email 存量不再编造 hash（10-05）
- **幂等占位值** `"1"`（合法 JSON 标量）被误当首次响应重放 → 改为非法 JSON
  占位 + dict 守卫（10-05）
- **三处跨层反向依赖**（core→services / services→api / tasks→api）→ observability
  下沉 + API 层 `__getattr__` 兼容转发（10-05）
- **告警 P1→P0 升级后 severity 不回写**导致状态机永久卡死 → `apply_escalation`
  统一兜底 + 确定性时钟消除时序 flake（10-05）
- `is_latest` 补部分唯一索引（`uq_risk_assessments_latest` /
  `uq_warning_notifications_assessment`）+ 新迁移（10-05）
- 前端可空字段 `.toFixed()` 致结果卡**白屏丢数据** + CSV 出现 `"NaN%"`
  （10-05）

### 可观测性接线（此前监控资产空转）

- **Sentry 接上业务调用点**（此前 `init_sentry` 正常但零业务调用点）：
  预警推送重试耗尽（全系统后果最重 = 漏报）/ 批量漏报汇总 /
  模型产物清理保护集解析失败（误删在用模型 → 推理 503）（10-05）
- **Celery `request_id` 传播**（合规审计缺口）：原先仅 HTTP 中间件写ContextVar，
  任务在独立 worker 进程 → 日志 `req_id`恒为 `-`，无法回答"某次风险评分由
  哪次请求产生"。经 `before_task_publish` / `task_prerun` / `task_postrun`
  三信号补齐（10-05）
- 指标递增失败日志 debug → **warning**（6 处）：原为双重静默 ——
  指标失败使 Grafana 曲线变平（看似"降级率 0%"），日志又仅 debug（10-05）
- `daily_intervention_check` **超时丢失当日全部 TaskExecution**：
  原为单事务，`soft_time_limit` 超时即全量回滚 → 改为按 plan 粒度提交
  （幂等依赖 `uq_task_execution_task_user_date`）（10-05）

### 性能

- `admin_service_stats` 12 条串行 count → 1 条 SQL（仪表盘首屏）；
  语义等价性在真实 PG 15.12 上逐项验证（12/12 一致）
- `intervention_service.get_active` 消除 N+1
- ML 缓存键加**模型指纹**（mtime+size）：修复模型热替换后最长 60s 内返回
  旧模型 `risk_score` / `risk_level`（10-05）

### 模型与评估

- P2-1 结论反转：MiniLM **不换**（10-04 误判为"换"因基线做差）；
  置信度阈值收敛到唯一事实源
- BERT 权重归档 + 禁用实验入口（指向已归档权重必然失败）；
  镜像 transformers 决策 + 修正相关事实错误（10-04）
- P2-2 DeepSeek 第二意见**不做**（消融证明无独立判别力）；
  离线评估脚本与 API key 读取已就绪备查（10-05）

### 明确未做（附理由）

- **前端 45 个 vue-tsc 存量类型错误**：实测根因在 Element Plus 库侧
  （`DefaultRow = Record<PropertyKey, any>`，且 `el-table-column` 未把泛型
  `T` 暴露给插槽），只能逐处 `as` 断言、分散 15 个文件 →
  触止损线停止，**维持现状 + 保留棘轮门禁**（`vue-tsc-baseline.mjs`
  `BASELINE=45`，实测存量未恶化）。不用 `as any` 压掉，否则门禁失去意义（10-05）
- **`tracing.inject_trace_into_headers` 出站 trace 传播**：全仓出站仅
  2 个文件且均为投递第三方 Alertmanager，W3C traceparent 无消费方，
  技术收益 ≈ 0 → 关闭，改由 payload 带 `request_id`（10-05）

---

## 2026-10 · 06：里程碑 v1.33-hardening-complete 封口

> 承接上段「明确未做」中两项已推进的条目，并完成里程碑收口。
> `RELEASE_CODENAME` 由 `v1.32-observability-complete` 递增为
> **`v1.33-hardening-complete`**（SSOT：`backend/app/core/config.py:23`；
> 递增前已验证全仓唯一声明处、无残留引用、别名 `RELEASE_VERSION` 等价）。
> CHANGELOG 补记范围 `986b9d1`（08-24）至本次封口 —— 积压 **122 笔提交 / 6 周**
> （节奏 2.9 提交/天）一次性入库，按主题聚合而非逐条罗列。

### 依赖安全

- `echarts` 5.6.0 → **6.1.0**（GHSA-fgmj-fm8m-jvvx / CVE-2026-45249, XSS）。
  跨大版本人工规划迁移（`dependabot.yml` 已全局忽略 `semver-major`，
  Dependabot 不会自动开PR）→ 逐条核对官方 v6 升级指南，**破坏面为零**：
  默认主题变更零影响（11 处 series 全部显式指定 `itemStyle.color`，
  不依赖默认色板）、未用 `outerBoundsMode` / `label.rich`、
  已是 ESM `import * as`、zrender 6 由 npm 自动带入。
  体积实测对照：628.7KB → 667.7KB（+39KB / +6.2%），tree-shaking 未退化。
  验证：typecheck 仍 45（零新增）/ build ✓ / 1165 passed（10-06）

### 可观测性

- **escalation 事务持有时长埋点就位**（为量化前置，见上段最后一条）：
  新增 `escalation_notify_duration_seconds{result}`（单次 `notifier.send()`
  耗时）与 `escalation_cycle_duration_seconds`（一次 `apply_escalation()`
  ≈ 事务持有时长）。设计要点：`result` 区分成功/失败（**慢且失败最糟**）、
  buckets 显式扩至 120s/300s（默认上限 10s 会让webhook 全落 `+Inf`）、
  失败路径在 `finally` 记录、**指标上报绝不抛异常**（P1 关键路径）。
  **判读标准与改动约束已写进代码注释**：P99 < 1s → 只加监控不改结构；
  达秒级 → 按批commit 切分；且 `alert.detail` 更新与 `alert_escalated`
  日志**必须同事务**，不可为缩短事务而拆开。
  剩余：待生产采集一个完整周期分布后决策（10-06）

---

### 相对 v1.32 的增量摘要

| 维度 | 内容 |
|---|---|
| 安全 | `requirements.lock` 漏洞清零（68 条）、`dompurify` 3.4.16、`echarts` 6.1.0 |
| 正确性 | PII 盲索引迁移、幂等占位值、告警 P1→P0 状态机卡死、scheduler 超时丢当日 TaskExecution、前端可空字段白屏 |
| 可观测 | Sentry 接业务调用点、Celery `request_id` 传播、指标失败日志提至 warning、escalation 事务持有埋点 |
| 性能 | admin 12→1 条 SQL、`get_active` 去 N+1、ML 缓存键加模型指纹 |
| 架构 | 解三处跨层反向依赖（observability 下沉 + API 层兼容转发）|
| 文档 | CHANGELOG 补记 2026-09 / 2026-10 两段 |

### 里程碑遗留（仍未关闭，均带触发条件）

- **前端 45 个 vue-tsc 存量类型错误**：根因在 Element Plus 库侧
  （`DefaultRow = Record<PropertyKey, any>`，且 `el-table-column` 未把泛型 `T`
  暴露给插槽），只能逐处 `as` 断言、分散 15 个文件 → 触止损线停止，
  维持现状 + 保留棘轮门禁（`vue-tsc-baseline.mjs` `BASELINE=45`，实测存量未恶化）。
  **禁止用 `as any` 压掉**，否则门禁失去意义。
  重启条件：下次前端迭代，或 Element Plus 升级后插槽类型有变化。
- **`tracing.inject_trace_into_headers` 出站 trace 传播**：**已判定关闭**。
  全仓出站仅 2 个文件且均为投递第三方 Alertmanager，W3C `traceparent` 无消费方，
  技术收益 ≈ 0 → 改由 webhook payload 带 `request_id`。
  重启条件：出现第一个需要跨服务追踪的**我方**服务调用时。
- **escalation 持事务结构优化**：埋点已就位
  （`escalation_notify_duration_seconds{result}` 与
  `escalation_cycle_duration_seconds`），**但生产数据尚未采集**
  （两个指标未接入任何看板/告警规则，且埋点提交 `536463b` 尚未部署）。
  判读标准已写进代码注释：P99 < 1s → 只加监控不改结构；达秒级 → 按批 commit 切分。
  无论结论如何，`alert.detail` 更新与 `alert_escalated` 日志**必须同事务**。
- **Dependabot 54 条告警**：全部来自 `frontend/package-lock.json`
  （`scope`：development 52 / runtime 2），与 Python 后端无关。
  52 条 devDeps 传递链不进生产产物，不逐条升级。

---

## 2026-08 · 下旬：安全治理、RBAC 扩展与供应链加固（2026-08-15 ~ 2026-08-17）

- 新增平台管理员 `super_admin` 独立角色：后端权限矩阵 / 租户守卫 / DB 约束，前端路由 / 菜单 / 权限 / i18n 全触点（08-15）
- P0 安全修复：Grafana 告警 webhook 密钥泄漏占位符化 + 独立卷渲染，密钥不进 git（08-15）
- 后端 / 前端全量审核 P1/P2 收口：租户越权、漂移检测、认证语义、内存防护；图表实例泄漏、PII 清理盲区、错误码匹配等（08-15）
- 供应链安全治理：gitleaks 接入 CI 与本地钩子、第三方 action 按 SHA 钉扎、workflow 权限最小化、接入 Dependabot 自动升级（08-15）
- CI 门禁治理：pr-quality-gates 移除假门禁（CI-AUDIT-04）；e2e 冒烟 wrong-credentials 场景伪造 401 补齐 CORS 头（08-16）
- BERT Hub 下载 revision 钉扎接线，消除构建期下载漂移风险（08-16）
- 前端依赖升级（Dependabot 合入）：vue 3.5.41、vue-i18n 11.4.8、@vue/language-core 3.3.9、vitest 4.1.10（08-17）

## 2026-08 · 中旬：生产加固与模型验证深化（2026-08-06 ~ 2026-08-10）

- 生产问题修复：Grafana 数据源可用性与 observability PG 时间参数类型、前端 HTTPS 白屏（CSP script-src 对齐）、注册 409 冲突的默认租户种子引导（08-06 ~ 08-07）
- v1.40 后续收口：关闭 33 项审计延期 P3/P4（权限 / 可观测 / 流式导出 / i18n / UX，含 37 项单测）+ VISUAL P3/P4 16 项 + lint/ruff 清零（08-08）
- JWT RS256 切换路径收口：生产豁免 secret 校验 + 密钥路径启动校验（08-08）
- 双语文本模型零泄漏训练 + 语言路由收口（08-09）
- 新数据域外探针验证：combined_data 42K 真实域外评估；训练产物影子对拍 + 自动回退（R1/R2）（08-09）
- CI：actions 升级至 Node 24 版本系列、Codecov 接入 CODECOV_TOKEN、sklearn 兼容性声明统一回 1.5.0、safety 扫描修复（08-10）

## 2026-08 · 上旬：告警链路修复与 E2E 稳定化（2026-08-02 ~ 2026-08-04)

- H-AUDIT-01 Grafana 告警链路修复：prometheus 服务编排 / datasource 指向 / 规则 job 名对齐，消除通知黑洞（08-02）
- 观测性与契约修复：空闲误报不发样本（NoData→OK）、PG 兼容 strftime/GROUP BY、金丝雀安全、契约测试对齐真实路由（08-02）
- 容器供应链扫描（trivy 类型化 inputs）+ CodeQL v4 权限收紧（08-02）
- e2e 大规模稳定化：禁用 Service Worker、serve 开启 SPA 回退、种子开关环境变量对齐（SEED_ENABLED→ENABLE_SEED）、401 注入补 CORS 头与 OPTIONS 预检放行（08-04）
- WebSocket 兼容修复：/ws 支持 query user_id 与尾斜杠路径；pdf/jobs 权限按 created_by 放宽为登录用户（08-04）

## 2026-07 · 下旬：模型优化核心与告警基建（2026-07-21 ~ 2026-07-30）

- 模型优化核心落地：漂移监控、影子模式、评分适配、M2-BERT 预测器 + 金丝雀运维脚本（07-29）
- 新增 ML 与金丝雀测试套件：漂移检测 / 融合优先级 / 影子模式 / 特征契约等（07-29）
- Grafana 告警规则 / 联系人 / 数据源 provisioning 配置入库（07-29）
- 引入 `requirements.lock` 全量传递依赖锁定（SEC-P2-005），收敛 Docker / CI / 本地三方版本声明（07-29）
- 仓库治理：清理冗余跟踪内容（第三方库 / 运行时状态 / 违例 outputs），README 面向 GitHub 展示精修（07-29 ~ 07-30）

## 2026-07 · 中旬：审计闭环、多租户与运营能力（2026-07-10 ~ 2026-07-16）

- Phase 1~5 能力交付：
  - 多租户基础设施（Tenant 模型 + 上下文中间件 + 查询隔离）、租户管理 API、租户级审计查询 API（07-12）
  - RBAC 租户绑定、品牌配置、数据导出与越权测试（07-12）
  - 内容治理 API（审核 / 下架 / 恢复）与运营看板 API（服务指标聚合）（07-12）
  - 模型预测暂停开关（kill switch）与模型验证基础设施（临床指标、置信区间、公平性检查）（07-11）
- UI/UX 审计收口 ISS-151~164：i18n、响应式、design tokens、a11y（WCAG AA 对比度）、移动端弹窗等（07-10）
- 前端管理端扩展：AdminReportsPage / AdminObservabilityPage / AdminMonitoringPage / AdminCanaryPage 等五大页面与路由 / 权限 / i18n 对齐（07-08 ~ 07-09）
- 测试体系强化：后端覆盖率提升至 87%，修复 10+ 个存量失败用例，契约测试（schemathesis content-type 文档化）独立工作流（07-10 ~ 07-16）
- 安全与性能 P1/P2 修复 + 服务层 / API 层大文件拆分（MAINT-P2-001/002）+ production build 循环依赖 TDZ 修复（07-15）
- CI 工作流大规模修复：coverage 门禁校准、deployment-window-check、seeded fixtures 等（07-11 ~ 07-16）

## 2026-06 · 仓库奠基（2026-06-22）

- 初始化仓库并完成代码审核修复与技术债务处理
- 完成 P2 级别代码质量改进
