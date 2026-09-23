# v1.39 Grafana Alert Rules — 下一步建议 (NEXT STEPS)

> **基于**: v1.39 DELIVERY_REPORT.md (2026-06-03)
> **目标**: 指导后续工作 (生产部署 / CI 补全 / 下一迭代)

---

## 1. P0 - 立即执行 (24 小时内)

### 1.1 部署到生产环境

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 后端: 应用 metrics.py + observability_exporter.py
# 3. Grafana: 复制 5 个 YAML 到生产环境
# 4. 重启后端 (Exporter 启动, 8 metric 暴露)
docker compose restart backend
sleep 5

# 5. 启动 Grafana (含 10 规则加载)
docker compose up -d grafana
sleep 30

# 6. 验证 (5 min)
python tests/validate_alerting_paths.py --check-promql
curl -s http://localhost:8000/api/v1/metrics | grep observability_ | wc -l
```

### 1.2 配置生产环境变量

至少配置 2 个渠道的 env var (避免单点失败):

```bash
# 必选 (P0 通知)
GRAFANA_WEBHOOK_URL=https://hooks.pagerduty.com/services/XXXXX
GRAFANA_SRE_EMAIL=sre-alerts@company.com

# 推荐 (P1 协同)
GRAFANA_SLACK_URL=https://hooks.slack.com/services/XXXXX
GRAFANA_SLACK_CHANNEL=#sre-alerts
```

### 1.3 监控 Exporter 自身

Exporter 启动后, 检查日志:
```bash
docker compose logs backend | grep ObservabilityExporter
# 期望: "ObservabilityExporter started (interval=60s)" + "DB ready on attempt 1"
```

---

## 2. P1 - 1 周内执行 (CI 专项)

### 2.1 补全 TC-AT-016 (E2E Grafana 启动 + 9 规则加载)

在 CI (GitHub Actions / GitLab CI) 中执行:

```yaml
# .github/workflows/v139-alerting-e2e.yml
name: v1.39 Alerting E2E
on: [push, pull_request]
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start services
        run: docker compose up -d
      - name: Wait for backend + grafana
        run: sleep 60
      - name: Verify 8 metrics
        run: |
          METRICS=$(curl -s http://localhost:8000/api/v1/metrics | grep -c "observability_")
          if [ "$METRICS" -lt 9 ]; then
            echo "FAIL: expected ≥ 9, got $METRICS"
            exit 1
          fi
      - name: Verify 10 rules
        run: |
          RULES=$(curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
            http://localhost:3000/api/v1/provisioning/alert-rules | jq '.[].rules | length')
          if [ "$RULES" -ne 10 ]; then
            echo "FAIL: expected 10, got $RULES"
            exit 1
          fi
```

### 2.2 补全 TC-AT-017 (缺 env var 行为)

```yaml
- name: TC-AT-017 missing env var
  run: |
    docker compose stop grafana
    unset GRAFANA_WEBHOOK_URL
    docker compose up -d grafana
    sleep 30
    DISABLED=$(curl -s -H "Authorization: Bearer $GRAFANA_SA_TOKEN" \
      http://localhost:3000/api/v1/provisioning/contact-points | \
      jq '.[] | select(.name == "sre-webhook") | .disabled')
    if [ "$DISABLED" != "true" ]; then
      echo "FAIL: sre-webhook should be disabled, got $DISABLED"
      exit 1
    fi
```

### 2.3 TC-AT-012 端到端验证 (8 metric 暴露)

```yaml
- name: TC-AT-012 metrics endpoint
  run: |
    EXPECTED=("observability_channel_success_rate" "observability_am_sync_success_rate"
              "observability_lock_acquire_rate" "observability_lock_fallback_rate"
              "observability_lock_error_rate" "observability_lock_acquire_total"
              "observability_escalation_rate" "observability_alert_total")
    for M in "${EXPECTED[@]}"; do
      if ! curl -s http://localhost:8000/api/v1/metrics | grep -q "$M"; then
        echo "FAIL: missing $M"
        exit 1
      fi
    done
    echo "PASS: 8/8 metrics exposed"
```

---

## 3. P2 - 1 月内执行 (生产数据调优)

### 3.1 阈值生产调优 (1-2 周观察期后)

基于生产告警频率调整:

| 规则 | 当前阈值 | 观察后建议 |
|:---|:---:|:---|
| R1 通道成功率 Critical | < 0.80 | 观察误报率, 可能调至 0.75 |
| R3 AM 同步 Critical | < 0.70 | 观察, 0.75 可能更合理 |
| R6 锁降级率高 | > 0.05 | 观察, 0.10 可能更合理 |
| R7 锁错误率高 | > 0.00 | 保持 0 (任一错误需告警) |
| R8 升级率高 | > 0.30 | 观察, 0.40 可能更合理 |

### 3.2 告警风暴抑制

如果生产出现告警风暴, 调整 `policies.yaml`:
- 增大 `group_interval` (5m → 10m)
- 增大 `repeat_interval` (1h → 4h)

### 3.3 通知渠道扩展

v1.39 仅 3 渠道 (webhook/email/slack), 后续可加:
- PagerDuty (替代 webhook, 含值班轮换)
- Microsoft Teams (替代 slack)
- Telegram Bot (海外)

---

## 4. P3 - v1.40 候选主题

### 4.1 完整 Meta-Observe (RISK-3 升级)

当前 v1.39 通过 R11 meta-rule 简单覆盖, v1.40 可深化:
- **Prometheus 黑盒探针**: 独立 `up` 指标来源
- **Grafana 自身 health**: 监控告警引擎异常
- **告警延迟监控**: P0 通知 < 30s 实时监控

### 4.2 R9 响应时长 P99 告警 (Q1=B 排除)

v1.39 仅覆盖 7 v1.36 metric 核心, v1.40 可加:
- 响应时长 P99 告警
- 慢查询告警
- DB 连接池告警

### 4.3 动态阈值 (基于历史数据)

当前 9 条规则都是静态阈值, v1.40 可引入:
- 基于 7 天滚动平均的动态阈值
- 时间相关阈值 (工作日 vs 周末)

### 4.4 告警分组 & 抑制 (Inhibition)

避免重复告警:
- P0 触发时抑制 P1
- 同 metric 不同 severity 合并

### 4.5 告警历史 & 复盘

- 30 天告警数据可视化
- 月度复盘报告
- 告警误报率统计

---

## 5. 已识别但未实施的项 (Backlog)

| ID | 项目 | 优先级 | 备注 |
|:---|:---|:---:|:---|
| BACK-1 | R9 响应时长 P99 告警 | P3 | Q1=B 排除, v1.40 候选 |
| BACK-2 | 完整 meta-observe | P3 | v1.40 候选 |
| BACK-3 | 动态阈值 | P3 | v1.40+ 候选 |
| BACK-4 | 告警抑制 (Inhibition) | P2 | v1.39 暂未实施 |
| BACK-5 | 告警历史可视化 | P2 | Grafana 已有 30d 历史, 需 dashboard |
| BACK-6 | PagerDuty 集成 | P2 | 替代 webhook, 含值班轮换 |
| BACK-7 | 告警误报率统计 | P3 | 月度报告 |

---

## 6. 风险监控 (生产上线后)

### 6.1 第 1 周观察清单

- [ ] Exporter 60s 周期是否稳定 (无 60s 失败)
- [ ] 8 metric 是否持续更新 (避免 gauge 卡死)
- [ ] 9 条规则触发频率是否符合预期
- [ ] P0 通知是否 5min 内到达
- [ ] 误报率是否在可接受范围 (建议 < 5%)
- [ ] conftest mock 在 CI 是否干扰其他测试

### 6.2 异常处理

| 症状 | 可能原因 | 处理 |
|:---|:---|:---|
| Exporter 60s 失败 | DB 抖动 | 检查 DB 健康, R3 GAP-3 已自动重试 |
| 规则永远 firing | 阈值过敏感 | 调高阈值 (P0: 0.80 → 0.75) |
| 通知失败 | env var 缺失 | 至少配置 2 个渠道 |
| 0 流量误报 (R7) | GAP-1 未生效 | 检查 R7 expr 是否含 `lock_acquire_total > 0` |

---

## 7. 与 v1.37 / v1.38 的衔接

### 7.1 v1.37 兼容性

- ✅ 16/16 Grafana Adapter 测试 PASS
- ✅ 后端 API 0 改动
- ✅ `simpod-json` 数据源保留 (v1.37 仪表盘依赖)

### 7.2 v1.38 兼容性

- ✅ 7/7 Dashboard Template 测试 PASS
- ✅ 11/11 validate_dashboard_json.py PASS
- ✅ v1.37-alerts-overview.json md5 unchanged
- ✅ v1.38 仪表盘继续使用 simpod-json 数据源, 0 改动

### 7.3 v1.40 衔接

v1.40 候选主题 (优先级降序):
1. **P0**: 完整 meta-observe (Prometheus 黑盒探针)
2. **P1**: R9 响应时长 P99 告警
3. **P2**: 动态阈值 (基于历史数据)
4. **P3**: 告警抑制 (Inhibition)

---

## 8. 总结

v1.39 核心交付完成, 评分 39/40, 15/17 测试本地 PASS, 2 E2E 转 CI.

**立即行动** (P0):
1. 部署到生产, 配置至少 2 个 env var
2. 监控 Exporter 启动日志
3. 观察 1-2 周后调整阈值

**后续工作** (P1-P3):
- P1: CI 专项补全 E2E 验证
- P2: 1 月内生产调优 + 渠道扩展
- P3: v1.40 完整 meta-observe + R9 + 动态阈值

> **下一步**: 用户验收 DELIVERY_REPORT.md, 确认部署计划.
