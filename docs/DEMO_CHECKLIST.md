# 现场演示清单（P3 / 答辩与求职演示前必跑）

> 2026-09-23 实测基线（dws 常驻栈）：`/health` 四项全 ok，
> 6 容器 healthy（backend/worker/beat/postgres/redis/prometheus）。
> 注意：常驻容器跑的是旧镜像，`version.py` 新增的 `release_codename` 字段需重建镜像后才可见。

## 1. 一键拉起

- Windows：`powershell -ExecutionPolicy Bypass -File scripts/demo_up.ps1`
- Linux/macOS：`bash scripts/demo_up.sh`
- 脚本自动检测 80/443/3001/8001/9090 占用；Grafana 3001 冲突最常见（旧栈残留）：
  `docker ps | grep grafana` → `docker compose -p <旧栈> down` 或调整本栈映射。

## 2. 健康断言（全部通过才能开讲）

```bash
curl http://127.0.0.1:8001/health                 # database/redis/celery_worker/models 全 ok
curl http://127.0.0.1:8001/api/v1/version         # 版本口径 = config SSOT
docker exec dws-celery-worker celery -A app.core.celery_app inspect ping  # pong
```

## 3. E2E 回归（演示前一晚跑）

```bash
cd backend && pytest tests/ -q -x            # 后端（需 Redis；缺失时 needs_redis 用例 2s 内快速失败）
cd frontend && npx vitest run                # 前端 1119 例
npx playwright test                          # 17 spec（含 alerting-e2e 12 步告警闭环）
```

## 4. 口径一页纸（被追问时直接念）

- 版本 SSOT：`backend/app/core/config.py`（app 3.1.0，镜像 tag 同值）。
- 生产模型 = 结构化 LR v1.23（F1 0.8955/AUC 0.9174）；论文选型 = CatBoost；
  其余（GBDT m1/TF-IDF+LR/MLP/融合m4/BERT ONNX）= 实验基线。详见 `backend/models/MODEL_REGISTRY.md`。
- 不做、为什么：Phase 5 UI 重组与 physiological-multimodal 为 deferred/wontfix（见归档），
  GBDT m1 因低于 LR 基线未投产（诚实记录）。

## 5. 离线预案

- 国内网络 docker.io 拉取慢：提前 `docker compose build` 并 `docker save` 打离线包。
- 模型/数据 1.4GB 不在 git：`python scripts/fetch_models.py --seed-only` 预拉最小集。
