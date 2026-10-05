# 变更日志

本文件记录项目的显著变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **纪事说明**：本仓库以里程碑方式聚合记录，所有日期均取自 git 提交历史
> （`git log --date=short`），非发布日历。当前版本号唯一权威源为
> `backend/app/core/config.py`（`app_version` 与 `RELEASE_CODENAME`）。

## [Unreleased]

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

## 2026-10 · 06：里程碑前遗留收口

> 承接上段「明确未做」中两项已推进的条目。

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
