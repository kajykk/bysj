---
name: sys-cache-optimizer
description: >-
  This skill should be used when adding or tuning caches — "加缓存", "缓存命中率低",
  "缓存穿透/击穿/雪崩", "热点数据多级缓存". It implements §4.1.3 of the optimization plan.
agent_created: true
---

# sys-cache-optimizer

## 用途
用多级缓存降低重复计算与重复查询，并防止缓存穿透/击穿/雪崩。

## 何时使用
- `sys-perf-diagnosis` 发现重复查询 / 重复计算热点。
- 用户要求「给热点接口加缓存」「设计缓存一致性策略」。

## 执行流程
1. **识别热点**：找出读多写少、计算昂贵的数据（配置、统计量、模型元数据）。
2. **选层级**：本地缓存（进程内，如 cachetools）+ 分布式缓存（Redis）做多级。
3. **设计键与 TTL**：合理过期策略；相关键用统一命名空间便于批量失效。
4. **一致性**：写后失效（write-through/invalidate）；避免大 key / 热 key 倾斜。
5. **防穿透**：空值缓存 + 布隆过滤器。
6. **防击穿**：热点 key 互斥锁 / 逻辑过期（异步重建）。
7. **防雪崩**：TTL 加随机抖动，避免同时失效。
8. **监控命中率**：记录命中/未命中，命中率过低则回退（缓存反而放大问题）。

## 工具与脚本
- 分布式：Redis（`redis-py`）。
- 本地：`cachetools`、FastAPI `lru_cache` / 依赖缓存。
- 命中率指标：接入 `sys-observability`。

## 验收与 KPI（§3）
- 缓存命中率显著提升、重复查询下降。
- 无穿透/击穿/雪崩事故；命中率异常可观测。

## 与本工程栈的对应
- FastAPI 路由在 `backend/app/api/v1/`；可在依赖注入层加缓存。
- ML 推理结果（如风险评估）适合短 TTL 缓存。

## 注意事项
- 不缓存含用户隐私的明文；敏感数据缓存需脱敏（见 `sys-security-hardening`）。
- 缓存变更需监控，命中率过低立即回退。
