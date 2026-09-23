# 系统优化后续完整计划 (System Optimization Follow-up Plan)

> **项目名称**: 基于多模态融合的大学生抑郁症预警与干预系统
> **文档版本**: v1.0
> **基线文档**: [SYSTEM_OPTIMIZATION_PLAN.md](./SYSTEM_OPTIMIZATION_PLAN.md) / [SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md](./SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md)
> **创建日期**: 2026-07-03
> **执行周期**: 2026-07-04 ~ 2026-08-14 (W13 ~ W14, P5 阶段, 共 6 周)
> **关联检验报告**: 2026-07-03 系统优化任务完成情况检验（16 项策略: 10 完成 / 4 部分完成 / 2 未完成）

---

## 目录 (Table of Contents)

1. [执行概要 (Executive Summary)](#1-执行概要-executive-summary)
2. [待办事项总览](#2-待办事项总览)
3. [详细实施计划](#3-详细实施计划)
   - 3.1 [SEC-A: 依赖项 SCA 扫描](#31-sec-a-依赖项-sca-扫描)
   - 3.2 [SEC-C: Secrets 管理 SOP](#32-sec-c-secrets-管理-sop)
   - 3.3 [P-D: PDF 生成 Celery 队列化](#33-p-d-pdf-生成-celery-队列化)
   - 3.4 [SEC-B: 容器镜像 trivy 扫描](#34-sec-b-容器镜像-trivy-扫描)
   - 3.5 [M-A: 架构文档 C4 + ADR](#35-m-a-架构文档-c4--adr)
   - 3.6 [R-C: ObservabilityExporter 事件驱动改造](#36-r-c-observabilityexporter-事件驱动改造)
4. [整体时间规划](#4-整体时间规划)
5. [资源需求与分配](#5-资源需求与分配)
6. [风险评估与应对措施](#6-风险评估与应对措施)
7. [质量保障与验收标准](#7-质量保障与验收标准)
8. [交付物清单](#8-交付物清单)

---

## 1. 执行概要 (Executive Summary)

### 1.1 背景

依据 2026-07-03 完成的系统优化任务检验报告，原 SYSTEM_OPTIMIZATION_PLAN.md 中规划的 16 项策略已有 10 项完成、4 项部分完成、2 项未完成。本计划针对剩余 6 项待办（2 项未完成 + 4 项部分完成）制定详细实施方案，确保系统优化工作闭环。

### 1.2 总体目标

| 维度 | 当前状态 | 目标状态 | 关键 KPI |
|------|---------|---------|---------|
| **依赖项安全扫描** | 无 SCA 工具 | CI 集成 pip-audit + 漏洞告警 | CI 每次构建自动扫描，严重漏洞阻塞合并 |
| **Secrets 管理** | 引用脚本不存在 | 完整轮换 SOP + 自动化脚本 | 90 天周期强制轮换，轮换过程零停机 |
| **PDF 生成架构** | 进程内线程池 | Celery 分布式队列 | 跨节点调度，单 PDF 生成不阻塞 API |
| **容器镜像安全** | 无镜像扫描 | trivy CI 集成 | HIGH/CRITICAL 漏洞零容忍 |
| **架构文档完整性** | 单一 .md 文件 | C4 模型 + ADR 记录 | 4 层 C4 图 + 至少 10 篇 ADR |
| **可观测性延迟** | 60s 周期轮询 | 事件驱动实时发布 | 端到端延迟 < 5s |

### 1.3 执行原则

1. **安全优先**: SEC-A / SEC-C / SEC-B 三项安全类待办优先实施
2. **零停机**: 所有改造必须支持灰度发布，不影响线上服务
3. **测试驱动**: 每项改造配套单元测试 + 集成测试 + 回归测试
4. **文档同步**: 代码变更与文档更新同步提交，PR 必须含文档 diff
5. **可观测**: 每项改造必须暴露 Prometheus 指标，便于回归验证

---

## 2. 待办事项总览

| 编号 | 任务 | 优先级 | 类型 | 预估工作量 | 阶段 |
|------|------|--------|------|-----------|------|
| SEC-A | 依赖项 SCA 扫描 | 🔴 高 | 未完成 | 小 (1 天) | P5-W1 |
| SEC-C | Secrets 管理 SOP | 🔴 高 | 未完成 | 中 (3 天) | P5-W1~W2 |
| P-D | PDF 生成 Celery 队列化 | 🟡 中 | 部分完成 | 中 (3 天) | P5-W3 |
| SEC-B | 容器镜像 trivy 扫描 | 🟡 中 | 部分完成 | 小 (1 天) | P5-W3 |
| M-A | 架构文档 C4 + ADR | 🟡 中 | 部分完成 | 中 (4 天) | P5-W4~W5 |
| R-C | ObservabilityExporter 事件驱动 | 🟢 低 | 部分完成 | 大 (5 天) | P5-W5~W6 |

**总计**: 6 项待办 / 17 人日 / 6 周周期

---

## 3. 详细实施计划

### 3.1 SEC-A: 依赖项 SCA 扫描

#### 3.1.1 背景与目标

**当前问题**:
- 项目依赖 200+ Python 包 (requirements.txt + requirements-dev.txt)，无任何自动化漏洞扫描
- GitHub Actions 9 个 workflow 均未含 SCA 步骤
- 依赖项 CVE 漏洞只能靠人工排查，存在安全盲区

**目标**:
- CI 每次构建自动扫描依赖项漏洞
- 严重漏洞 (HIGH/CRITICAL) 阻塞 PR 合并
- 每周生成依赖项安全报告，发送至运维群

#### 3.1.2 实施步骤

**Step 1: 工具选型与安装** (0.5 天)

选用 `pip-audit` (官方推荐, PyPI 数据源) + `safety` (商业数据库, 兜底) 双重扫描。

```bash
# 添加到 backend/requirements-dev.txt
pip-audit>=2.7.0
safety>=3.2.0
```

**Step 2: 创建 GitHub Actions workflow** (0.5 天)

新建 [.github/workflows/dependency-scan.yml](file:///e:/code/bysj/.github/workflows/dependency-scan.yml):

```yaml
name: Dependency Security Scan

on:
  pull_request:
    branches: [main, develop]
  schedule:
    # 每周一 02:00 UTC (北京时间 10:00) 全量扫描
    - cron: '0 2 * * 1'

jobs:
  pip-audit:
    name: pip-audit Scan
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - name: Install pip-audit
        run: pip install pip-audit>=2.7.0
      - name: Scan backend dependencies
        working-directory: backend
        run: |
          pip-audit \
            --requirement requirements.txt \
            --requirement requirements-dev.txt \
            --format json \
            --output pip-audit-report.json \
            --strict
          # 严重漏洞 (HIGH/CRITICAL) 退出码非零, 阻塞合并
      - name: Upload scan report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pip-audit-report
          path: backend/pip-audit-report.json
          retention-days: 30

  safety-scan:
    name: Safety Scan (Cross-check)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install safety
        run: pip install safety>=3.2.0
      - name: Scan with safety
        working-directory: backend
        run: |
          safety scan \
            --file requirements.txt \
            --output json \
            --save-safety-report safety-report.json
      - name: Upload safety report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: safety-report
          path: backend/safety-report.json
          retention-days: 30
```

**Step 3: 在 pr-quality-gates.yml 中添加依赖扫描 job** (0.2 天)

修改 [.github/workflows/pr-quality-gates.yml](file:///e:/code/bysj/.github/workflows/pr-quality-gates.yml)，在 `quality-gate-summary.needs` 中加入 `pip-audit` 依赖，使 SCA 失败阻塞 PR 合并。

**Step 4: 处理已知漏洞** (0.3 天)

- 运行 `pip-audit -r requirements.txt` 生成基线报告
- 对 HIGH/CRITICAL 漏洞: 升级到修复版本或添加 `--ignore-vuln` 例外（必须经安全负责人审批）
- 对 MEDIUM/LOW 漏洞: 记录到 `docs/security/known-vulnerabilities.md` 跟踪

#### 3.1.3 验收标准

- [ ] `pip-audit` 在 CI 中成功运行，输出 JSON 报告
- [ ] `safety` 作为交叉验证扫描器运行
- [ ] HIGH/CRITICAL 漏洞阻塞 PR 合并
- [ ] 每周一定时全量扫描，报告归档 30 天
- [ ] 文档 `docs/security/dependency-scan.md` 说明扫描策略与例外流程

#### 3.1.4 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 依赖项含未修复的 0-day 漏洞 | 中 | 高 | 添加 `--ignore-vuln` 例外 + 监控 upstream 修复进度 |
| pip-audit 误报 | 低 | 中 | safety 交叉验证 + 人工审计 |
| CI 扫描时间过长 | 中 | 低 | 缓存 pip 下载 + 并行扫描 requirements.txt / requirements-dev.txt |

---

### 3.2 SEC-C: Secrets 管理 SOP

#### 3.2.1 背景与目标

**当前问题**:
- [config.py:282](file:///e:/code/bysj/backend/app/core/config.py#L282) 注释引用 `scripts/rotate_pii_keys.py` 但**该脚本不存在**
- 无 `docs/ops/` 目录或 Secrets 轮换 SOP 文档
- 无密钥生命周期管理流程

**目标**:
- 补全 PII 密钥轮换脚本
- 建立 4 类密钥 (PII / JWT / Webhook / Metrics Token) 的轮换 SOP
- 文档化密钥生成、分发、轮换、撤销全流程

#### 3.2.2 实施步骤

**Step 1: 创建 PII 密钥轮换脚本** (1 天)

新建 [backend/scripts/rotate_pii_keys.py](file:///e:/code/bysj/backend/scripts/rotate_pii_keys.py):

```python
"""PII 加密密钥轮换脚本.

用法:
    # 演练模式 (dry-run, 仅打印计划不执行)
    python scripts/rotate_pii_keys.py --dry-run

    # 实际轮换 (会修改 .env 文件)
    python scripts/rotate_pii_keys.py --new-key <NEW_KEY>

    # 从环境变量读取新密钥
    export NEW_PII_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    python scripts/rotate_pii_keys.py --new-key-env NEW_PII_KEY

轮换流程:
    1. 生成新 Fernet 密钥
    2. 将旧密钥加入 pii_previous_keys (逗号分隔, 支持多代回退)
    3. 重新加密所有 PII 字段 (email/phone/emergency_contact)
    4. 验证解密成功后, 清空 pii_previous_keys (可选, 保留 1 周观察期)

注意:
    - 轮换期间服务不停机 (pii_previous_keys 支持旧密钥解密回退)
    - 轮换必须在低峰期执行 (避免 re-encrypt 长事务锁表)
    - 轮换前必须备份 .env 文件和数据库快照
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 添加 backend 目录到 sys.path, 支持从项目根目录运行
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def generate_new_key() -> str:
    """生成新的 Fernet 密钥."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def reencrypt_all_pii(new_key: str, old_keys: list[str]) -> dict:
    """使用新密钥重新加密所有 PII 字段.

    Args:
        new_key: 新 Fernet 密钥
        old_keys: 旧密钥列表 (用于解密回退)

    Returns:
        统计信息: {table: reencrypted_count}
    """
    import asyncio
    from sqlalchemy import select, update
    from app.core.database import AsyncSessionLocal
    from app.core.pii_crypto import PiiCrypto
    from app.models.user import User

    async def _reencrypt() -> dict:
        stats = {"users": 0}
        new_crypto = PiiCrypto(new_key)
        old_crypto_instances = [PiiCrypto(k) for k in old_keys] if old_keys else []

        async with AsyncSessionLocal() as db:
            # 分批处理避免内存溢出
            batch_size = 100
            offset = 0
            while True:
                result = await db.execute(
                    select(User).offset(offset).limit(batch_size)
                )
                users = result.scalars().all()
                if not users:
                    break

                for user in users:
                    for field in ["email", "phone", "emergency_contact"]:
                        encrypted = getattr(user, field, None)
                        if not encrypted:
                            continue
                        # 尝试用旧密钥解密
                        plaintext = None
                        for old_crypto in old_crypto_instances:
                            try:
                                plaintext = old_crypto.decrypt(encrypted)
                                break
                            except Exception:
                                continue
                        if plaintext is None:
                            # 可能已经是新密钥加密, 跳过
                            continue
                        # 用新密钥重新加密
                        new_encrypted = new_crypto.encrypt(plaintext)
                        setattr(user, field, new_encrypted)

                await db.flush()
                stats["users"] += len(users)
                offset += batch_size

            await db.commit()
        return stats

    return asyncio.run(_reencrypt())


def update_env_file(new_key: str, previous_keys: list[str]) -> None:
    """更新 .env 文件中的 PII_ENCRYPTION_KEY 和 PII_PREVIOUS_KEYS.

    Args:
        new_key: 新密钥
        previous_keys: 旧密钥列表 (按时间倒序)
    """
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        raise FileNotFoundError(f".env not found at {env_path}")

    # 备份 .env
    backup_path = env_path.with_suffix(".env.backup")
    env_path.rename(backup_path)

    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open(env_path, "w", encoding="utf-8") as f:
            for line in lines:
                if line.startswith("PII_ENCRYPTION_KEY="):
                    f.write(f"PII_ENCRYPTION_KEY={new_key}\n")
                elif line.startswith("PII_PREVIOUS_KEYS="):
                    f.write(f"PII_PREVIOUS_KEYS={','.join(previous_keys)}\n")
                else:
                    f.write(line)
    except Exception:
        # 恢复备份
        env_path.unlink(missing_ok=True)
        backup_path.rename(env_path)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="PII key rotation tool")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--new-key", help="New Fernet key (generates one if not provided)")
    parser.add_argument("--new-key-env", help="Environment variable containing new key")
    args = parser.parse_args()

    # 加载当前 settings
    from app.core.config import settings

    current_key = settings.pii_encryption_key
    if not current_key:
        print("[ERROR] PII_ENCRYPTION_KEY not configured, cannot rotate")
        return 1

    # 确定新密钥
    if args.new_key:
        new_key = args.new_key
    elif args.new_key_env:
        new_key = os.environ.get(args.new_key_env)
        if not new_key:
            print(f"[ERROR] Env var {args.new_key_env} not set")
            return 1
    else:
        new_key = generate_new_key()
        print(f"[INFO] Generated new key: {new_key}")

    # 计算旧密钥列表
    old_keys_str = settings.pii_previous_keys or ""
    previous_keys = [k for k in old_keys_str.split(",") if k.strip()]
    if current_key not in previous_keys:
        previous_keys.insert(0, current_key)
    # 保留最近 3 代密钥
    previous_keys = previous_keys[:3]

    print(f"[INFO] Current key: {current_key[:8]}...")
    print(f"[INFO] Previous keys count: {len(previous_keys)}")

    if args.dry_run:
        print("[DRY-RUN] Plan:")
        print(f"  1. Update PII_ENCRYPTION_KEY={new_key[:8]}...")
        print(f"  2. Update PII_PREVIOUS_KEYS={','.join(k[:8] + '...' for k in previous_keys)}")
        print(f"  3. Re-encrypt all PII fields (estimated users: ?)")
        return 0

    # 确认执行
    confirm = input("Type ROTATE to confirm: ")
    if confirm != "ROTATE":
        print("[ABORT] User cancelled")
        return 1

    # Step 1: 更新 .env
    print("[STEP 1] Updating .env file...")
    update_env_file(new_key, previous_keys)
    print("[STEP 1] Done")

    # Step 2: 重新加密所有 PII 字段
    print("[STEP 2] Re-encrypting all PII fields...")
    stats = reencrypt_all_pii(new_key, previous_keys)
    print(f"[STEP 2] Done: {stats}")

    print("\n[SUCCESS] Rotation complete")
    print("[NEXT] Restart backend service to load new key")
    print("[NEXT] Keep PII_PREVIOUS_KEYS for 1 week, then clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: 创建 Secrets 管理 SOP 文档** (1.5 天)

新建 [docs/ops/secrets-rotation-sop.md](file:///e:/code/bysj/docs/ops/secrets-rotation-sop.md)，内容覆盖:

```markdown
# Secrets 轮换标准操作程序 (SOP)

## 1. 适用范围

本 SOP 适用于以下 4 类 Secrets 的生命周期管理:

| Secret 名称 | 用途 | 轮换周期 | 影响范围 |
|------------|------|---------|---------|
| PII_ENCRYPTION_KEY | PII 字段加密 (email/phone/emergency_contact) | 90 天 | User 表加密字段 |
| JWT_SECRET_KEY | JWT 签名 | 90 天 | 所有已签发 token 失效, 用户需重新登录 |
| ALERTMANAGER_WEBHOOK_SECRET | AlertManager Webhook 鉴权 | 60 天 | AlertManager + 后端 webhook 接收 |
| METRICS_ACCESS_TOKEN | Prometheus /metrics 端点访问 | 60 天 | Prometheus scrape 配置 |

## 2. 轮换前置条件

- [ ] 拥有 .env 文件读写权限
- [ ] 拥有数据库读权限 (PII 轮换需要)
- [ ] 拥有 Kubernetes/docker-compose 重启权限
- [ ] 已通知相关团队 (至少提前 24 小时)
- [ ] 已创建数据库快照备份

## 3. PII_ENCRYPTION_KEY 轮换流程

### 3.1 准备阶段 (T-1 天)

1. 生成新密钥:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. 数据库快照备份:
   ```bash
   docker exec dws-postgres pg_dump -U depress_admin depression_system > backup_$(date +%Y%m%d).sql
   ```
3. 通知用户: "将于明日 02:00 进行密钥轮换, 预计耗时 10 分钟"

### 3.2 执行阶段 (T 日 02:00 低峰期)

1. 演练模式验证:
   ```bash
   cd backend
   python scripts/rotate_pii_keys.py --dry-run --new-key <NEW_KEY>
   ```

2. 实际执行:
   ```bash
   python scripts/rotate_pii_keys.py --new-key <NEW_KEY>
   ```

3. 重启后端服务:
   ```bash
   docker-compose restart backend celery_worker celery_beat
   ```

### 3.3 验证阶段 (T+0 ~ T+7 天)

- [ ] T+0: 健康检查通过 `/health/ready`
- [ ] T+0: 登录测试 (验证 JWT 不受影响)
- [ ] T+0: PII 字段查询测试 (验证解密成功)
- [ ] T+1: 监控 Sentry 无加密相关错误
- [ ] T+7: 清空 `PII_PREVIOUS_KEYS`, 完成 1 个观察周期

### 3.4 回滚流程

若轮换后出现异常:

1. 恢复 .env.backup:
   ```bash
   cp .env.backup .env
   ```
2. 从数据库快照恢复:
   ```bash
   docker exec -i dws-postgres psql -U depress_admin depression_system < backup_YYYYMMDD.sql
   ```
3. 重启服务

## 4. JWT_SECRET_KEY 轮换流程

### 4.1 影响

- 所有已签发的 access_token 和 refresh_token 立即失效
- 用户需重新登录
- refresh_token cookie 失效

### 4.2 执行步骤

1. 生成新密钥:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. 更新 .env: `JWT_SECRET_KEY=<NEW_KEY>`
3. 重启 backend + celery_worker
4. 通知用户重新登录

## 5. ALERTMANAGER_WEBHOOK_SECRET 轮换流程

1. 生成新密钥:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. 更新后端 .env: `ALERTMANAGER_WEBHOOK_SECRET=<NEW_KEY>`
3. 更新 AlertManager 配置: `infra/alertmanager/alertmanager.yml`
4. 重启 backend + alertmanager 服务

## 6. METRICS_ACCESS_TOKEN 轮换流程

1. 生成新密钥
2. 更新后端 .env: `METRICS_ACCESS_TOKEN=<NEW_KEY>`
3. 更新 Prometheus scrape 配置: `infra/prometheus/prometheus.yml` 的 `bearer_token`
4. 重启 backend + prometheus 服务

## 7. 应急联系

- 安全负责人: <填写>
- 运维负责人: <填写>
- DBA: <填写>
```

**Step 3: 创建 docs/ops/ 目录与索引** (0.5 天)

新建 [docs/ops/README.md](file:///e:/code/bysj/docs/ops/README.md) 索引所有运维 SOP 文档。

#### 3.2.3 验收标准

- [ ] `scripts/rotate_pii_keys.py` 脚本存在且可运行 (dry-run 模式)
- [ ] `docs/ops/secrets-rotation-sop.md` 文档完整覆盖 4 类密钥
- [ ] 文档含准备/执行/验证/回滚 4 阶段流程
- [ ] 在 staging 环境完成 1 次完整演练并截图归档

#### 3.2.4 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 轮换过程中数据库长事务锁表 | 中 | 高 | 低峰期执行 + 分批处理 (batch_size=100) |
| 新密钥未正确加载 | 低 | 高 | 启动健康检查 + 自动回滚脚本 |
| PII_PREVIOUS_KEYS 配置错误导致解密失败 | 中 | 高 | 保留 1 周观察期 + 回滚流程演练 |

---

### 3.3 P-D: PDF 生成 Celery 队列化

#### 3.3.1 背景与目标

**当前问题**:
- [risk_service.py:56](file:///e:/code/bysj/backend/app/services/risk_service.py#L56) 使用 `ThreadPoolExecutor(max_workers=4)` 进程内线程池
- 多实例部署时无法跨节点调度 PDF 生成任务
- 服务重启时正在进行的 PDF 任务会丢失

**目标**:
- PDF 生成任务通过 Celery 队列调度
- 支持跨节点任务分发
- 任务状态持久化到 Redis (PdfJobStore 升级)

#### 3.3.2 实施步骤

**Step 1: 创建 Celery PDF 任务** (1 天)

新建 [backend/app/tasks/pdf_report.py](file:///e:/code/bysj/backend/app/tasks/pdf_report.py):

```python
"""P1-4: PDF 报告生成 Celery 异步任务.

将原 risk_service._generate_pdf_report 升级为 Celery 任务,
支持跨节点调度与任务持久化.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.celery_app import celery_app
from app.services.pdf_job_store import PdfJobStore, PdfJob

logger = logging.getLogger(__name__)

# 全局任务存储 (单实例, 多实例时升级为 Redis Hash)
_pdf_job_store = PdfJobStore()


@celery_app.task(
    name="app.tasks.pdf_report.generate_pdf_report",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    time_limit=300,        # 硬超时 5 分钟
    soft_time_limit=270,   # 软超时 4.5 分钟
)
def generate_pdf_report(
    self,
    job_id: str,
    user_id: int,
    user_name: str,
    created_by: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Celery 任务: 生成 PDF 报告.

    Args:
        job_id: 任务 ID (前端轮询用)
        user_id: 报告归属用户 ID
        user_name: 用户名 (PDF 显示用)
        created_by: 任务创建者 ID
        items: 风险评估数据列表

    Returns:
        任务状态字典 (含 pdf_bytes 供 job_store 取回)
    """
    from app.services.risk_service import RiskService

    job = _pdf_job_store.get(job_id)
    if job is None:
        logger.error("PDF job not found: %s", job_id)
        return {"status": "failed", "error": "job_not_found"}

    job.status = "running"
    job.started_at = _now_iso()
    _pdf_job_store.update(job)

    try:
        # 复用原 RiskService 的 PDF 生成逻辑 (同步函数)
        service = RiskService()
        pdf_bytes = service._generate_pdf_report(user_id, items)

        job.status = "completed"
        job.completed_at = _now_iso()
        job.progress = 100
        job.pdf_bytes = pdf_bytes
        job.file_size = len(pdf_bytes)
        job.page_count = _count_pdf_pages(pdf_bytes)
        _pdf_job_store.update(job)

        logger.info(
            "PDF job %s completed (size=%d bytes, pages=%d)",
            job_id, job.file_size, job.page_count,
        )
        return job.to_status_dict()

    except Exception as exc:
        logger.exception("PDF job %s failed: %s", job_id, exc)
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = _now_iso()
        _pdf_job_store.update(job)

        # 重试 (最多 3 次)
        if self.request.retries < 3:
            raise self.retry(exc=exc)
        return job.to_status_dict()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """简单统计 PDF 页数 (基于 /Type /Page 计数)."""
    try:
        content = pdf_bytes.decode("latin-1", errors="ignore")
        return content.count("/Type /Page")
    except Exception:
        return 0
```

**Step 2: 修改 reports.py API 端点** (1 天)

修改 [backend/app/api/v1/reports.py](file:///e:/code/bysj/backend/app/api/v1/reports.py):

```python
# 新增端点: 提交 PDF 生成任务 (返回 job_id 供轮询)
@router.post("/reports/user-risk/pdf/async", response_model=PdfJobStatus)
async def submit_pdf_job(
    request: PdfJobRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PdfJobStatus:
    """异步提交 PDF 生成任务.

    返回 job_id, 客户端通过 GET /reports/pdf/status/{job_id} 轮询状态.
    """
    from app.tasks.pdf_report import generate_pdf_report, _pdf_job_store
    from app.services.risk_service import RiskService

    # 获取风险数据 (复用原逻辑)
    service = RiskService()
    items = await service.get_user_risk_items(db, request.user_id, request.days)

    # 创建任务
    job_id = str(uuid.uuid4())
    job = PdfJob(
        id=job_id,
        status="queued",
        user_name=request.user_name,
        created_by=current_user.id,
        created_at=_now_iso(),
    )
    _pdf_job_store.create(job)

    # 派发到 Celery 队列
    generate_pdf_report.delay(
        job_id=job_id,
        user_id=request.user_id,
        user_name=request.user_name,
        created_by=current_user.id,
        items=items,
    )

    return PdfJobStatus(**job.to_status_dict())


@router.get("/reports/pdf/status/{job_id}", response_model=PdfJobStatus)
async def get_pdf_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> PdfJobStatus:
    """查询 PDF 任务状态."""
    from app.tasks.pdf_report import _pdf_job_store

    job = _pdf_job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    # 鉴权: 仅创建者或管理员可查询
    if job.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="forbidden")
    return PdfJobStatus(**job.to_status_dict())


@router.get("/reports/pdf/download/{job_id}")
async def download_pdf(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """下载已完成的 PDF."""
    from app.tasks.pdf_report import _pdf_job_store

    job = _pdf_job_store.get(job_id)
    if job is None or job.status != "completed" or job.pdf_bytes is None:
        raise HTTPException(status_code=404, detail="pdf_not_ready")

    if job.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="forbidden")

    return Response(
        content=job.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="risk_report_{job_id}.pdf"',
        },
    )
```

**Step 3: 保留旧 ThreadPoolExecutor 端点作为兼容** (0.5 天)

保留 [risk_service.py:56](file:///e:/code/bysj/backend/app/services/risk_service.py#L56) 的 `_pdf_executor` 与原同步端点，添加 `DeprecationWarning`，3 个月后移除。

**Step 4: 单元测试 + 集成测试** (0.5 天)

新建 [backend/tests/test_pdf_celery.py](file:///e:/code/bysj/backend/tests/test_pdf_celery.py):

- `test_submit_pdf_job_returns_job_id`
- `test_get_pdf_job_status_queued`
- `test_get_pdf_job_status_completed`
- `test_download_pdf_unauthorized_user`
- `test_pdf_job_retry_on_failure`
- `test_pdf_job_timeout_after_300s`

#### 3.3.3 验收标准

- [ ] Celery 任务 `app.tasks.pdf_report.generate_pdf_report` 可正常派发
- [ ] API 端点 `POST /reports/user-risk/pdf/async` 返回 job_id
- [ ] API 端点 `GET /reports/pdf/status/{job_id}` 返回任务状态
- [ ] API 端点 `GET /reports/pdf/download/{job_id}` 返回 PDF 二进制
- [ ] 任务失败自动重试 3 次
- [ ] 单元测试覆盖率 ≥ 90%

#### 3.3.4 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| Celery worker 与 FastAPI 进程间序列化失败 | 中 | 高 | items 使用 JSON 可序列化结构, 避免 SQLAlchemy 对象 |
| PdfJobStore 进程内存储多实例不一致 | 高 | 中 | 标注 TODO 升级为 Redis Hash, 当前单实例部署可接受 |
| 长时间 PDF 任务阻塞 Celery worker | 中 | 中 | time_limit=300s + 单 worker concurrency=2 |

---

### 3.4 SEC-B: 容器镜像 trivy 扫描

#### 3.4.1 背景与目标

**当前问题**:
- 已有 Dockerfile + docker-compose.yml 完整编排 (9 个服务)
- 但无任何容器镜像漏洞扫描
- 镜像构建后直接推送, 可能含已知 OS 包漏洞

**目标**:
- CI 中集成 `trivy` 镜像扫描
- HIGH/CRITICAL 漏洞阻塞镜像推送
- 每周全量扫描已发布镜像

#### 3.4.2 实施步骤

**Step 1: 创建 trivy 扫描 workflow** (0.5 天)

新建 [.github/workflows/container-scan.yml](file:///e:/code/bysj/.github/workflows/container-scan.yml):

```yaml
name: Container Image Security Scan

on:
  pull_request:
    branches: [main, develop]
    paths:
      - 'backend/Dockerfile'
      - 'frontend/Dockerfile'
      - 'docker-compose.yml'
  schedule:
    # 每周日 03:00 UTC 全量扫描已发布镜像
    - cron: '0 3 * * 0'

jobs:
  scan-backend:
    name: Scan Backend Image
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - name: Build backend image
        working-directory: backend
        run: |
          docker build -f Dockerfile -t dws-backend:scan .
      - name: Run Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: dws-backend:scan
          format: 'sarif'
          output: 'trivy-backend-results.sarif'
          severity: 'HIGH,CRITICAL'
          exit-code: '1'  # HIGH/CRITICAL 漏洞导致 CI 失败
          ignore-unfixed: true
      - name: Upload SARIF report
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-backend-results.sarif
      - name: Upload scan artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: trivy-backend-report
          path: trivy-backend-results.sarif
          retention-days: 30

  scan-frontend:
    name: Scan Frontend Image
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - name: Build frontend image
        working-directory: frontend
        run: |
          docker build -f Dockerfile -t dws-frontend:scan .
      - name: Run Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: dws-frontend:scan
          format: 'sarif'
          output: 'trivy-frontend-results.sarif'
          severity: 'HIGH,CRITICAL'
          exit-code: '1'
          ignore-unfixed: true
      - name: Upload SARIF report
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-frontend-results.sarif
```

**Step 2: 创建 .trivyignore** (0.2 天)

新建 [backend/.trivyignore](file:///e:/code/bysj/backend/.trivyignore) 记录已知接受风险的漏洞 (每个条目必须含原因说明):

```
# CVE-XXXX-XXXXX  # 原因: 上游无修复版本, 影响范围有限, 已通过 WAF 规则缓解
```

**Step 3: 在 pr-quality-gates.yml 中加入依赖** (0.3 天)

修改 [pr-quality-gates.yml](file:///e:/code/bysj/.github/workflows/pr-quality-gates.yml), 在 `quality-gate-summary.needs` 中加入 `scan-backend` 和 `scan-frontend` (仅在 Dockerfile 变更时触发)。

#### 3.4.3 验收标准

- [ ] `container-scan.yml` 在 PR 中触发 trivy 扫描
- [ ] HIGH/CRITICAL 漏洞导致 CI 失败
- [ ] SARIF 报告上传到 GitHub Security tab
- [ ] 每周日定时全量扫描已发布镜像
- [ ] `.trivyignore` 仅含经审批的例外项

---

### 3.5 M-A: 架构文档 C4 + ADR

#### 3.5.1 背景与目标

**当前问题**:
- 仅有 [docs/architecture.md](file:///e:/code/bysj/docs/architecture.md) 单一文档
- 无 C4 模型图 (Context / Container / Component / Code)
- 无 ADR (Architecture Decision Records), 重要架构决策无记录

**目标**:
- 补全 4 层 C4 模型图 (使用 structurizr 或 mermaid)
- 建立 ADR 目录, 至少记录 10 项关键决策
- 文档可在 GitHub Markdown 中直接渲染

#### 3.5.2 实施步骤

**Step 1: 创建 C4 模型文档** (2 天)

新建以下文档:

1. [docs/architecture/c4-context.md](file:///e:/code/bysj/docs/architecture/c4-context.md) - System Context 图
   - 系统与外部用户 (学生/咨询师/管理员) 的交互
   - 外部系统 (邮件/短信/Sentry/Prometheus)
   - 使用 mermaid C4Context diagram

2. [docs/architecture/c4-container.md](file:///e:/code/bysj/docs/architecture/c4-container.md) - Container 图
   - 前端 (Vue 3 + Vite + Element Plus)
   - 后端 (FastAPI + Uvicorn)
   - Celery worker + beat
   - PostgreSQL + Redis
   - Grafana + Prometheus + Sentry
   - 使用 mermaid C4Container diagram

3. [docs/architecture/c4-component.md](file:///e:/code/bysj/docs/architecture/c4-component.md) - Component 图
   - 后端各模块 (api / core / services / models / tasks / monitoring)
   - 模块间依赖关系
   - 使用 mermaid graph TD

4. [docs/architecture/c4-code.md](file:///e:/code/bysj/docs/architecture/c4-code.md) - Code 图
   - 关键类图: ModelEngine / RiskService / ObservabilityExporter
   - 使用 mermaid classDiagram

**Step 2: 创建 ADR 目录与首批 10 篇 ADR** (2 天)

新建 [docs/architecture/adr/](file:///e:/code/bysj/docs/architecture/adr/) 目录, 每篇 ADR 遵循模板:

```markdown
# ADR-XXX: <决策标题>

## 状态 (Status)
Accepted / Proposed / Deprecated / Superseded by ADR-YYY

## 日期 (Date)
YYYY-MM-DD

## 上下文 (Context)
<问题描述与背景, 为何需要做此决策>

## 决策 (Decision)
<做出的具体决策>

## 替代方案 (Alternatives Considered)
<其他可选方案及为何不选>

## 后果 (Consequences)
- 正面: <好处>
- 负面: <代价>
- 中性: <需注意的点>

## 关联 (Related)
- 相关 ADR / 文档 / PR
```

首批 10 篇 ADR 主题:

| ADR 编号 | 主题 | 优先级 |
|---------|------|--------|
| ADR-001 | 选择 FastAPI 而非 Django/Flask | 高 |
| ADR-002 | 选择 SQLAlchemy 2.0 async + asyncpg | 高 |
| ADR-003 | 选择 Celery 而非 RQ/Dramatiq 异步任务 | 高 |
| ADR-004 | 选择 Vue 3 + Composition API 而非 Options API | 中 |
| ADR-005 | 选择 Element Plus 而非 Ant Design Vue | 中 |
| ADR-006 | 模型推理使用 asyncio.to_thread 而非专用进程 | 高 |
| ADR-007 | PII 加密使用 Fernet 对称加密而非非对称加密 | 高 |
| ADR-008 | 健康检查分层 (live/ready/startup) 三探针 | 高 |
| ADR-009 | Redis pubsub 而非 RabbitMQ 用于 WebSocket 多 worker | 中 |
| ADR-010 | 使用 Alembic 而非 SQLAlchemy create_all 进行数据库迁移 | 高 |

#### 3.5.3 验收标准

- [ ] 4 个 C4 模型文档创建, mermaid 图可在 GitHub 渲染
- [ ] ADR 目录与模板建立
- [ ] 至少 10 篇 ADR 完成 (覆盖 6 篇高优先级 + 4 篇中优先级)
- [ ] [docs/architecture.md](file:///e:/code/bysj/docs/architecture.md) 添加链接指向 C4 与 ADR

---

### 3.6 R-C: ObservabilityExporter 事件驱动改造

#### 3.6.1 背景与目标

**当前问题**:
- [observability_exporter.py](file:///e:/code/bysj/backend/app/services/observability_exporter.py) 采用 60s 周期轮询 `_compute_*` 函数
- 告警事件需等下次轮询才能反映到 Prometheus 指标
- 端到端延迟最高 60s, 不满足实时告警需求

**目标**:
- 改造为事件驱动: 监听告警/警告/Review 等关键事件, 实时更新 Prometheus 指标
- 端到端延迟 < 5s
- 保留 60s 周期作为兜底 (防止事件丢失)

#### 3.6.2 实施步骤

**Step 1: 定义事件总线接口** (1 天)

新建 [backend/app/core/event_bus.py](file:///e:/code/bysj/backend/app/core/event_bus.py):

```python
"""轻量级进程内事件总线.

使用 asyncio.Queue 实现, 单进程内的事件订阅/发布.
跨进程事件通过 Redis pubsub (复用 ws.py 模式).

事件类型:
- alert.fired: 告警触发
- alert.resolved: 告警恢复
- alert.escalated: 告警升级
- warning.created: 风险预警创建
- review.submitted: 评估复核提交
- model.drift_detected: 模型漂移检测
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# 事件处理器类型: async def handler(event_data: dict) -> None
EventHandler = Callable[[dict], Coroutine[Any, Any, None]]


class EventBus:
    """进程内异步事件总线."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10000)
        self._running = False
        self._consumer_task: asyncio.Task | None = None

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件."""
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, data: dict) -> None:
        """发布事件 (非阻塞, 队列满时丢弃并告警)."""
        event = {"type": event_type, "data": data}
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event bus queue full, dropping event: %s", event_type)

    async def start(self) -> None:
        """启动事件消费循环."""
        if self._running:
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("EventBus started")

    async def stop(self) -> None:
        """停止事件消费循环."""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus stopped")

    async def _consume_loop(self) -> None:
        """消费队列中的事件并分发给订阅者."""
        while self._running:
            try:
                event = await self._queue.get()
                event_type = event["type"]
                handlers = self._handlers.get(event_type, [])
                for handler in handlers:
                    try:
                        await handler(event["data"])
                    except Exception:
                        logger.exception(
                            "Event handler failed for type=%s", event_type
                        )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Event consume loop error")


# 全局事件总线实例
event_bus = EventBus()
```

**Step 2: 在关键业务点发布事件** (1.5 天)

修改以下文件, 在关键操作完成后发布事件:

- [backend/app/services/alert_lifecycle_service.py](file:///e:/code/bysj/backend/app/services/alert_lifecycle_service.py): `alert.fired` / `alert.resolved` / `alert.escalated`
- [backend/app/services/warning_service.py](file:///e:/code/bysj/backend/app/services/warning_service.py): `warning.created`
- [backend/app/services/review_service.py](file:///e:/code/bysj/backend/app/services/review_service.py): `review.submitted`
- [backend/app/tasks/model_drift.py](file:///e:/code/bysj/backend/app/tasks/model_drift.py): `model.drift_detected`

示例:

```python
# alert_lifecycle_service.py
from app.core.event_bus import event_bus

class AlertLifecycleService:
    async def fire_alert(self, alert_data: dict) -> Alert:
        alert = await self._create_alert(alert_data)
        # 发布事件
        await event_bus.publish("alert.fired", {
            "alert_id": alert.id,
            "severity": alert.severity,
            "rule_id": alert.rule_id,
            "fired_at": alert.fired_at.isoformat(),
        })
        return alert
```

**Step 3: ObservabilityExporter 订阅事件** (1.5 天)

修改 [observability_exporter.py](file:///e:/code/bysj/backend/app/services/observability_exporter.py):

```python
from app.core.event_bus import event_bus

class ObservabilityExporter:
    def __init__(self) -> None:
        # ... 原有字段
        self._register_event_handlers()

    def _register_event_handlers(self) -> None:
        """注册事件订阅器, 实时更新 Prometheus 指标."""
        event_bus.subscribe("alert.fired", self._on_alert_fired)
        event_bus.subscribe("alert.resolved", self._on_alert_resolved)
        event_bus.subscribe("alert.escalated", self._on_alert_escalated)
        event_bus.subscribe("warning.created", self._on_warning_created)
        event_bus.subscribe("review.submitted", self._on_review_submitted)
        event_bus.subscribe("model.drift_detected", self._on_drift_detected)

    async def _on_alert_fired(self, data: dict) -> None:
        """实时更新 alerts_fired_total Counter."""
        from app.core.metrics import alerts_fired_total
        alerts_fired_total.inc()
        logger.debug("Event alert.fired processed: %s", data)

    async def _on_alert_resolved(self, data: dict) -> None:
        from app.core.metrics import alerts_resolved_total
        alerts_resolved_total.inc()

    async def _on_warning_created(self, data: dict) -> None:
        from app.core.metrics import warnings_created_total
        warnings_created_total.inc()

    # ... 其他事件处理器

    async def start(self) -> None:
        # ... 原有启动逻辑
        await event_bus.start()
        # 保留 60s 周期作为兜底 (防止事件丢失)
        self._task = asyncio.create_task(self._loop())
```

**Step 4: lifespan 集成** (0.5 天)

修改 [backend/app/main.py](file:///e:/code/bysj/backend/app/main.py):

```python
from app.core.event_bus import event_bus

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... 原有启动
    await event_bus.start()
    # ... yield
    # 关闭阶段
    await event_bus.stop()
```

**Step 5: 单元测试 + 性能压测** (0.5 天)

新建 [backend/tests/test_event_bus.py](file:///e:/code/bysj/backend/tests/test_event_bus.py):

- `test_event_bus_subscribe_publish`
- `test_event_bus_multiple_subscribers`
- `test_event_bus_queue_full_drops_event`
- `test_event_bus_handler_exception_isolated`
- `test_observability_exporter_realtime_update` (验证事件触发后 Prometheus 指标实时更新)
- `test_event_bus_end_to_end_latency` (验证端到端延迟 < 5s)

#### 3.6.3 验收标准

- [ ] `EventBus` 类实现, 支持订阅/发布/消费循环
- [ ] 5 类关键业务事件接入事件总线
- [ ] ObservabilityExporter 订阅事件, 实时更新 Prometheus 指标
- [ ] 保留 60s 周期作为兜底
- [ ] 端到端延迟 < 5s (单元测试验证)
- [ ] 单元测试覆盖率 ≥ 90%
- [ ] [docs/architecture/adr/ADR-011-event-bus.md](file:///e:/code/bysj/docs/architecture/adr/ADR-011-event-bus.md) ADR 文档

#### 3.6.4 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 事件队列满导致事件丢失 | 低 | 中 | 队列容量 10000 + 兜底 60s 周期轮询 |
| 事件处理器异常影响业务 | 低 | 高 | 异常隔离 (try/except 单 handler) |
| 跨进程事件丢失 (Celery worker 触发) | 中 | 中 | 后续升级为 Redis pubsub 跨进程事件 |
| 内存泄漏 (handler 持有引用) | 低 | 中 | 单元测试 + 内存监控 |

---

## 4. 整体时间规划

### 4.1 6 周分阶段计划

```
W13 (07/04-07/10) │ SEC-A + SEC-C 启动
                  │ - pip-audit CI 集成 (1d)
                  │ - PII 轮换脚本开发 (1d)
                  │ - Secrets SOP 文档 (1.5d)
                  │ - staging 演练 (0.5d)
W14 (07/11-07/17) │ SEC-C 收尾 + P-D 启动
                  │ - PII 轮换演练验证 (1d)
                  │ - Celery PDF 任务开发 (1.5d)
                  │ - reports.py API 改造 (1d)
W15 (07/18-07/24) │ P-D 收尾 + SEC-B 启动
                  │ - PDF Celery 测试 (0.5d)
                  │ - trivy CI 集成 (1d)
                  │ - .trivyignore 配置 (0.2d)
                  │ - 镜像扫描验证 (0.3d)
W16 (07/25-07/31) │ M-A 启动
                  │ - C4 Context + Container (1d)
                  │ - C4 Component + Code (1d)
                  │ - ADR 模板 + ADR-001~005 (2d)
W17 (08/01-08/07) │ M-A 收尾 + R-C 启动
                  │ - ADR-006~010 (2d)
                  │ - EventBus 接口 (1d)
                  │ - 业务点事件发布 (1d)
W18 (08/08-08/14) │ R-C 收尾 + 全部验收
                  │ - ObservabilityExporter 订阅 (1d)
                  │ - lifespan 集成 + 测试 (1d)
                  │ - 整体验收 + 文档归档 (3d)
```

### 4.2 里程碑

| 里程碑 | 日期 | 交付物 |
|--------|------|--------|
| M1: 安全类完成 | 2026-07-17 | SEC-A + SEC-C 全部交付, staging 演练通过 |
| M2: PDF + 镜像扫描完成 | 2026-07-24 | P-D + SEC-B 全部交付, CI 集成验证 |
| M3: 架构文档完成 | 2026-07-31 | M-A 全部交付, C4 + 10 篇 ADR |
| M4: 事件驱动完成 | 2026-08-07 | R-C 全部交付, 端到端延迟 < 5s |
| M5: 全部验收 | 2026-08-14 | 6 项待办全部 Closed, 总结报告发布 |

---

## 5. 资源需求与分配

### 5.1 人力资源

| 角色 | 投入比例 | 负责范围 |
|------|---------|---------|
| 后端工程师 | 100% | SEC-A / SEC-C / P-D / R-C 实施 |
| DevOps 工程师 | 50% | SEC-B / CI 集成 / staging 演练 |
| 架构师 | 30% | M-A C4 + ADR 评审 |
| 安全工程师 | 20% | SEC-A / SEC-C / SEC-B 评审 |
| QA 工程师 | 50% | 测试用例编写 + 回归测试 |

### 5.2 基础设施

| 资源 | 用途 | 备注 |
|------|------|------|
| GitHub Actions 分钟数 | CI 集成 | 每月预计增加 200 分钟 |
| staging 环境 | 演练 | 复用现有 docker-compose.test |
| Sentry | 异常监控 | 复用现有 DSN |
| Prometheus | 指标验证 | 复用现有实例 |

---

## 6. 风险评估与应对措施

### 6.1 整体风险矩阵

| 风险 | 概率 | 影响 | 风险等级 | 应对措施 |
|------|------|------|---------|---------|
| PII 密钥轮换导致历史数据不可解密 | 低 | 极高 | 🔴 高 | 备份数据库 + 保留旧密钥 1 周 + 回滚演练 |
| Celery PDF 任务序列化失败 | 中 | 中 | 🟡 中 | items 严格使用 JSON 可序列化结构 |
| trivy 扫描时间过长影响 CI | 中 | 低 | 🟢 低 | 仅扫描 HIGH/CRITICAL + 缓存镜像层 |
| 事件总线内存泄漏 | 低 | 中 | 🟡 中 | 队列容量上限 10000 + 内存监控告警 |
| ADR 决策与实际实现不一致 | 中 | 低 | 🟢 低 | 每季度审计 ADR 与代码一致性 |
| 跨进程事件丢失 (Celery worker) | 中 | 中 | 🟡 中 | 保留 60s 周期轮询作为兜底 |

### 6.2 应急响应

| 场景 | 响应时间 | 应急操作 |
|------|---------|---------|
| PII 轮换导致解密失败 | 5 分钟 | 执行回滚流程: 恢复 .env.backup + 数据库快照 |
| Celery PDF 任务积压 | 15 分钟 | 临时扩容 celery_worker 副本数 |
| 事件总线故障 | 30 分钟 | 降级为 60s 周期轮询模式 (自动) |
| trivy CI 误报阻塞合并 | 1 小时 | 添加 .trivyignore + 安全负责人审批 |

---

## 7. 质量保障与验收标准

### 7.1 代码质量

- [ ] 所有新增代码通过 `ruff check` + `mypy --strict`
- [ ] 新增函数单元测试覆盖率 ≥ 90%
- [ ] 关键路径集成测试覆盖
- [ ] 所有 PR 通过 8 个 quality gate (含新增 SEC-A / SEC-B)

### 7.2 文档质量

- [ ] 每项改造配套文档 (SOP / ADR / README)
- [ ] mermaid 图可在 GitHub Markdown 中渲染
- [ ] 文档含明确的目标 / 步骤 / 验收 / 回滚
- [ ] 文档版本号与代码版本同步

### 7.3 安全验收

- [ ] staging 环境完成 1 次 PII 密钥轮换演练
- [ ] CI 中 pip-audit + safety + trivy 三重扫描全部通过
- [ ] Secrets SOP 文档经安全工程师评审
- [ ] 无 HIGH/CRITICAL 漏洞未处理

### 7.4 性能验收

- [ ] PDF 生成任务端到端延迟 < 60s (单报告)
- [ ] ObservabilityExporter 事件驱动延迟 < 5s
- [ ] CI 扫描时间不超过现有构建时间的 50%

---

## 8. 交付物清单

### 8.1 代码交付物

| 编号 | 文件 | 类型 | 关联任务 |
|------|------|------|---------|
| 1 | `.github/workflows/dependency-scan.yml` | 新增 | SEC-A |
| 2 | `.github/workflows/container-scan.yml` | 新增 | SEC-B |
| 3 | `backend/requirements-dev.txt` | 修改 (添加 pip-audit/safety) | SEC-A |
| 4 | `backend/.trivyignore` | 新增 | SEC-B |
| 5 | `backend/scripts/rotate_pii_keys.py` | 新增 | SEC-C |
| 6 | `backend/app/tasks/pdf_report.py` | 新增 | P-D |
| 7 | `backend/app/api/v1/reports.py` | 修改 (新增 3 个端点) | P-D |
| 8 | `backend/app/core/event_bus.py` | 新增 | R-C |
| 9 | `backend/app/services/observability_exporter.py` | 修改 (订阅事件) | R-C |
| 10 | `backend/app/services/alert_lifecycle_service.py` | 修改 (发布事件) | R-C |
| 11 | `backend/app/main.py` | 修改 (lifespan 启动 EventBus) | R-C |

### 8.2 测试交付物

| 编号 | 文件 | 测试数 |
|------|------|--------|
| 1 | `backend/tests/test_pdf_celery.py` | 6 |
| 2 | `backend/tests/test_event_bus.py` | 6 |
| 3 | `backend/tests/test_rotate_pii_keys.py` | 5 |

### 8.3 文档交付物

| 编号 | 文件 | 关联任务 |
|------|------|---------|
| 1 | `docs/security/dependency-scan.md` | SEC-A |
| 2 | `docs/security/known-vulnerabilities.md` | SEC-A |
| 3 | `docs/ops/README.md` | SEC-C |
| 4 | `docs/ops/secrets-rotation-sop.md` | SEC-C |
| 5 | `docs/architecture/c4-context.md` | M-A |
| 6 | `docs/architecture/c4-container.md` | M-A |
| 7 | `docs/architecture/c4-component.md` | M-A |
| 8 | `docs/architecture/c4-code.md` | M-A |
| 9 | `docs/architecture/adr/ADR-001-fastapi-selection.md` | M-A |
| 10 | `docs/architecture/adr/ADR-002-sqlalchemy-async.md` | M-A |
| 11 | `docs/architecture/adr/ADR-003-celery-selection.md` | M-A |
| 12 | `docs/architecture/adr/ADR-004-vue3-composition-api.md` | M-A |
| 13 | `docs/architecture/adr/ADR-005-element-plus.md` | M-A |
| 14 | `docs/architecture/adr/ADR-006-asyncio-to-thread.md` | M-A |
| 15 | `docs/architecture/adr/ADR-007-fernet-pii-encryption.md` | M-A |
| 16 | `docs/architecture/adr/ADR-008-health-check-probes.md` | M-A |
| 17 | `docs/architecture/adr/ADR-009-redis-pubsub-websocket.md` | M-A |
| 18 | `docs/architecture/adr/ADR-010-alembic-migration.md` | M-A |
| 19 | `docs/architecture/adr/ADR-011-event-bus.md` | R-C |

### 8.4 报告交付物

| 编号 | 文件 | 日期 |
|------|------|------|
| 1 | `docs/SYSTEM_OPTIMIZATION_FOLLOWUP_SUMMARY.md` | 2026-08-14 (M5 里程碑) |
| 2 | staging 演练截图归档 | 2026-07-17 (M1 里程碑) |
| 3 | CI 扫描基线报告 | 2026-07-24 (M2 里程碑) |

---

## 9. 变更日志 (Changelog)

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|---------|------|
| 2026-07-03 | v1.0 | 初始版本, 基于 2026-07-03 检验报告生成 | 系统优化团队 |

---

## 10. 附录

### 10.1 相关文档

- [SYSTEM_OPTIMIZATION_PLAN.md](./SYSTEM_OPTIMIZATION_PLAN.md) - 原始优化计划
- [SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md](./SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md) - P4 阶段总结报告
- [architecture.md](./architecture.md) - 现有架构文档
- [I18N_MIGRATION_PROGRESS.md](./I18N_MIGRATION_PROGRESS.md) - i18n 迁移进度

### 10.2 检验报告摘要 (2026-07-03)

| 状态 | 数量 | 占比 | 策略编号 |
|---|---|---|---|
| ✅ 已完成 | 10 | 62.5% | P-A, P-B, P-C, R-A, R-B, S-A, S-B, S-C, M-B, M-C |
| ⚠️ 部分完成 | 4 | 25.0% | P-D, R-C, SEC-B, M-A |
| ❌ 未完成 | 2 | 12.5% | SEC-A, SEC-C |

### 10.3 术语表

| 术语 | 全称 | 说明 |
|------|------|------|
| SCA | Software Composition Analysis | 软件组合分析, 扫描第三方依赖漏洞 |
| SOP | Standard Operating Procedure | 标准操作程序 |
| ADR | Architecture Decision Record | 架构决策记录 |
| C4 | C4 Model | 软件架构可视化模型 (Context/Container/Component/Code) |
| PII | Personally Identifiable Information | 个人身份信息 |
| Fernet | - | Python cryptography 库的对称加密方案 |
| trivy | - | 开源容器镜像漏洞扫描器 |
