# ISS-06 运行期资源基线报告

> 维度：资源（CPU / 内存 / IO / 线程） ｜ 优先级：P1 ｜ 阶段：WF-0 ｜ 技能：sys-resource-tuning
> 状态：**已采集 —— postgres+redis 全栈实测**

## 1. 背景

资源基线缺失，历史上只能靠"APM 数据 pending"占位。本任务在**带 Redis 的真实部署态**（而非 sqlite 单文件）下，对运行中的后端进程施加负载并采样进程级与容器级资源，建立可复现的基线。

> 诚实声明：这是**本地单 worker** 实例的基线，非生产多 worker / 容器 cgroup 限制口径。进程级 CPU% 可 >100（多核占满），与容器 `limits` 限制下的 CPU 口径不同。生产容量评估需多 worker + 真实数据集重测。

## 2. 环境

| 项 | 值 |
|---|---|
| 后端 | FastAPI + uvicorn，单 worker，PID **32724**，监听 127.0.0.1:8000 |
| 数据库 | `ci-postgres`（postgres:15，映射 5433，testdb） |
| 缓存 | `dws-redis`（redis:7-alpine，映射 6379，无密码） |
| 负载 | httpx ThreadPoolExecutor，60s，并发 20，共 660 请求（/health + /health/ready + /api/v1/reviews 鉴权墙） |
| 采样 | psutil 每 0.5s 一次（共 80 样本），docker stats 每 ~5s 一次（共 8 快照） |
| 主机 RAM | 16935 MB |

## 3. 实测结果

### 3.1 后端进程（PID 32724）

| 指标 | 实测值 | 目标 | 结论 |
|---|---|---|---|
| CPU 峰值 | **15.6%**（进程级） | < 70% | 余量充足 |
| 稳态 RSS | **675.8 MB**（占主机 4.0%） | < 75% | 余量充足 |
| 峰值线程数 | **53** | — | 偏高，疑与 ws.py pubsub 后台任务相关 |
| 磁盘读 | 0.0 MB / 60s | ↓ | 可忽略 |
| 磁盘写 | 0.15 MB / 60s | ↓ | 可忽略 |

> RSS 在 60s 内极其平稳（steady 675.8 / peak 677.7），无内存泄漏迹象。磁盘 IO 可忽略，因为后端本身无状态、数据全在外部 postgres。

### 3.2 容器开销（docker stats）

| 容器 | CPU | 内存 | 内存占比 |
|---|---|---|---|
| ci-postgres | 0 – 0.87% | ~54 MiB | 0.69% |
| dws-redis | 0.58 – 0.65% | ~6 MiB | 0.08% |

两容器在基线负载下 CPU / 内存占用极低，不是瓶颈。

## 4. 分析

1. **资源余量极大**：单 worker 在 ~11 QPS 负载下 CPU 仅 15.6%、内存 4%。真实生产若多 worker，按 worker 数线性放大（如 4 worker ≈ 2.7 GB RSS、CPU 随请求分布），仍在常规规格内。
2. **53 线程偏高**：单 worker 通常只需少数线程（事件循环 + 线程池）。偏高与 `ws.py` 的 pubsub 后台任务（此前观测到 redis `TimeoutError` 重试循环）很可能相关 —— 该后台噪声不仅浪费线程，也可能拖慢事件循环（见 ISS-12 长尾延迟）。
3. **磁盘非瓶颈**：后端无本地持久化热点，IO 可忽略。

## 5. 复现命令

```bash
# 1) 起依赖（已在运行）
docker start ci-postgres dws-redis

# 2) 准备 venv 依赖
backend/.venv/Scripts/python.exe -m pip install psutil httpx

# 3) 建表 + 默认租户 + 启动（详见会话记录 _bootstrap_pg.py）
#    alembic 的依赖顺序有缺陷，改用 Base.metadata.create_all 建 39 表；
#    启动前须 INSERT INTO tenants(id,name,code,status) VALUES(1,'Default Tenant','default','active')
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4) 资源基线采样（自动按 8000 端口 LISTENING PID 定位）
cd backend && .venv/Scripts/python.exe _resource_baseline.py
# 输出：backend/_resource_baseline.json
```

## 6. 状态与后续

- **已实测**：资源基线已从 pending 变为可量化数值（见 `KPI-基线.json` → `resource.*`）。
- **后续**：
  - 生产多 worker + cgroup limits 下重测，得到容器口径的 CPU/Mem 上限。
  - 排查 `ws.py` pubsub 后台任务（53 线程 + redis 超时重试），见 ISS-12。
