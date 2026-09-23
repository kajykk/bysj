# 覆盖率基线报告 (Coverage Baseline Report)

> **迭代**: v1.6-contract-e2e-quality-governance
> **日期**: 2026-04-28
> **状态**: 🔄 基线配置完成，待实际测量

---

## 1. 后端覆盖率配置

### 1.1 配置项

| 配置 | 值 | 说明 |
|------|-----|------|
| 目标覆盖率 | >= 85% | pytest.ini: `--cov-fail-under=85` |
| 测量源 | `app/` | 业务代码 |
| 排除项 | tests, migrations, scripts, docs | 非业务代码 |
| 报告格式 | terminal, HTML, XML | 多格式输出 |

### 1.2 运行命令

```bash
# 运行所有测试并生成覆盖率报告
cd backend
pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml

# 运行特定模块测试
pytest tests/unit/ --cov=app.services --cov-report=term

# 生成基线报告
pytest --cov=app --cov-report=json:coverage-baseline.json
```

### 1.3 分阶段目标

| 阶段 | 目标覆盖率 | 时间线 |
|------|-----------|--------|
| 当前基线 | 待测量 | 2026-04-28 |
| 第一阶段 | >= 70% | 1-2 周 |
| 第二阶段 | >= 80% | 2-3 周 |
| 最终目标 | >= 85% | 3-4 周 |

---

## 2. 前端覆盖率配置

### 2.1 配置项

| 配置 | 值 | 说明 |
|------|-----|------|
| 目标覆盖率 | >= 80% | vitest 配置 |
| 测量源 | `src/` | 业务代码 |
| 排除项 | tests, mocks, types | 非业务代码 |

### 2.2 运行命令

```bash
# 运行所有测试并生成覆盖率报告
cd frontend
npx vitest --coverage

# 生成基线报告
npx vitest --coverage --reporter=json
```

### 2.3 分阶段目标

| 阶段 | 目标覆盖率 | 时间线 |
|------|-----------|--------|
| 当前基线 | 待测量 | 2026-04-28 |
| 第一阶段 | >= 65% | 1-2 周 |
| 第二阶段 | >= 75% | 2-3 周 |
| 最终目标 | >= 80% | 3-4 周 |

---

## 3. 覆盖率提升策略

### 3.1 后端重点模块

| 模块 | 优先级 | 难点 |
|------|--------|------|
| `app/services/` | P0 | 业务逻辑复杂 |
| `app/api/v1/` | P0 | 需要模拟请求 |
| `app/core/` | P1 | 配置和工具类 |
| `app/ml/` | P1 | 模型加载依赖 |

### 3.2 前端重点模块

| 模块 | 优先级 | 难点 |
|------|--------|------|
| `src/components/` | P0 | UI 交互测试 |
| `src/composables/` | P0 | 逻辑复用测试 |
| `src/views/` | P1 | 页面级测试 |
| `src/api/` | P1 | API 调用模拟 |

---

## 4. 质量门禁

### 4.1 CI 门禁

```yaml
# .github/workflows/quality-gate.yml
- name: Backend Coverage
  run: |
    cd backend
    pytest --cov=app --cov-fail-under=85 --cov-report=xml
  
- name: Frontend Coverage
  run: |
    cd frontend
    npx vitest --coverage --threshold=80
```

### 4.2 本地检查

```bash
# 预提交检查
make check-coverage
```

---

## 5. 待办事项

- [ ] 运行后端全量测试，记录当前覆盖率基线
- [ ] 运行前端全量测试，记录当前覆盖率基线
- [ ] 识别覆盖率缺口最大的模块
- [ ] 制定针对性补测计划
- [ ] 配置 CI 覆盖率门禁

---

> **下一步**: T-COV-002 - 运行测试并记录当前覆盖率基线
