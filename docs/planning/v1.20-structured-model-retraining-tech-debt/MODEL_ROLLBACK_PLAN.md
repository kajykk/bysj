# MODEL ROLLBACK PLAN — v1.20 结构化模型

## 1. 回滚触发条件

| 条件 | 严重级别 | 触发动作 |
|---|---|---|
| 模型预测准确率下降 > 5% | Warning | 人工评估后决定是否回滚 |
| 模型预测产生 NaN/Inf | Critical | 自动 fallback |
| API 响应延迟 > 200ms | Warning | 人工评估 |
| API 500 错误率 > 1% | Critical | 立即回滚 |
| 用户反馈预测明显错误 | Warning | 人工评估 |

## 2. 回滚方式

### 方式 A: 配置开关（推荐，无需重启）

```bash
# 强制使用 heuristic fallback
export STRUCTURED_MODEL_MODE=fallback

# 或修改 .env 文件
STRUCTURED_MODEL_MODE=fallback
```

**生效方式**: 热加载（配置读取时生效）或/需重启服务

### 方式 B: 文件级回滚（需要重启）

```bash
# 删除或移动 v1.20 模型文件
mv models/artifacts/structured_v1.20/structured_model_v1.20.pkl \
   models/artifacts/structured_v1.20/structured_model_v1.20.pkl.bak

# 重启服务 → 系统自动检测文件缺失 → fallback
```

## 3. 回滚后验证

- [ ] `/api/v1/health` 返回 200
- [ ] `POST /api/v1/model/predict/structured` 正常响应
- [ ] 响应中 `fallback_used: true`, `model_used: "structured_heuristic_fallback"`
- [ ] 预测结果合理（与 heuristic 行为一致）

## 4. 恢复流程

问题修复后恢复步骤：
1. 更新模型文件至 `models/artifacts/structured_v1.20/`
2. 设置 `STRUCTURED_MODEL_MODE=primary`
3. 重启服务
4. 验证: `fallback_used: false`, `model_used: "structured_logistic_regression_quick"`
