# 详细设计 — v1.19-ci-e2e-audit-export

> **版本**: v1.0-Draft  
> **日期**: 2026-05-01

---

## 1. 前端导出 UI 设计

### 1.1 组件结构

```
CrisisEventListPage (现有页面)
├── DateRangePicker (新增)
│   ├── start_date: DatePicker
│   └── end_date: DatePicker
├── ExportButton (新增)
│   ├── Loading State
│   ├── Error Toast
│   └── Empty Data Toast
└── CrisisEventTable (现有)
```

### 1.2 状态管理

```typescript
interface ExportState {
  startDate: string;       // YYYY-MM-DD
  endDate: string;         // YYYY-MM-DD
  exporting: boolean;      // loading
  error: string | null;
}
```

### 1.3 交互设计

| 状态 | 按钮文案 | 按钮状态 | Toast |
|---|---|---|---|
| 默认 | 导出 CSV | Enabled | - |
| Loading | 导出中... | Disabled + Spin | - |
| 成功 | 导出 CSV | Enabled | "导出成功，共 N 条记录" |
| 空数据 | 导出 CSV | Enabled | "所选时间范围内无危机事件" |
| 网络错误 | 导出 CSV | Enabled | "导出失败: [原因]" |
| 权限不足 | - | - | "无权限访问" |

### 1.4 CSV 下载实现

```typescript
async function handleExport() {
  setExporting(true);
  try {
    const response = await fetch(
      `/api/v1/admin/crisis-events/export?start_date=${startDate}&end_date=${endDate}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!response.ok) {
      if (response.status === 403) throw new Error('无权限访问');
      const err = await response.json();
      throw new Error(err.detail || '导出失败');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `crisis_events_${startDate}_${endDate}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('导出成功');
  } catch (e) {
    message.error(e.message);
  } finally {
    setExporting(false);
  }
}
```

---

## 2. CI/Docker 验证脚本设计

### 2.1 后端验证脚本 (`scripts/ci_verify.sh`)

```bash
#!/bin/bash
set -e

echo "=== CI Verification v1.19 ==="

# 1. 安装依赖
pip install -r requirements.txt

# 2. 数据库迁移
alembic upgrade head
echo "Migration: OK"

# 3. 运行测试
pytest --tb=short -x
echo "Pytest: OK"

# 4. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3

# 5. 健康检查
curl -f http://localhost:8000/health
echo "Health: OK"

# 6. 结构化预测测试
curl -s -X POST http://localhost:8000/api/v1/prediction/structured \
  -H "Content-Type: application/json" \
  -d '{"age":25,"cgpa":3.8,"stress_level":1,"sleep_duration":8}'
echo "Structured Predict: OK"

# 7. 清理
kill %1

echo "=== All checks passed ==="
```

### 2.2 前端构建验证 (`scripts/ci_frontend.sh`)

```bash
#!/bin/bash
set -e

npm ci
npm run build

if [ -d "dist" ]; then
  echo "Build: OK (dist/ exists)"
else
  echo "Build: FAILED (dist/ missing)"
  exit 1
fi
```

---

## 3. E2E 测试脚本设计

### 3.1 危机文本闭环测试 (pytest)

```python
# tests/e2e/test_crisis_text_flow.py
async def test_crisis_text_closed_loop():
    """危机文本提交 → CrisisEvent → ReviewTask → 咨询师处理"""
    # 1. 创建用户 + 登录
    # 2. 提交危机文本 (含自杀关键词)
    # 3. 验证 CrisisEvent 已创建，status=detected
    # 4. 验证 ReviewTask 已创建，priority=crisis_review
    # 5. 咨询师登录
    # 6. 查看待处理 ReviewTask
    # 7. 处理 ReviewTask (resolve)
    # 8. 验证 CrisisEvent 状态更新
```

---

## 4. 结构化模型重训预研 (Phase 8, P1)

### 4.1 预研任务
1. 确认 `train_baseline.py` 脚本位置和可用性
2. 确认训练数据 (`data/Depression Student Dataset.csv`) 完整性
3. 确认 sklearn 版本兼容性
4. 确认 artifact 输出目录结构
5. 输出 `STRUCTURED_MODEL_RETRAIN_PLAN.md`

---

> **文档版本**: v1.0-Draft  
> **最后更新**: 2026-05-01
