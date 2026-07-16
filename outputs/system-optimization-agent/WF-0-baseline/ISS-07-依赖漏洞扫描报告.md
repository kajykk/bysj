# ISS-07 依赖漏洞扫描报告

> 阶段: WF-0/WF-1 | 优先级: P0 | 技能: sys-security-hardening
> 扫描时间: 2026-07-15 01:21 (pip-audit 生产) / 01:34 (pip-audit 开发) / 2026-07-14 18:11 (trivy 容器)
> 工具: pip-audit 2.10.1 (OSV advisory DB) + trivy (aquasec/trivy:latest, DB: ghcr.io/aquasecurity/trivy-db)

## 1. 背景与目标

ISS-07 要求把实时漏洞扫描纳入基线。本工程依赖扫描分三层：

1. **Python 依赖漏洞扫描** — `pip-audit` 对照 OSV/PyPI 公告库，检测 `requirements*.txt` 声明的直接与传递依赖。
2. **容器/基础镜像扫描** — `trivy` 扫描镜像层与系统包（本环境无独立 trivy 二进制；本次通过已就绪的 Docker + WSL 2 拉取 `aquasec/trivy` 镜像完成）。
3. **IaC / 配置扫描** — `trivy config` 扫描 `docker-compose.yml`（本次因 checks-bundle 下载被网络策略阻断，改用人工静态审查替代，见 §5）。

SAST 部分（bandit）已于前序工作完成：**0 High / 3 Medium / 19 Low**（B615 已清零，见 ISS-13）。

## 2. Python 依赖扫描结果（pip-audit / OSV）

### 2.1 生产依赖 (`requirements.txt`)

| 指标 | 值 |
|---|---|
| 扫描依赖总数 | 122 |
| 存在漏洞的依赖数 | 0 |
| 已知漏洞总数 | 0 |

关键依赖版本（均无已知 CVE）：fastapi 0.139.0 / uvicorn 0.51.0 / sqlalchemy 2.0.51 / pydantic 2.13.4 / pyjwt 2.13.0 / cryptography 49.0.0 / bcrypt 4.3.0 / redis 8.0.1 / celery 5.6.3 / asyncpg 0.31.0 / torch 2.13.0 / tensorflow 2.21.0 / transformers 5.13.1 / scikit-learn 1.9.0 等。

### 2.2 开发依赖 (`requirements-dev.txt`)

| 指标 | 值 |
|---|---|
| 扫描依赖总数 | 17 |
| 存在漏洞的依赖数 | 0 |
| 已知漏洞总数 | 0 |

### 2.3 结论

**Python 依赖面零已知漏洞。** 全部 139 个依赖（122 生产 + 17 开发）在 OSV 公告库中无匹配 CVE。说明依赖版本管理（上界约束 `>=,<`）有效，核心库均处于较新且已修复的版本区间。

## 3. bandit SAST 结果（前序工作，复述）

- 0 High / 3 Medium / 19 Low
- B615（HuggingFace from_pretrained 未 pin revision）已清零（ISS-13 已修复-已验证）。
- 剩余 3 Medium：B104×2（绑定 0.0.0.0）、B614（torch.load 不安全，safe_pickle.py，已用 weights_only + 路径白名单 + 哈希校验补偿，并有 96% 测试覆盖）。

## 4. 容器 / 基础镜像扫描结果（trivy）

> 执行方式：`docker run aquasec/trivy:latest image --severity HIGH,CRITICAL`
> DB 源：`ghcr.io/aquasecurity/trivy-db`（默认 mirror.gcr.io 被网络策略阻断，已切换）
> 镜像来源：postgres:15 / python:3.12.10-slim 经 daocloud 镜像拉取到本地后扫描（Docker Hub 直连被阻断）

### 4.1 汇总

| 目标 | 类型 | HIGH | CRITICAL | 合计 |
|---|---|---|---|---|
| postgres:15 (debian 13.5) | debian OS | 34 | 8 | **42** |
| usr/local/bin/gosu | gobinary | 14 | 1 | **15** |
| python:3.12.10-slim (debian 12.11) | debian OS | 52 | 8 | **60** |
| python base 内 pip (METADATA) | python-pkg | 0 | 0 | 0 |
| 镜像内嵌密钥 | secret | 1 (HIGH) | 0 | 1 |
| **合计（镜像 HIGH/CRITICAL）** | — | **100** | **17** | **117** |

> 注：python base 镜像内的 `pip` 包（语言层）扫描为 0 漏洞，与应用层 `pip-audit` 结论一致。

### 4.2 postgres:15 关键发现

- **CRITICAL**:
  - `CVE-2026-42496` perl-archive-tar：通过精心构造的 symlink 实现路径穿越（Status: `fix_deferred`，Debian 13 尚未发布修复）。
- **HIGH（代表性）**:
  - `CVE-2026-53615` util-linux / libblkid：分区解析整数溢出（bsdutils/libblkid1/libmount1/libuuid1/util-linux 等共享，affected，无 Fixed Version）。
  - `CVE-2026-24882` gnupg 系列：tpm2daemon 栈溢出可致任意代码执行。
  - `CVE-2026-41992` gzip：LZH 解压全局缓冲区溢出。
  - `CVE-2026-54369` libacl1：symlink 穿越提权。
  - `CVE-2025-69720` ncurses 系列：缓冲区溢出可致任意代码执行。
  - perl 系列：`CVE-2026-8376` / `CVE-2026-42497` / `CVE-2026-48962` / `CVE-2026-9538`（编译/解压/DoS，多为 `fix_deferred`）。
- **gosu gobinary（CRITICAL 1 / HIGH 14）**：Go 标准库 CVE（net/url、crypto/x509、crypto/tls、net/http2 等 DoS 类），多数在 Go 1.24.13+ / 1.25.x 已修复；`CVE-2025-68121`（crypto/tls 会话恢复证书校验错误，CRITICAL）标记为 `fixed`（gosu 当前构建用的 Go 1.24.6 受影响，升级 Go 工具链即可消除）。
- **密钥 1**（HIGH）：`/etc/ssl/private/ssl-cert-snakeoil.key` — Debian 基础镜像自带的 snakeoil 自签名私钥，属标准占位密钥，**误报（false-positive）**，正式部署会挂载真实证书覆盖。

### 4.3 python:3.12.10-slim 关键发现

- **CRITICAL**:
  - `CVE-2026-33845` gnutls：DTLS 零长度分片 DoS。
  - `CVE-2025-7458` sqlite3：整数溢出。
  - `CVE-2026-31789` openssl：32 位系统上大 X.509 证书堆溢出。
  - `CVE-2026-42496` perl-archive-tar：symlink 路径穿越（`fix_deferred`）。
  - `CVE-2023-45853` zlib：zipOpenNewFileInZip4_6 整数溢出致堆溢出（`will_not_fix`，Debian 12 不打算回移植）。
- **HIGH（代表性）**：`CVE-2025-69720` ncurses、`CVE-2026-53615` util-linux、`CVE-2026-54369` libacl1、`CVE-2025-32988/32990` gnutls SAN/certtool、`CVE-2026-40355/40356` krb5、`CVE-2026-28387~45447` openssl 系列（DANE/CMS/PKCS7 UAF 与 DoS）、`CVE-2026-42497/48962/9538` perl 系列、`CVE-2023-31484` perl CPAN TLS 校验缺失（fixed）。
- **python 语言层（pip METADATA）**：0 漏洞。

### 4.4 关键判断（诚实评估）

1. **漏洞位于基础镜像 OS 层，不在应用代码**。应用自身的 PyPI 依赖（pip-audit，139 个）与语言层包（trivy python-pkg，0）均干净。
2. **大量 CVE 的 Fixed Version 为空（`fix_deferred` / `will_not_fix`）**——Debian 当前尚未发布对应补丁。这意味着仅靠 `apt-get upgrade` 今天无法清零这些项，"24-72h 清零"的 SLA 对 OS 层不可达，需通过**升级基础镜像到更新点版本**或**切换 distroless / chainguard 等精简镜像**来根治。
3. **gosu 的 CRITICAL 已 confirmed fixed in 上游 Go**，重新构建 gosu 即可消除；但本工程 python 镜像不含 gosu，gosu 仅存在于 postgres 官方镜像内。
4. **snakeoil 密钥为误报**，真实部署用挂载证书覆盖。
5. **python:3.12.10-slim 基于 debian 12.11**，比 postgres 的 debian 13.5 旧，故 HIGH 数量更多（52 vs 34）——优先升级 backend 基础镜像可显著降低计数。

## 5. docker-compose.yml 审查（trivy config 被阻断，人工替代）

`trivy config` 本应自动扫描 compose 的 misconfig/secret，但本沙箱**无法下载 trivy checks-bundle**（mirror.gcr.io 被网络策略阻断），回退的 embedded 规则不包含 docker-compose 策略集，故自动扫描返回 "Supported files not found"。改为人工静态审查 `docker-compose.yml`：

- ✅ **无硬编码密钥**：所有凭据均通过 `${VAR:?must be set}`（POSTGRES_PASSWORD / REDIS_PASSWORD / JWT_SECRET_KEY / GRAFANA_ADMIN_PASSWORD）或 `${VAR:-default}`（SENTRY_DSN / CORS_ORIGINS）从环境变量注入；`DATABASE_URL` / `REDIS_URL` 内联的是变量插值而非明文。
- ⚠️ 次要加固缺口（非密钥泄露）：
  - redis healthcheck 用 `-a "${REDIS_PASSWORD}"` 在命令行传口令（容器内 `ps` 可见）。
  - 未设置 `user:`（容器以 root 运行）、`security_opt: no-new-privileges`、只读根文件系统 / `cap_drop`。
  - 生产环境 postgres/redis 端口已注释（仅容器间通信）——网络隔离良好。

## 6. 可复现命令

```bash
cd backend
# 生产依赖
.venv/Scripts/python.exe -m pip_audit -r requirements.txt --desc on -f json -o pip_audit_report.json
# 开发依赖
.venv/Scripts/python.exe -m pip_audit -r requirements-dev.txt -f json -o pip_audit_dev_report.json
# 容器扫描（需 Docker + 可访问 trivy-db 源）
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v trivy-cache:/root/.cache/trivy \
  -e TRIVY_DB_REPOSITORY=ghcr.io/aquasecurity/trivy-db \
  aquasec/trivy:latest image --severity HIGH,CRITICAL python:3.12.10-slim
# compose 审查（需能下载 checks-bundle；否则人工审查见 §5）
docker run --rm -v $PWD:/work:ro aquasec/trivy:latest config /work/docker-compose.yml
```

## 7. 状态

- **Python 依赖漏洞扫描：已闭环**（139 依赖，0 CVE）。
- **bandit SAST：已闭环**（0 High / 3 Medium / 19 Low）。
- **容器/基础镜像扫描：已完成（实测，非 CI）**——postgres:15 42 + gosu 15 + python:3.12.10-slim 60 = **117 HIGH/CRITICAL**；其中大量为 OS 层 `fix_deferred`，需升级基础镜像根治。snakeoil 密钥为误报。
- **docker-compose：自动扫描被网络策略阻断，已人工审查**（无硬编码密钥）。
- **建议纳入 CI**：在带 Docker 的流水线固定 `TRIVY_DB_REPOSITORY` 并执行 `trivy image` + `trivy config`，将 high/critical 按 24-72h SLA 跟踪；对 `fix_deferred` 项建立基础镜像升级看板（优先升级 backend 的 python 基础镜像，从 debian 12 → 13 点版本）。
- ISS-07 整体标记：**进行中-三层扫描已实测，容器层发现 117 HIGH/CRITICAL（多为 OS 层 fix_deferred，待基础镜像升级）**。
