# 06-learnings — v1.36-alert-observability

> **Agent 必读**: 每次开始工作前，必须阅读此文件。本文件继承 v1.35 的经验教训。

---

## 1. 继承自 v1.35 (跨实例告警 / 归档 / AM 同步)

### 1.1 代码风格与规范

- ✅ 异步函数统一 `async def`
- ✅ 依赖注入用 `Annotated[X, Depends(...)]` 模式
- ✅ 日志格式: `[模块名] 消息 (key=value, ...)`
- ✅ 端点响应统一 `ok({...})` 包装
- ✅ 测试用 mock, 不依赖真实 Redis/AM
- ✅ 数据库时间统一 `_utcnow_naive()` 处理
- ✅ OperationLog 写入用 `target_id` + `target_type` 关联

### 1.2 避坑指南

- ⚠️ **Windows pytest exit -1073741510**: 全量测试时偶发, 分批运行可避免
- ⚠️ **Pydantic 字段别名**: 用 `Field(..., alias=...)` 时响应也需 alias
- ⚠️ **JSON_EXTRACT**: MySQL 5.7.13+ 才支持, 注意版本
- ⚠️ **self-JOIN 性能**: 大表上小心, 需复合索引
- ⚠️ **跨实例内存状态**: 进程重启丢失, 接受或外置 Redis
- ⚠️ **detail JSON 长度限制**: 5K 字符 (alerts.py line 197)
- ⚠️ **action_type 长度限制**: 50 字符 (CheckConstraint)

### 1.3 常用命令

```bash
# 重置数据库
python -c "from app.core.database import Base, engine; Base.metadata.drop_all(engine); Base.metadata.create_all(engine)"

# 启动 Redis
docker run -d --name redis -p 6379:6379 redis:7

# 启动 AlertManager (mock)
docker run -d --name am -p 9093:9093 prom/alertmanager:latest

# 跑测试 (分批)
cd backend && python -m pytest tests/test_observability_api.py -v
cd backend && python -m pytest tests/test_channel_logging.py -v
cd backend && python -m pytest tests/test_dedup_lock_stats.py -v
```

---

## 2. v1.36 新增约定

### 2.1 新增 action_type 命名规范

- ✅ 统一小写 + 下划线
- ✅ 语义清晰: `alert_channel_sent` (动作_结果)
- ✅ 长度 < 50 字符
- ✅ 文档化: 见 02-architecture.md

### 2.2 观测 API 规范

- ✅ 端点前缀: `/alerts/observability/`
- ✅ 权限: 全部 `require_role("admin")`
- ✅ 缓存: 5min Redis TTL
- ✅ 时间窗口: max 30 天
- ✅ 响应: `{"code": 0, "data": {...}}`

### 2.3 内存计数规范

- ✅ 模块级 `_stats: dict[str, int]`
- ✅ flush 60s 一次
- ✅ 仅写 skipped/fallback (避免 DB 写入放大)
- ✅ 进程重启可丢失

### 2.4 复合索引规范

- ✅ 命名: `idx_oplog_<col1>_<col2>`
- ✅ 启动时自动创建
- ✅ 字段顺序: 选择性高的在前 (action_type 在前)

---

## 3. 避坑指南 (v1.36 新增)

- ⚠️ **notifier 改造** 不能影响现有通知 (异步写日志, 失败不回滚)
- ⚠️ **am_sync 改造** 不能影响现有同步 (失败仅记录, 不抛异常)
- ⚠️ **dedup_lock 改造** 不能影响现有去重 (内存计数, 路径不变)
- ⚠️ **复合索引创建** 大表上 ALTER TABLE 可能慢, 注意迁移窗口
- ⚠️ **EP-2 self-JOIN** 性能差时退化到 LIMIT 10000

---

## 4. 与其他迭代的协作

- v1.34 静默规则 → 静默命中率 API (EP-5)
- v1.34 升级任务 → 升级率 API (EP-3)
- v1.35 跨实例锁 → 锁可观测 API (EP-7)
- v1.35 AM 同步 → AM 同步可观测 API (EP-6)
- v1.35 归档 → 归档可观测 (P2 后续)
