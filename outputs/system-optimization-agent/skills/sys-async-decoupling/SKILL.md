---
name: sys-async-decoupling
description: >-
  This skill should be used when decoupling time-consuming work from the
  request path — "异步化", "削峰填谷", "引入消息队列", "任务重试幂等".
  It implements §4.1.4 of the optimization plan.
agent_created: true
---

# sys-async-decoupling

## 用途
将非关键路径改为异步，用消息队列削峰，提升并发承载与峰值吞吐。

## 何时使用
- 在线请求包含耗时任务（邮件、导出、批量计算、ML 推理回调）。
- 用户要求「削峰」「异步处理」。

## 执行流程
1. **切分关键/非关键**：把可延迟的工作从同步链路剥离。
2. **选机制**：
   - 轻量：`FastAPI BackgroundTasks`（进程内、最简）。
   - 健壮：任务队列（Celery / ARQ / Redis Stream / RabbitMQ）。
3. **幂等设计**：任务携带唯一 id，消费端去重，避免重复消费副作用。
4. **重试与退避**：指数退避 + 死信队列（DLQ），失败可追踪。
5. **削峰**：生产者限流、队列缓冲，消费者按能力消费。
6. **可观测**：任务积压、消费延迟、失败率接入 `sys-observability`。
7. **回归**：用 `sys-load-testing` 验证峰值承载提升 30–80%。

## 工具与脚本
- 队列：Redis Stream / Celery / ARQ。
- 后端：`backend/app`（FastAPI）；耗时任务建议在 `app/services` 或独立 worker。
- ML 推理：`app/ml`、`app/core/model_engine_predict`。

## 验收与 KPI（§3）
- 非关键路径异步率提升，高峰期并发承载 ↑30–80%。
- 任务重试/幂等生效，无重复副作用。

## 与本工程栈的对应
- 推理路径已做延迟导入优化，适合放入独立 worker 异步执行。
- 大数据导出、报告生成适合异步 + 进度查询。

## 注意事项
- 异步化后必须保证用户可感知进度 / 结果可达。
- 消费端务必幂等，防止消息重投造成重复业务动作。
