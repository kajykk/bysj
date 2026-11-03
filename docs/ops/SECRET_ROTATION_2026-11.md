# 密钥轮换清单（2026-11，阶段 0 配套）

> **适用范围**：`e:\code\bysj` 及外部密钥目录 `E:\secrets\bysj\`。
> **本文不含任何明文密钥值**；只列「哪把、在哪用过、轮换后失效什么、如何验证」。
> **本文所有轮换动作只能由用户执行**，代码侧只负责「密钥不再随目录流通」。

## 0. 迁移与回滚（已完成部分）

| 项 | 结论 |
|---|---|
| 密钥存放位置 | `E:\secrets\bysj\`（`.env`、`.env.production`、`backend.env`、`.env.probe`） |
| 仓库内保留 | 仅 `.env.example`（无真实值） |
| compose 读取方式 | `docker compose --env-file "$ENV_FILE" up -d` |
| 本地后端 | `$env:ENV_FILE="E:\secrets\bysj\backend.env"` 后启动 |
| 回滚（仅迁移失败时） | 把文件复制回原路径（`.env`/`.env.production` → 仓库根，`backend.env` → `backend/.env`），`docker compose up` 恢复旧行为；回滚不恢复安全性，需随后重新迁出 |

## 1. 必须轮换的凭据

> 轮换顺序建议：先 `PII_ENCRYPTION_KEY`（需配套重加密脚本）→ 再 `JWT_*` → 再基础设施
> （PG/Redis）→ 最后监控（Grafana/Alertmanager/Metrics）。每次只动一把，验证后再下一把。

### 1.1 `JWT_SECRET_KEY`（HS256 签名密钥）

- **在哪用过**：`backend/.env`、`.env`、`.env.production`；后端 `Settings.jwt_secret_key`；compose 4 个服务的 `JWT_SECRET_KEY` 注入。
- **轮换后失效**：全部已签发的 access token 立即失效（用户需重新登录/刷新）；refresh token 同样失效。
- **验证命令**：

  ```powershell
  # 旧 token 应返回 401（替换 $OLD_TOKEN）
  curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer $env:OLD_TOKEN" http://127.0.0.1:8001/api/v1/users/me
  ```

  期望 `401`；随后用新登录获取的 token 调同一接口期望 `200`。

### 1.2 `PII_ENCRYPTION_KEY`（Fernet，加密 email/phone/emergency_contact）

- **在哪用过**：`.env`、`.env.production`、`backend.env`；`app/core/pii_crypto.py`；数据库列密文。
- **轮换后失效**：**历史密文无法解密**。必须先把旧 key 移入 `PII_PREVIOUS_KEYS`，执行一次全量重加密（读取→用新 key 写回），确认无解密失败后再摘除旧 key。
- **验证命令**：（在仓库内、只读方式核对，不打印明文）

  ```powershell
  # 统计仍无法用新 key 解密的行数，期望 0
  python backend/scripts/pii_reencrypt.py --dry-run
  ```

  若无该脚本，则用应用只读接口抽样：管理员查询用户详情，`email`/`phone` 应正常显示且日志无 `pii_decrypt_failed`。

### 1.3 `POSTGRES_PASSWORD`（及 `DATABASE_URL`）

- **在哪用过**：`.env`/`.env.production` 的 `DATABASE_URL`；compose `postgres` 初始化与 `backend`/`alembic_migrate`/celery 连接串。
- **轮换后失效**：旧连接立即断开；正在运行的容器需重建（`docker compose up -d`）。注意 `.env` 与 `.env.production` 存在**两套不同口令**，轮换时只保留一套并删除另一套。
- **验证命令**：

  ```powershell
  docker compose --env-file $env:ENV_FILE exec postgres psql -U depress_admin -d depression_system -c "select 1;"
  ```

  旧口令应认证失败；新口令返回 `1`。

### 1.4 `REDIS_PASSWORD`

- **在哪用过**：`.env`/`.env.production` 的 `REDIS_URL`；compose `redis` 启动参数与各服务的 `REDIS_URL`。
- **轮换后失效**：jti 黑名单、限流计数、缓存、Celery broker 全部重连；短暂登录态抖动可接受。
- **验证命令**：

  ```powershell
  docker compose --env-file $env:ENV_FILE exec redis redis-cli -a $env:NEW_REDIS_PASSWORD ping
  ```

  期望 `PONG`；旧口令期望 `WRONGPASS`。

### 1.5 `ALERTMANAGER_WEBHOOK_SECRET`

- **在哪用过**：`.env`/`.env.production`；compose 中 Alertmanager → backend `/api/v1/alerts/webhook` 的 `Authorization: Bearer`。
- **轮换后失效**：旧 Alertmanager 配置的告警投递被 401 拒绝（需同步更新 `infra/alertmanager/alertmanager.yml` 的 `http_config.authorization.credentials_file`）。
- **验证命令**：

  ```powershell
  # 用旧 secret 直接打 webhook，期望 401；用新 secret 期望 202/200
  curl.exe -s -o NUL -w "%{http_code}`n" -X POST -H "Authorization: Bearer $env:OLD_ALERT_SECRET" -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8001/api/v1/alerts/webhook
  ```

### 1.6 `METRICS_ACCESS_TOKEN`

- **在哪用过**：`.env`/`.env.production`；Prometheus 抓取 `/api/v1/metrics` 的 Bearer。
- **轮换后失效**：Prometheus 抓取 401，Grafana 面板出现断点，直到更新 `infra/prometheus/prometheus.yml`（密码文件 `infra/prometheus/token`，已在 `.gitignore` 中）。
- **验证命令**：

  ```powershell
  curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer $env:OLD_METRICS_TOKEN" http://127.0.0.1:8001/api/v1/metrics   # 期望 401
  curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer $env:NEW_METRICS_TOKEN" http://127.0.0.1:8001/api/v1/metrics   # 期望 200
  ```

### 1.7 `GRAFANA_ADMIN_PASSWORD` 与 `GRAFANA_SERVICE_TOKEN`（`glsa_…`）

- **在哪用过**：`.env`/`.env.production`；compose `grafana` 服务的管理员口令；`GRAFANA_SERVICE_TOKEN` 还用于兑换 `/api/v1/*/grafana/*` 的虚拟管理员身份（`app/core/deps.py`）。
- **轮换后失效**：Grafana 管理员登录需重置；旧 SA token 调用后端 observability/grafana 接口立即 401。SA token 权限过大，建议轮换时**降权为只读 observability**。
- **验证命令**：

  ```powershell
  curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer $env:OLD_GRAFANA_SA" http://127.0.0.1:8001/api/v1/observability/summary   # 期望 401
  ```

### 1.8 `SMTP_PASSWORD`

- **在哪用过**：`.env`/`.env.production`；`app/monitoring/notifier.py` 发信。
- **轮换后失效**：告警邮件发送失败（会进重试队列），不影响主业务。
- **验证命令**：触发一次测试告警邮件（管理端“通知测试”），日志应无 `SMTPAuthenticationError`。

### 1.9 `DEEPSEEK_API_KEY`（`sk-…`，已确认无代码引用）

- **在哪用过**：原 `backend/.env`（现 `E:\secrets\bysj\backend.env`）；全仓代码与文档检索**零引用**。
- **轮换后失效**：无影响（本就未使用）。建议**直接吊销**而非轮换。
- **验证命令**：`git grep -n "DEEPSEEK_API_KEY"` 应无命中（排除 `.env.example`）。

### 1.10 E2E 测试账号口令（开发库）

- **在哪用过**：`E2E_USER_PASSWORD` 等，Playwright 测试脚本登录开发环境。
- **轮换后失效**：E2E 需同步更新外部密钥文件；不影响生产。
- **验证命令**：`npm run test:e2e:doctor` 后跑一条登录用例。

### 1.11 TLS 证书/私钥（`infra/nginx/certs/`）

- **在哪用过**：nginx 443 监听。
- **轮换后失效**：浏览器需信任新证书；旧证书吊销。
- **验证命令**：

  ```powershell
  openssl s_client -connect 127.0.0.1:443 -servername localhost </dev/null 2>$null | Select-String "Verify return code"
  ```

  期望 `Verify return code: 0 (ok)`。

## 2. 本次已闭合的风险（代码侧）

| 风险 | 原状态 | 现状态 |
|---|---|---|
| 生产密钥随目录流通 | `.env`/`.env.production`/`backend/.env` 三个文件在仓库内 | 已迁至 `E:\secrets\bysj\`；仓库仅 `.env.example`；启动脚本强制 `ENV_FILE` |
| 占位/示例口令被当成生产配置 | `change_me_smtp_password` 等可静默启动 | 生产启动期 **fail-fast**（配置校验），开发仅 warn |
| 模型 revision 浮动 | 生产 `.env` 为 `main` | 生产必须是 40 位 commit hash，否则拒绝启动 |
| 生产 CORS 含明文源 | `http://localhost:3000` | 生产含 `http://` 即拒绝启动 |
| JWT 可跨服务重放 | 未配置 issuer/audience | 生产必须配置 `JWT_ISSUER` / `JWT_AUDIENCE` |
| 模型制品随镜像/仓库分发 | `COPY models/` 打包 22 个 `.pkl` 与训练 CSV | 镜像仅带 `MODEL_REGISTRY.md`；生产缺制品启动失败，开发 `/health` 暴露 `degraded` |
| 死模型条目被误当可用 | 8 个条目指向不存在文件 | `resolvable=False` + 文档标注；D6 明确 DNN 不交付 |
| 上传 MIME 校验 fail-open | libmagic 缺失时跳过校验仍成功 | 改为 `503` 拒绝（fail-closed） |
| `/health` 公网泄露依赖状态 | nginx 代理完整 `/health` 且无限流 | 仅代理 `/health/live`，30r/m 限流 |
| CI 只扫 git 内容 | 未追踪的 `.env` 不可见 | 新增工作区扫描 job（gitleaks `dir` + env 文件断言） |
| 镜像版本与仓库不一致 | 无校验 | `GIT_SHA` 写入 label/`APP_GIT_SHA`，启动日志打印，CI 断言 |
| 后端/celery 镜像 tag 分裂 | `3.1.0` vs `v1.41` | 统一 `APP_VERSION` |
| Prometheus 可热重载 | `--web.enable-lifecycle` | 已移除 |

## 3. 仍依赖用户执行的事项

1. **执行本清单 §1 的全部轮换**（代码无法代做）；轮换前先备份数据库。
   - 2026-11-03：§1.1 / §1.2 / §1.3 / §1.4 / §1.7 已执行；§1.8 只替换了口令，
     **host/user/from 仍是 `example.com` 占位，无法实发验证**；详见 §4.1、§4.5。
2. 在 `E:\secrets\bysj\.env` 中补齐生产必需项，否则容器会**按设计启动失败**：
   - [x] `JWT_ISSUER`、`JWT_AUDIENCE`（任意稳定的服务标识，需与签发端一致）
   - [x] `MODEL_BERT_REVISION`：40 位 commit hash（替换当前的 `main`）
   - [x] `CORS_ALLOWED_ORIGINS`：仅保留 `https://` 域名（移除 `http://localhost:3000`）
   - [ ] `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_USE_TLS` /
     `SMTP_FROM_EMAIL`：**唯一剩余的凭证类阻塞项**。当前 host=`smtp.example.com`、
     user/from=`*@example.com`，均为占位；密码是随机占位值，不是有效授权码。
     未配置真实 SMTP 前，密码重置邮件与告警邮件全链路不可用（代码会走日志回退/重试，
     不会崩溃，但不会真正投递）
3. 把模型制品上传到外部制品库并生成 `.sha256`；生产 `MODEL_DIR` 指向该目录（compose 只读卷）。
4. 部署时显式传入 `GIT_SHA`（如 `$env:GIT_SHA=$(git rev-parse HEAD)`），使镜像 label 与
   启动日志中的 `git_sha` 可核对；未传时为 `unknown`（仅警告不阻断）。
5. 目录权限收紧：`E:\secrets\bysj` 仅当前账户与 Administrators。
6. 在 CI/仓库设置中把新增的 `workspace-scan` job 设为 required。
7. 轮换完成后，用 §1 各条的验证命令逐项确认，并把结果记入运维台账。

## 4. 2026-11-03 执行记录（§1.1 / §1.2 / §1.3 / §1.4 / §1.7）

> 记录只含「动作 + 长度/布尔 + 验证读数」，不含任何明文密钥。
> 执行文件：`E:\secrets\bysj\.env`（compose 实际读取）与 `E:\secrets\bysj\.env.production`
> （历史遗留的第二套口令，已与本轮轮换值统一，消除双口令分叉）。
> 备份目录：`E:\secrets\bysj\backups\20261103-140816\`（含 4 个旧 env 副本、
> `db_before_pii_rotation.sql`、旧 access token 文本、临时 compose override）。
> **备份内含旧密钥，观察期结束后必须销毁。**

### 4.1 已轮换凭据

| 项 | 动作 | 验证读数 |
|---|---|---|
| `JWT_SECRET_KEY` | 重新生成（64 字符，含大小写/数字/符号） | 旧 token → `401`；轮换后签发的新 token → `200`，claims 含 `iss=bysj-backend`、`aud=bysj-api` |
| `PII_ENCRYPTION_KEY` | 重新生成 Fernet 密钥（44 字符）；旧密钥先移入 `PII_PREVIOUS_KEYS` | dry-run 1 行 → `--apply` 1 行，失败 0，`email_hash` 盲索引同步 1 条；清空 previous 后 `current_key_decrypts=True` |
| `POSTGRES_PASSWORD` / `DATABASE_URL` | 重新生成（43 字符），`.env` 与 `.env.production` 同一取值 | 容器网络内（host=`postgres`）旧口令认证失败、新口令成功。**本机回环因 `pg_hba` trust 不能作为证据** |
| `REDIS_PASSWORD` / `REDIS_URL` | 重新生成（43 字符） | `dws-redis` 健康检查（带新口令 `PING`）通过，backend/celery 正常连接 |
| `GRAFANA_ADMIN_PASSWORD` | 重新生成（32 字符） | Grafana 登录 `200` |
| `GRAFANA_SA_TOKEN` / `GRAFANA_SERVICE_TOKEN` | 创建新 SA `dws-observability-20261103`（Viewer）并签发新 token（`glsa_` 46 字符），两个变量同值 | 旧 SA token 调后端 → `401`；新 SA token → `200`；数据源 `secureJsonFields.Authorization=true` |
| `SMTP_PASSWORD` | 把占位值 `change_me_smtp_password` 换成随机 32 字符 | **未验证，且不构成可用配置**：`SMTP_HOST=smtp.example.com`、`SMTP_USER`/`SMTP_FROM_EMAIL=*@example.com` 仍是占位，没有真实授权码，未做实发邮件测试；这是**唯一还缺的凭证类阻塞项** |

PII 轮换命令（在 backend 容器内执行，与线上代码一致）：

```bash
python scripts/rotate_pii_keys.py            # dry-run
python scripts/rotate_pii_keys.py --apply    # 实际重加密
```

### 4.2 同步补齐的生产配置项

| 变量 | 取值 | 校验点 |
|---|---|---|
| `JWT_ISSUER` | `bysj-backend` | 生产启动校验非空；签发/校验均使用 |
| `JWT_AUDIENCE` | `bysj-api` | 同上 |
| `MODEL_BERT_REVISION` | `2a995a880017c60e4683869e817130d8af548486`（`hfl/chinese-bert-wwm-ext`） | 40 位十六进制，通过生产校验；来源为 HF 镜像 API 返回的 `sha` |
| `PASSWORD_RESET_BASE_URL` | `https://localhost/reset-password` | 生产要求 `https://` |
| `CORS_ALLOWED_ORIGINS` | `https://localhost` | 生产拒绝任何 `http://` 源 |

### 4.3 整体健康读数

- `docker compose ps`：8 个常驻 `dws-*` 服务 `healthy`；`dws-migrate` `Exited (0)`。
- `https://localhost/health` → `200`。
- 旧 JWT 访问受保护接口 → `401`；轮换后新 token → `200`。

### 4.4 遗留问题与注意事项

1. **（2026-11-03 已修复）Grafana JSON 数据源 → 后端 401**：
   根因是 provisioning 把 SA Token 写进了 `secureJsonData.Authorization`。Grafana 数据源代理
   只把 `jsonData.httpHeaderNameN` + `secureJsonData.httpHeaderValueN` 拼进出站请求；任意键名
   只有 backend 插件能通过 `DecryptedSecureJSONData` 读取，而 `simpod-json-datasource`
   是纯前端插件（`plugin.json: "backend": false`），拿不到 `secureJsonData`。
   已改为 `httpHeaderName1: Authorization` / `httpHeaderValue1: Bearer ${GRAFANA_SA_TOKEN}`，
   并给数据源 URL 补尾斜杠（后端路由是 `/`，缺斜杠会 307 且代理不跟随）。
   实测 `GET /api/datasources/proxy/uid/<uid>/` → `200`，插件按条件恢复 `enabled=true`。
   2026-11-03 在 Grafana UI 点过 **Save & test**，返回 `Successfully queried the data source`。
2. **（已解决）后端 8001 端口占用**：宿主机残留的 `uvicorn`（PID 27308，2026-11-01 启动）
   已停止；compose 恢复 `127.0.0.1:8001:8000` 回环映射，未使用 `ports: !reset []` override。
   当前 `docker port dws-backend` = `127.0.0.1:8001`，无需再选“不发布后端端口”路径。
3. **`backend.env` / `.env.probe` 未轮换**：二者 JWT/PII 密钥与旧生产值不同，属开发/探针配置，
   不在本次生产轮换范围；如要统一，需另行评估。
4. **观察期**：`PII_PREVIOUS_KEYS` 已清空并通过解密验证；建议保留数据库备份至下一个观察周期
   （T+7），确认无 `pii_decrypt_failed` 后再销毁备份目录中的旧密钥副本。

### 4.5 轮换带出的告警/监控链路修复（2026-11-03）

轮换后报警链路有两个真实的“静默失败”，已修复并实测：

| 项 | 现象 | 根因 | 处理与读数 |
|---|---|---|---|
| Grafana → backend 告警 webhook | 403 | `init-alerting.sh` 只在 provisioning 卷首次初始化时渲染占位符；旧卷里仍是**轮换前**的 webhook secret（文件 mtime 2026-10-23） | 显式删除渲染产物并重启 grafana，脚本重新渲染（日志 `[init-alerting] rendered ...`）；渲染后 secret 哈希前缀与 backend 一致；webhook 实测 `200` |
| `.env` 与 `.env.production` 分叉 | 同一变量两套值 | 首次轮换只改了 `.env.production`，`.env` 里 `ALERTMANAGER_WEBHOOK_SECRET`、`METRICS_ACCESS_TOKEN` 仍是旧值 | 以 `.env.production` 为准同步 `.env`；Grafana/backend/Prometheus 三处取值一致 |
| Prometheus 抓取 backend | target `down` / `403` | `infra/prometheus/token` 是**第三套历史 token**（04dd8cb...），与 backend 运行时值不一致 | 用 backend 实际 token 重写 token 文件并重启 prometheus；target 恢复 `up` |
| 告警总览面板 | 15 个可见面板显示 `No data` | 不是链路故障：`alert_archives`、`alert_silences`、`drift_alerts` 三张表均为 0 行 | 面板查询与数据源代理均正常；等真实告警产生后即有数据 |

另发现一个未修复的配置不一致：Grafana `root_url=https://localhost/grafana`，但 nginx
没有 `/grafana` 反代（该路径返回 Vue SPA）。当前 Grafana 只能经
`http://127.0.0.1:3002/grafana` 访问；若要并入 `https://localhost/grafana`，需补 nginx
反代并保证子路径重写。已记入 `UPGRADE_2026-11-03.md` §8。
