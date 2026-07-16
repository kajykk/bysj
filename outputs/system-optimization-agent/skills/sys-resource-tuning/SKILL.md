---
name: sys-resource-tuning
description: >-
  This skill should be used when tuning CPU/memory/storage/network usage —
  "CPU 高", "内存泄漏", "GC 频繁", "磁盘 IO 等待高", "线程池不合理".
  It implements §4.2 of the optimization plan.
agent_created: true
---

# sys-resource-tuning

## 用途
识别并消除资源热点（CPU/内存/存储/网络），使资源利用更平稳。

## 何时使用
- 监控显示 CPU 峰值 >70%、内存常态 >75%、IO wait 高。
- `sys-perf-diagnosis` 指向资源瓶颈。

## 执行流程
1. **CPU**：用 `py-spy` 抓热点函数；消除不必要循环/正则/重复计算；调整线程池大小与并发上限。
2. **内存**：用 `tracemalloc`/`objgraph` 查泄漏与大对象；优化对象生命周期与缓存大小；分析 GC 压力，降低 Full GC 频率。
3. **存储**：优化日志采集与落盘策略；压缩大文件、归档冷数据；定期清理无效缓存/历史文件。
4. **网络**：复用连接（连接池）减少握手；降低大包/重复传输；合理超时与重试。
5. **验证**：复测资源指标，确认峰值回落、无明显瓶颈。

## 工具与脚本
- CPU：`py-spy top`、`cProfile`、`threadpool` 配置。
- 内存：`tracemalloc`、`objgraph`、`gc` 日志。
- 存储/网络：日志轮转、连接池（`SQLAlchemy pool_size`）、压缩。

## 验收与 KPI（§3）
- CPU 峰值 <70%，内存常态 <75%，磁盘 IO wait ↓30%+。
- 网络重传率下降，带宽利用更平滑。

## 与本工程栈的对应
- SQLAlchemy 连接池在 `backend/app/db` 配置。
- ML 推理易产生大对象与临时张量，重点排查（`app/ml`）。
- 日志目录 `backend/logs`，需轮转策略。

## 注意事项
- 内存泄漏修复后需长时间压测验证，避免偶发。
- 调线程池/连接池须配合压测，避免过小或过大。
