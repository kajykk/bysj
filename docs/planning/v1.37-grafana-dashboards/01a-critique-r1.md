# v1.37 Grafana 仪表盘模板 — Round 1 自查 (Critique)

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 对 Round 1 Draft 做 4 维度自查, 发现问题, 准备进入 Round 2 修订

---

## 1. 自查方法

| 维度 | 检验项 | 评价方式 |
|:---|:---|:---|
| **完整性** | 7 Rows × panels / 变量 / 数据源 / AC 是否齐全 | 列表核对 |
| **可行性** | JSON Datasource / Provisioning / Service Account 是否真实可行 | 文档调研 + 验证 |
| **可测试性** | AC 能否被自动化测试覆盖 | 18 AC → 测试矩阵 |
| **可观测性** | 仪表盘自身能否被监控 (加载失败 / Token 失效) | 元指标设计 |

---

## 2. 完整性复查 (P0)

### 2.1 7 Rows 覆盖矩阵

| Row | 端点 | panels | 覆盖情况 |
|:---|:---|:---:|:---|
| 1. Alert Trend | /trend | 3 | ✅ 完整 |
| 2. Response Time | /response-time | 3 | ✅ 完整 |
| 3. Escalation | /escalation | 3 | ✅ 完整 |
| 4. Channel Stats | /channel-stats | 3 | ✅ 完整 |
| 5. Silence Hit Rate | /silence-hit-rate | 3 | ✅ 完整 |
| 6. AM Sync | /am-sync | 3 | ✅ 完整 |
| 7. Lock Stats | /lock-stats | 3 | ✅ 完整 |
| **合计** | 7 | **21** | **✅** |

**结论**: 7 Rows 全部覆盖, 无遗漏。

### 2.2 变量完整性

| 变量 | Draft | 行业最佳实践 | 差异 |
|:---|:---:|:---|:---|
| time_range | ✅ | ✅ | 无 |
| severity | ✅ (4 级 + all) | ✅ | 无 |
| channel | ✅ (4 个 + all) | ✅ | 无 |
| rule | ✅ (top 20) | ✅ | 无 |
| instance_id | ✅ | ⚠️ 多实例时必需, 单实例可选 | 可保留 (未来扩展) |
| refresh | ✅ (1m 默认) | ✅ | 无 |

**结论**: 6 个变量与 Grafana 行业实践一致, 无重大差异。

### 2.3 数据源端点 (v1.36 继承)

| 端点 | 缓存 | 是否需要变量注入 |
|:---|:---:|:---|
| /trend | 5min | start_time/end_time/bucket/severity/status/group_by |
| /response-time | 5min | start_time/end_time/severity |
| /escalation | 5min | start_time/end_time |
| /channel-stats | 5min | start_time/end_time/channel |
| /silence-hit-rate | 5min | start_time/end_time |
| /am-sync | 5min | start_time/end_time/operation |
| /lock-stats | (无) | (无时间参数) |

**⚠️ 发现 #1 (P1)**: Draft 未明确"变量如何注入到 URL 参数"。需在 Round 2 补充:
- time_range 变量 → URL `start_time` & `end_time` 转换 (Grafana `__from` & `__to` → ISO 8601)
- severity 变量 → URL `severity=`
- channel 变量 → URL `channel=`

**⚠️ 发现 #2 (P1)**: `instance_id` 变量在单实例场景下不实用, 但 v1.37 仅单实例, 建议简化为 static 静态值显示。

**⚠️ 发现 #3 (P2)**: `rule` 变量需要从 `/trend?group_by=rule` 拉取 top 20, 但 Grafana JSON Datasource 的 "query" 类型变量不支持复杂提取, 需手工转换 (e.g., `/trend?group_by=rule` → JSON 路径 `$.by_rule.*`).

---

## 3. 可行性复查 (P0)

### 3.1 Grafana JSON Datasource 可行性

**调研结论** (来自 Grafana 官方文档):
- 插件地址: https://github.com/grafana/grafana-json-datasource
- 兼容性: Grafana 9.x+ (含 10.x / 11.x)
- 安装: Provisioning 或 `grafana-cli plugins install grafana-json-datasource`
- 数据源格式: 标准 HTTP GET, 期望 JSON 响应 (v1.36 端点已返回标准 JSON)

**✅ 结论**: 插件成熟稳定, v1.36 端点格式兼容。

### 3.2 Provisioning 路径

**调研结论**:
- Grafana Provisioning 在容器启动时自动加载 `provisioning/` 目录
- 文件路径挂载: `/etc/grafana/provisioning/dashboards/*.yaml` + `/var/lib/grafana/dashboards/*.json`
- 支持 hot-reload (`allowUiUpdates: false` + 短轮询)

**✅ 结论**: Provisioning 是 Grafana 容器化部署的标准做法, 完全可行。

### 3.3 Service Account Token 集成

**调研结论**:
- Grafana 10.x+ 支持 Service Account (SA) + API Token
- SA Token 通过 `Authorization: Bearer <token>` 头部传递
- 生命周期: 可设 30 天过期, 需手动轮换

**✅ 结论**: SA Token 是 Grafana 官方推荐方式, 完全可行。

**⚠️ 发现 #4 (P1)**: v1.36 后端 `/alerts/observability/*` 端点已使用 `require_role("admin")` 鉴权, 需确认是否接受 Bearer Token (而非 Cookie/JWT):
- 如果 v1.36 端点通过 `Authorization: Bearer` 解码并查找 admin 用户 → 兼容
- 如果 v1.36 端点依赖 OAuth2 表单登录 → 不兼容, 需在 v1.37 增加 "Service Account 鉴权" 路径

**缓解**: Round 2 应明确 v1.37 仪表盘调用 v1.36 端点的鉴权方式, 如不兼容需 v1.36 后端补 minor patch。

### 3.4 单 panel 后端响应延迟

**调研结论** (基于 v1.36 性能测试):
- /trend 7d 100K 行 < 500ms (T3.2 验证)
- /response-time 7d < 300ms
- /channel-stats 7d < 200ms
- /am-sync < 100ms
- /lock-stats < 50ms
- /silence-hit-rate < 100ms
- /escalation ~ 200ms (预估)

**5min 缓存保护**: Grafana 1m refresh → 7 个 panel 首次查询 (cold) ≈ 1.5s, 后续 refresh 全部 cache hit ≈ 0ms

**✅ 结论**: 满足 AC-9 (3s) 和 AC-10 (2s)。

---

## 4. 可测试性复查 (P0)

### 4.1 18 AC → 测试矩阵

| AC | 自动化测试 | 文件 |
|:---|:---:|:---|
| AC-1 JSON 可导入 | test_dashboard_json.py::test_json_valid_grafana10 | T1 |
| AC-2 7 Rows 完整 | test_dashboard_panels.py::test_rows_count | T2 |
| AC-3 6 变量可下拉 | test_dashboard_panels.py::test_variables_complete | T2 |
| AC-4 time_range 切换 | 手动 + E2E | (E2E) |
| AC-5 severity 过滤 | 手动 + E2E | (E2E) |
| AC-6 panel URL 正确 | test_dashboard_panels.py::test_panel_targets | T2 |
| AC-7 Bearer 头部 | test_dashboard_panels.py::test_authorization_header | T2 |
| AC-8 Provisioning 加载 | test_provisioning.py::test_docker_compose_provisions | T3 |
| AC-9 首次加载 < 3s | test_perf.py::test_first_load | T4 (perf) |
| AC-10 refresh < 2s | test_perf.py::test_refresh | T4 (perf) |
| AC-11 panel < 500ms | test_perf.py::test_per_panel | T4 (perf) |
| AC-12-15 README | 手动 + 文档 lint | (manual) |
| AC-16 JSON schema | test_dashboard_json.py (7 子测试) | T1 |
| AC-17 panel 完整 | test_dashboard_panels.py (5 子测试) | T2 |
| AC-18 provisioning | test_provisioning.py (3 子测试) | T3 |

**✅ 结论**: 18 AC 全部可被自动化测试或手动验证覆盖。

**⚠️ 发现 #5 (P2)**: AC-4 (time_range 切换) 和 AC-5 (severity 过滤) 需要真实 Grafana 运行环境验证, 单元测试覆盖不到。需在 Round 3 明确 "手动 E2E 步骤" 作为 P1 验证。

**⚠️ 发现 #6 (P1)**: 单元测试无法直接验证 Grafana 导入是否真正成功, 需引入 `grafana-json-datasource` 的 CLI 工具或 mock 验证。

---

## 5. 可观测性复查 (P1)

### 5.1 仪表盘自身可观测性

| 场景 | 当前设计 | 改进建议 |
|:---|:---|:---|
| 加载失败 | 用户肉眼可见 | (无改进) |
| Token 失效 | Grafana 401 错误, 用户可见 | (无改进) |
| 端点 5xx | panel 显示 "No data" | (无改进) |
| Token 即将过期 | 无 | **⚠️ P1 改进**: 仪表盘顶部加 "Token 剩余天数" indicator, 通过 `/health` 返回 `token_expires_at` |

**⚠️ 发现 #7 (P1)**: 当前设计缺少对 Service Account Token 生命周期的可观测性。Round 2 需明确:
- 是否在仪表盘加 Token 剩余天数显示?
- 是否需要后端 `/health` 增加 `token_expires_at` 字段?
- 还是依赖 Grafana 自身的告警?

### 5.2 数据延迟可观测

**⚠️ 发现 #8 (P2)**: v1.36 端点使用 5min Redis 缓存, Grafana 1m refresh 会看到 stale data。
- 建议在每个 panel 标题加 "cached" 角标 (v1.36 端点已返回 `cached: bool`)
- Grafana 默认 panel 不会显示该字段, 需 Round 2 明确是否在 panel subtitle 加 "🟢 Live / 🟡 Cached (5min)"

---

## 6. 综合问题清单 (按严重度)

### 6.1 P0 (必须 Round 2 解决)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P0-1 | v1.36 端点是否接受 Bearer Token (鉴权兼容) | 审查 v1.36 deps.py + require_role 流程, 如不兼容需 minor patch |

### 6.2 P1 (建议 Round 2 解决)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P1-1 | 变量到 URL 参数的转换未明确 | Round 2 补充 Grafana variable → URL params 映射表 |
| P1-2 | instance_id 变量在单实例场景不实用 | 简化为 static 字符串 |
| P1-3 | rule 变量需要 JSON path 提取 | Round 2 给出 JSON path 表达式 |
| P1-4 | Token 过期无可观测 | Round 2 决定是否加 indicator |
| P1-5 | cache stale 无可视 | Round 2 决定是否在 panel subtitle 显示 |

### 6.3 P2 (可选优化)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P2-1 | time_range 切换 / severity 过滤需 E2E 验证 | Round 3 补充手动 E2E 步骤 |
| P2-2 | Grafana 导入兼容性需 CLI 验证 | Round 3 引入 `grafana-cli` 或 mock |

---

## 7. 改进建议总结

1. **澄清鉴权链路**: 确认 v1.36 后端是否接受 `Authorization: Bearer <SA_token>`, 如果不, 需 minor patch
2. **明确变量到 URL 映射**: 6 个变量如何注入到 7 个端点
3. **简化 instance_id**: 单实例下用 static 字符串代替 query 变量
4. **可选可观测性增强**: Token 剩余天数 + cache stale 角标
5. **E2E 验证范围**: 明确哪些 AC 走单元测试, 哪些走手动 E2E

---

## 8. Round 2 待办

完成上述 P0-1 + P1-1~5 的修订后, 进入 Round 2 调研 (Step 3):
- Grafana 10.x vs 11.x JSON 兼容性差异
- Service Account vs Legacy API Key 的对比
- JSON Datasource 性能优化 (query options, parallel queries)
- Provisioning 在 Docker / K8s 下的最佳实践

---

> **Round 1 Step 2 完成**: 进入 Step 3 (Research) - 调研 Grafana JSON Datasource 最佳实践
