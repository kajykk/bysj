# v1.26 Monitoring Metrics Specification

## Endpoint

`GET /api/v1/monitoring/engine-snapshot` (需要 admin.predict.audit 权限)

## 返回字段说明

### model_load_stats
| 字段 | 类型 | 含义 |
|------|------|------|
| loads | int | 模型加载次数 |
| cache_hits | int | 缓存命中次数 |
| first_load_ms | float | 首次加载耗时 (ms) |
| last_load_ms | float | 最近一次加载耗时 (ms) |

### predict_stats
| 字段 | 类型 | 含义 |
|------|------|------|
| count | int | 预测次数 |
| total_ms | float | 累计耗时 (ms) |
| last_ms | float | 最近一次耗时 (ms) |

### monitoring.routing
| 字段 | 类型 | 含义 |
|------|------|------|
| structured | int | 全特征路径调用次数 |
| lite | int | lite 模型路径调用次数 |
| anxiety_only | int | 仅 GAD-7 路径调用次数 |
| insufficient | int | 信息不足路径调用次数 |

### monitoring.fallback_total
| 类型 | 含义 |
|------|------|
| int | 累计 fallback 触发次数（含 lite 模型不可用 / 文本过短 / 结构化特征不可用） |

### monitoring.crisis_override_count
| 类型 | 含义 |
|------|------|
| int | Crisis 安全 override 触发次数 |

### monitoring.input_quality
| 字段 | 含义 |
|------|------|
| complete | 特征完整（0 字段缺失） |
| partial | 部分缺失（1-2 字段） |
| poor | 严重缺失（3+ 字段） |

### monitoring.adapter
| 字段 | 含义 |
|------|------|
| hit_ratio | Adapter 命中率 |
| hit_count / miss_count | Adapter 命中/未命中次数 |

### monitoring.score_delta_recent
最近 100 次评分差异统计 (mean / max abs delta)

### 其他
- cache_size: 当前缓存的模型数
- uptime_seconds: 引擎运行时间

## 使用方式

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/monitoring/engine-snapshot
```
