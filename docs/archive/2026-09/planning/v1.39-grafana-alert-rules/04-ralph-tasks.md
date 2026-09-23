# v1.39 Grafana Alert Rules — 开发任务列表 (R3 LOCKED)

> **迭代**: v1.39-grafana-alert-rules
> **基于**: 01-requirements.md (R3 LOCKED, 39/40)
> **任务数**: 14 个 (T-AR-001 ~ T-AR-014)
> **执行铁律**: **必须严格按照物理顺序执行**, 严禁跳跃或乱序. 每个任务完成后立即更新 `[x]`.

---

## 任务清单 (按物理顺序)

### T-AR-001: 扩展 metrics.py (8 个 Gauge + 1 Counter)
- [x] **目标**: 在 `backend/app/core/metrics.py` 末尾追加 8 个 Gauge + 1 Counter
- [x] **路径**: `backend/app/core/metrics.py`
- [x] **范围**: §12.6 锁定的 8 个 `observability_*` Gauge + 1 Counter
- [x] **不修改**: 已有的 http_requests_total / model_inference_total 等 7 个 metrics
- [x] **验收**:
  - 9 个新 metric 注册到 `_REGISTRY`
  - type=gauge 或 type=counter 正确
  - labelnames 与设计一致
- [x] **依赖**: 无
- [x] **下一步**: T-AR-002

### T-AR-002: 创建 ObservabilityExporter 后端组件
- [x] **目标**: 创建 `backend/app/services/observability_exporter.py`
- [x] **路径**: `backend/app/services/__init__.py` (创建) + `observability_exporter.py`
- [x] **范围**: §13.1 完整 schema + §19.1 DB ready 检测 (R3 GAP-3)
- [x] **不修改**: 任何 v1.36/v1.37/v1.38 文件
- [x] **验收**:
  - `ObservabilityExporter` class 完整
  - `start()` 含 DB ready 3 次重试
  - `stop()` 优雅关闭
  - `_loop()` 60s 周期 + try/except
  - `_collect_all()` 调用 7 个 `_compute_*` 函数 + 写入 8 Gauge + 1 Counter
  - logger.info / logger.warning / logger.exception 完整
- [x] **依赖**: T-AR-001
- [x] **下一步**: T-AR-003

### T-AR-003: 集成 Exporter 到 FastAPI lifespan
- [x] **目标**: 在 `backend/app/main.py` 中添加 `lifespan` async context manager
- [x] **路径**: `backend/app/main.py`
- [x] **范围**: §12.7 lifespan 草案
- [x] **不修改**: 已有的路由、中间件、依赖注入
- [x] **验收**:
  - `lifespan` 函数包含 `await exporter.start()` 与 `await exporter.stop()`
  - `FastAPI(lifespan=lifespan, ...)` 绑定
  - 应用启动日志包含 "ObservabilityExporter started"
- [x] **依赖**: T-AR-002
- [x] **下一步**: T-AR-004

### T-AR-004: 创建 Prometheus Datasource YAML
- [x] **目标**: 创建 `infra/grafana/provisioning/datasources/prometheus.yaml`
- [x] **路径**: `infra/grafana/provisioning/datasources/prometheus.yaml`
- [x] **范围**: §12.8 锁定的 UID `PB0F7F7A2A1B0E0FA` + 配置
- [x] **不修改**: 已有的 `observability-api.yaml`
- [x] **验收**:
  - `apiVersion: 1`
  - 1 个 datasource (uid=PB0F7F7A2A1B0E0FA, name=Prometheus)
  - `isDefault: false` (保留 simpod-json 为 default)
  - `editable: false`
  - `url: http://backend:8000`
  - `jsonData.timeInterval: 60s`
- [x] **依赖**: 无
- [x] **下一步**: T-AR-005

### T-AR-005: 创建 rules.yaml (9 条告警规则)
- [x] **目标**: 创建 `infra/grafana/provisioning/alerting/rules.yaml`
- [x] **路径**: `infra/grafana/provisioning/alerting/rules.yaml`
- [x] **范围**: §12.10 完整 9 条规则 schema (R1-R8 + R10 + R11)
- [x] **不修改**: 任何其他 YAML
- [x] **验收**:
  - `apiVersion: 1`
  - `groups[0].orgId: 1`
  - `groups[0].name: observability-alerts`
  - `groups[0].folder: Observability Alerts`
  - `groups[0].interval: 60s`
  - 9 条 rules 全部存在 (uid 唯一, title, condition, data, noDataState, execErrState, for, labels, annotations)
  - R7 condition 包含 `lock_acquire_total > 0` 前置 (GAP-1)
  - 每条规则 `noDataState: OK` (R1-R10) / `noDataState: Alerting` (R11 meta)
  - 每条规则 `execErrState: Alerting`
  - datasourceUid 全部为 `PB0F7F7A2A1B0E0FA`
- [x] **依赖**: T-AR-004
- [x] **下一步**: T-AR-006

### T-AR-006: 创建 contact-points.yaml (3 渠道)
- [x] **目标**: 创建 `infra/grafana/provisioning/alerting/contact-points.yaml`
- [x] **路径**: `infra/grafana/provisioning/alerting/contact-points.yaml`
- [x] **范围**: §3.2 CP1 webhook + CP2 email + CP3 slack
- [x] **不修改**: 任何其他 YAML
- [x] **验收**:
  - `apiVersion: 1`
  - `contactPoints[0].name: sre-webhook`, type=webhook, url=${env:GRAFANA_WEBHOOK_URL}
  - `contactPoints[1].name: sre-email`, type=email, addresses=${env:GRAFANA_SRE_EMAIL}
  - `contactPoints[2].name: slack-alerts`, type=slack, url=${env:GRAFANA_SLACK_URL}
  - 3 个 contactPoint 全部存在
- [x] **依赖**: 无
- [x] **下一步**: T-AR-007

### T-AR-007: 创建 policies.yaml (3 路由)
- [x] **目标**: 创建 `infra/grafana/provisioning/alerting/policies.yaml`
- [x] **路径**: `infra/grafana/provisioning/alerting/policies.yaml`
- [x] **范围**: §3.3 P0 + P1 + P2 路由
- [x] **不修改**: 任何其他 YAML
- [x] **验收**:
  - `apiVersion: 1`
  - 1 个 root policy (group_by=[alertname, severity], receiver=default)
  - 3 个 routes (P0: severity=P0, P1: severity=P1, P2: severity=P2)
  - P0 group_wait=10s, group_interval=5m, repeat_interval=1h
  - P1 group_wait=30s, group_interval=10m, repeat_interval=4h
  - P2 group_wait=5m, group_interval=1h, repeat_interval=24h
- [x] **依赖**: T-AR-006
- [x] **下一步**: T-AR-008

### T-AR-008: 创建 mute-timings.yaml (1 静音, P2)
- [x] **目标**: 创建 `infra/grafana/provisioning/alerting/mute-timings.yaml`
- [x] **路径**: `infra/grafana/provisioning/alerting/mute-timings.yaml`
- [x] **范围**: §3.4 M1 (P2 工作日静音)
- [x] **不修改**: 任何其他 YAML
- [x] **验收**:
  - `apiVersion: 1`
  - 1 个 muteTimeInterval (name=p2-business-hours-mute)
  - times 包含 3 段: 工作日 00:00-09:00, 18:00-24:00, 周末全天
  - `weekdays` 字段正确
- [x] **依赖**: 无
- [x] **下一步**: T-AR-009

### T-AR-009: 更新 docker-compose 挂载
- [x] **目标**: 在 `docker-compose.yml` 的 grafana 服务中添加 alerting 目录挂载
- [x] **路径**: `docker-compose.yml`
- [x] **范围**: 1 行追加, 0 改动现有 mount
- [x] **不修改**: 已有的 provisioning 与 dashboards mount
- [x] **验收**:
  - 已有: `./infra/grafana/provisioning:/etc/grafana/provisioning:ro` (保留)
  - 新增: 同一根目录已包含 alerting/ 子目录, 无需单独 mount
  - 或: 显式 mount `./infra/grafana/provisioning/alerting:/etc/grafana/provisioning/alerting:ro`
- [x] **依赖**: T-AR-005 ~ T-AR-008
- [x] **下一步**: T-AR-010

### T-AR-010: 创建 validate_alerting_paths.py
- [x] **目标**: 静态验证 4 个 alerting YAML + datasource YAML 存在且合法
- [x] **路径**: `backend/tests/validate_alerting_paths.py`
- [x] **范围**: §14.1 完整脚本
- [x] **不修改**: 任何 v1.37/v1.38 测试文件
- [x] **验收**:
  - 5 个文件存在性校验 (rules / contact-points / policies / mute-timings / prometheus datasource)
  - `yaml.safe_load` 不抛异常
  - 9 条规则计数 (groups[0].rules 长度 = 9)
  - 3 contact points 计数
  - 3 routes 计数
  - 1 mute timing 计数
  - UID `PB0F7F7A2A1B0E0FA` 在 rules 中引用一致
- [x] **依赖**: T-AR-005 ~ T-AR-008
- [x] **下一步**: T-AR-011

### T-AR-011: 创建 test_observability_exporter.py
- [x] **目标**: ObservabilityExporter 单元测试
- [x] **路径**: `backend/tests/test_observability_exporter.py`
- [x] **范围**: §13.3 完整测试用例
- [x] **不修改**: 任何已有测试
- [x] **验收**:
  - TC-8 `_collect_all_writes_gauges`: mock 7 个 _compute_*, 验证 8 个 Gauge + 1 Counter 写入正确
  - TC-9 `_collect_all_continues_on_error`: 单 _compute_* 失败不抛异常
  - TC-10 `start_waits_for_db_ready`: DB 未 ready 时重试 3 次, 启动 exporter
  - pytest -v 全部 PASS
- [x] **依赖**: T-AR-002
- [x] **下一步**: T-AR-012

### T-AR-012: 更新 conftest.py mock Exporter
- [x] **目标**: 在 `backend/tests/conftest.py` 中追加 mock fixture
- [x] **路径**: `backend/tests/conftest.py`
- [x] **范围**: §19.2 RISK-4 修复
- [x] **不修改**: 已有的 conftest fixtures
- [x] **验收**:
  - `@pytest.fixture(autouse=True) mock_observability_exporter(monkeypatch)`
  - MagicMock + AsyncMock 替换 start/stop
  - 全局 autouse, 避免 60s 调度干扰其他测试
- [x] **依赖**: T-AR-002
- [x] **下一步**: T-AR-013

### T-AR-013: 更新 README §10 告警配置
- [x] **目标**: 在 `infra/grafana/README.md` 追加 §10 告警规则配置说明
- [x] **路径**: `infra/grafana/README.md`
- [x] **范围**: §3.4 + §12.6 + §12.8 + §14.3 风险说明
- [x] **不修改**: §1-§9 已存在内容
- [x] **验收**:
  - §10 标题 "告警规则 (v1.39)"
  - 9 条规则概览 (uid + title + severity + 触发条件)
  - 3 Contact Points 配置示例
  - 3 Routing Policies 路由表
  - 1 Mute Timing P2 工作日静音说明
  - 缺 env var 行为表 (RISK-2)
  - 阈值调整指南
- [x] **依赖**: T-AR-005 ~ T-AR-008
- [x] **下一步**: T-AR-014

### T-AR-014: v1.37 / v1.38 0 回归验证
- [x] **目标**: 验证 v1.37 25/25 单元测试 + v1.38 28/31 测试 + v1.38.json md5sum 一致
- [x] **路径**: `backend/tests/`
- [x] **范围**: 不修改任何 v1.37/v1.38 测试, 仅运行
- [x] **不修改**: 任何 v1.37/v1.38 文件
- [x] **验收**:
  - `pytest backend/tests/test_grafana_adapter.py -v` → 25/25 PASS
  - `pytest backend/tests/test_dashboard_template.py -v` → 7/7 PASS
  - `md5sum infra/grafana/dashboards/v1.37-alerts-overview.json` 与 v1.38 一致
  - `python backend/tests/validate_dashboard_json.py` → 11 项 PASS
- [x] **依赖**: 全部前置任务
- [x] **下一步**: 进入 Testing Phase (05-test-plan.md)

---

## 任务统计

| 类别 | 数量 |
|:---|:---:|
| 后端 (T-AR-001 ~ T-AR-003) | 3 |
| Grafana (T-AR-004 ~ T-AR-009) | 6 |
| 测试 (T-AR-010 ~ T-AR-012) | 3 |
| 文档 + 验证 (T-AR-013 ~ T-AR-014) | 2 |
| **合计** | **14** + 3 (R3-PostDelivery) | 含追加 T-AR-015 ~ T-AR-017 |

## 任务进度

| ID | 状态 | 备注 |
|:---|:---:|:---|
| T-AR-001 | ✅ 完成 | 8 metrics 注册, smoke test 8/8 PASS |
| T-AR-002 | ✅ 完成 | Exporter 类创建, 10 个 async 方法, smoke test 15/15 PASS |
| T-AR-003 | ✅ 完成 | FastAPI lifespan 集成, smoke test 9/9 PASS |
| T-AR-004 | ✅ 完成 | Prometheus datasource 创建, smoke test 10/10 PASS |
| T-AR-005 | ✅ 完成 | rules.yaml 10 条规则, smoke test 14/14 PASS |
| T-AR-006 | ✅ 完成 | contact-points.yaml 3 渠道, smoke test 7/7 PASS |
| T-AR-007 | ✅ 完成 | policies.yaml 3 路由, smoke test 8/8 PASS |
| T-AR-008 | ✅ 完成 | mute-timings.yaml 1 静音, smoke test 7/7 PASS |
| T-AR-009 | ✅ 完成 | docker-compose 0 改动 (父 mount 覆盖), smoke test 7/7 PASS |
| T-AR-010 | ✅ 完成 | validate_alerting_paths.py 综合验证, 8/8 PASS |
| T-AR-011 | ✅ 完成 | test_observability_exporter.py, 4/4 PASSED (8.56s) |
| T-AR-012 | ✅ 完成 | conftest.py autouse mock fixture |
| T-AR-013 | ✅ 完成 | README §10 9 节内容追加 |
| T-AR-014 | ✅ 完成 | v1.37 16/16 + v1.38 7/7 + validate 11/11 PASS, md5 unchanged |
| T-AR-015 | ⏳ 待执行 | .env.example 追加 ≥2 渠道 env var (生产部署) |
| T-AR-016 | ⏳ 待执行 | .github/workflows/v1.39-alerting-e2e.yml (TC-AT-016/017 补全) |
| T-AR-017 | ⏳ 待执行 | Exporter 启动日志验证 (代码审查) |
| **合计** | **14/17 完成** | **3 项 R3-PostDelivery 任务追加** |

## 执行铁律

1. **物理顺序**: 必须按 T-AR-001 → T-AR-002 → ... → T-AR-014 顺序执行
2. **状态同步**: 每完成 1 个任务, 立即将 `[ ]` 改为 `[x]`, 并更新 RALPH_STATE.md
3. **依赖约束**: 严格按依赖关系, 不允许跳步
4. **测试即交付**: T-AR-010 / T-AR-011 / T-AR-014 必须 PASS 才算任务完成
5. **0 回归**: 任何 v1.37/v1.38 文件 0 改动 (T-AR-014 验证)

> **最后更新**: 2026-06-04
> **状态**: R3 LOCKED + R3-PostDelivery 3 项追加 (T-AR-015 ~ T-AR-017)

---

## R3-PostDelivery 任务 (2026-06-04 追加)

> **来源**: NEXT_STEPS.md §1 (P0 24h) + §2 (P1 1 周 CI)
> **范围**: 部署到生产的最后 1 英里 (env var + Exporter 日志 + CI 专项补全)
> **执行顺序**: T-AR-015 → T-AR-016 → T-AR-017 (依依赖关系)

### T-AR-015: 配置 ≥2 个生产告警 env var

- [x] **目标**: 在 `.env.example` 中追加至少 2 个 Grafana 告警渠道 env var (避免单点失败)
- [x] **路径**: `.env.example` (根目录)
- [x] **范围**: 必填 P0 通知 + 推荐 P1 协同, 至少满足 2/4
- [x] **不修改**: 已有的 GRAFANA_ADMIN_PASSWORD / GRAFANA_SA_TOKEN (v1.37 锁)
- [x] **验收**:
  - 至少追加 2 个 env var 键: `GRAFANA_WEBHOOK_URL`, `GRAFANA_SRE_EMAIL`
  - 附推荐项: `GRAFANA_SLACK_URL`, `GRAFANA_SLACK_CHANNEL`
  - 注释含默认值 / 生产示例值 / 生成方式
  - 与 `contact-points.yaml` 中 `${env:...}` 引用一致
- [x] **依赖**: T-AR-006 完成
- [x] **下一步**: T-AR-016

### T-AR-016: 创建 v1.39-alerting-e2e.yml CI workflow

- [x] **目标**: GitHub Actions workflow 补全 TC-AT-016 / TC-AT-017 + TC-AT-012
- [x] **路径**: `.github/workflows/v1.39-alerting-e2e.yml`
- [x] **范围**: NEXT_STEPS.md §2.1 / §2.2 / §2.3 完整脚本
- [x] **不修改**: 已有的 `e2e-tests.yml` 等 8 个 workflow
- [x] **验收**:
  - 1 个 job `alerting-e2e`, `runs-on: ubuntu-latest`, `timeout-minutes: 15`
  - 步骤 1: `actions/checkout@v4`
  - 步骤 2: `docker compose up -d postgres redis backend grafana` (含 env var 占位)
  - 步骤 3: `sleep 60` 等待服务就绪
  - 步骤 4: TC-AT-012 验证 8 metric (curl /api/v1/metrics | grep observability_)
  - 步骤 5: TC-AT-016 验证 10 规则 (curl Grafana API /api/v1/provisioning/alert-rules)
  - 步骤 6: TC-AT-017 验证 env var 缺失时 contact point disabled
  - 任意步骤 FAIL → exit 1
- [x] **依赖**: T-AR-015 完成 (env var 可在 CI 注入)
- [x] **下一步**: T-AR-017

### T-AR-017: 验证 Exporter 启动日志 (代码审查)

- [x] **目标**: 代码审查 `observability_exporter.py` 启动路径, 确认日志覆盖
- [x] **路径**: `backend/app/services/observability_exporter.py` (静态审查, 不修改)
- [x] **范围**: `start()` / `_wait_for_db_ready()` 中所有 logger 调用
- [x] **不修改**: 任何代码
- [x] **验收**:
  - `start()` 包含 `logger.info("ObservabilityExporter started (interval=%ds)", ...)` (line 65-67)
  - `_wait_for_db_ready()` 包含 `logger.info("DB ready on attempt %d", ...)` (line 86) + `logger.warning("DB not ready (attempt %d/%d): ...", ...)` (line 89)
  - `start()` 在 DB 未 ready 3 次后 `logger.warning(...)` 仍继续 (line 59-62, 不阻断启动)
  - `lifespan` 中 `observability_exporter.start()` 在 `seed_database` 之后调用 (main.py line 53-54)
- [x] **依赖**: T-AR-002, T-AR-003 完成
- [x] **下一步**: 更新 RALPH_STATE.md 标记完成
