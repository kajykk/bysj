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
