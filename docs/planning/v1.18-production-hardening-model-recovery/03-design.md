# v1.18 生产上线硬化与结构化模型恢复 - 设计文档

> **迭代**: v1.18-production-hardening-model-recovery
> **日期**: 2026-05-01
> **状态**: Round 1 Draft

---

## 1. 结构化模型恢复设计

### 1.1 问题诊断

**症状**: `structured_logistic_regression_quick` 模型加载失败，API 返回 422
**可能原因**:
1. 模型文件在 v1.17 开发过程中被覆盖或损坏
2. sklearn 版本不兼容（训练时 vs 运行时）
3. 特征名称列表与模型期望不一致

### 1.2 恢复方案

**方案 A: 从备份恢复**（首选）
- 检查 `backend/models/artifacts/` 是否有备份
- 如有，直接复制替换

**方案 B: 重新训练**（备选）
- 使用 `backend/train_baseline.py` 或 `backend/train_simple.py`
- 使用 v1.16 的相同训练数据
- 确保特征名称列表一致

**方案 C: 降级到启发式规则**（兜底）
- 如果模型无法恢复，使用启发式规则作为 fallback
- 确保系统不因模型损坏而完全不可用

### 1.3 验证矩阵

| 风险等级 | 测试样本 | 期望输出 | 容差 |
|---|---|---|---|
| 低风险 | 正常作息、无抑郁症状 | Level 1 | plus or minus 0 |
| 中风险 | 轻度睡眠问题、偶尔情绪低落 | Level 2 | plus or minus 0 |
| 高风险 | 持续失眠、明显兴趣丧失 | Level 3 | plus or minus 0 |
| 极高风险 | 自杀意念、严重功能障碍 | Level 4 | plus or minus 0 |

---

## 2. 数据库迁移设计

### 2.1 迁移脚本结构

```python
# a1b2c3d4e5f6_add_review_and_crisis_tables.py

def upgrade():
    # 1. 创建 review_tasks 表
    op.create_table("review_tasks", ...)
    
    # 2. 创建 crisis_events 表
    op.create_table("crisis_events", ...)
    
    # 3. 创建索引
    op.create_index(...)

def downgrade():
    # 1. 删除索引
    op.drop_index(...)
    
    # 2. 删除 crisis_events
    op.drop_table("crisis_events")
    
    # 3. 删除 review_tasks
    op.drop_table("review_tasks")
```

### 2.2 执行策略

**开发环境**:
```bash
cd backend
alembic upgrade a1b2c3d4e5f6
```

**生产环境**:
1. 备份数据库: `pg_dump depression_system > backup_$(date +%Y%m%d).sql`
2. 执行迁移: `alembic upgrade a1b2c3d4e5f6`
3. 验证表结构
4. 如失败: `alembic downgrade a1b2c3d4e5f6`

### 2.3 回滚方案

| 场景 | 回滚操作 | 数据影响 |
|---|---|---|
| 迁移失败 | `alembic downgrade a1b2c3d4e5f6` | 无数据丢失 |
| 迁移后发现问题 | 恢复备份 + 跳过迁移版本 | 迁移后数据丢失 |
| 部分数据写入后失败 | 手动清理 + downgrade | 需人工介入 |

---

## 3. 危机审计导出设计

### 3.1 CSV 格式

```csv
id,user_id,trigger_source,crisis_score,status,created_at,handled_by,handled_action
1,1234****,text,0.95,detected,2026-04-15T10:30:00,,
2,5678****,model,0.87,handled,2026-04-16T14:20:00,3,电话干预
```

### 3.2 脱敏规则

| 字段 | 原始值 | 脱敏后 | 规则 |
|---|---|---|---|
| user_id | 12345 | 1234**** | 保留前 4 位 |
| input_summary | 用户输入的详细文本 | 截断至50字符 | 保留前50字符 |
| crisis_keywords | ["自杀", "不想活"] | 保留原样 | 用于分析，不脱敏 |

### 3.3 导出接口设计

**Endpoint**: `GET /api/v1/admin/crisis-events/export`
**Auth**: Admin only
**Query Params**:
- `start_date`: ISO 8601 日期 (必填)
- `end_date`: ISO 8601 日期 (必填)

**Response**: `text/csv` 文件下载

---

## 4. 生产配置硬化设计

### 4.1 环境变量配置

| 变量名 | 开发环境值 | 生产环境要求 | 说明 |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | 应用环境 |
| `DATABASE_URL` | `sqlite+aiosqlite:///...` | `postgresql+asyncpg://...` | 数据库连接 |
| `JWT_SECRET_KEY` | 空/弱密钥 | 强随机字符串 (>=32字符) | JWT签名密钥 |
| `SENTRY_DSN` | 空 | 有效的Sentry DSN | 错误追踪 |
| `REDIS_URL` | `redis://localhost:6379/0` | 生产Redis地址 | 缓存/队列 |

### 4.2 生产安全检查

在 `app/core/config.py` 中添加验证：
- `APP_ENV=production` 时，`DATABASE_URL` 不能以 `sqlite` 开头
- `APP_ENV=production` 时，`JWT_SECRET_KEY` 必须 >= 32 字符
- `APP_ENV=production` 时，`SENTRY_DSN` 建议配置（警告而非报错）

### 4.3 观测配置

**Sentry 集成**:
- 自动捕获未处理异常
- 记录 API 性能指标
- 配置 release 标签 (`app_version`)

**自定义监控**:
- API 延迟 > 500ms 记录 warning
- 危机事件检测记录 info
- 模型预测失败记录 error

---

## 5. E2E 验收流程设计

### 5.1 危机检测闭环

```
用户提交危机文本
  -> 文本分析器检测危机关键词
  -> 创建 CrisisEvent (status=detected)
  -> 创建 ReviewTask (priority=crisis_review)
  -> 咨询师查看 ReviewTask
  -> 咨询师处理/升级 ReviewTask
  -> 更新 CrisisEvent (status=handled)
```

### 5.2 融合预测闭环

```
用户提交多模态数据
  -> 融合引擎计算风险分数
  -> 风险分数触发 review_required
  -> 创建 ReviewTask (priority=high_risk_review)
  -> 咨询师查看并处理
```

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-05-01
