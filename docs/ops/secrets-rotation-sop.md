# Secrets 轮换标准操作程序 (SOP)

> **关联任务**: SEC-C Secrets 管理 SOP
> **创建日期**: 2026-07-03
> **基线文档**: [SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md](../SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md)
> **关联脚本**: [backend/scripts/rotate_pii_keys.py](../../backend/scripts/rotate_pii_keys.py)

---

## 1. 适用范围

本 SOP 适用于以下 4 类 Secrets 的生命周期管理:

| Secret 名称 | 用途 | 轮换周期 | 影响范围 | 配置位置 |
|------------|------|---------|---------|---------|
| `PII_ENCRYPTION_KEY` | PII 字段加密 (email/phone/emergency_contact) | 90 天 | User 表加密字段 + emergency_contacts 表 | `.env` |
| `JWT_SECRET_KEY` | JWT 签名 (access_token + refresh_token) | 90 天 | 所有已签发 token 失效, 用户需重新登录 | `.env` |
| `ALERTMANAGER_WEBHOOK_SECRET` | AlertManager Webhook 鉴权 | 60 天 | AlertManager + 后端 webhook 接收 | `.env` + `infra/alertmanager/alertmanager.yml` |
| `METRICS_ACCESS_TOKEN` | Prometheus `/metrics` 端点访问 | 60 天 | Prometheus scrape 配置 | `.env` + `infra/prometheus/prometheus.yml` |

---

## 2. 轮换前置条件

- [ ] 拥有 `.env` 文件读写权限
- [ ] 拥有数据库读权限 (PII 轮换需要, 用于重加密)
- [ ] 拥有 Kubernetes/docker-compose 重启权限
- [ ] 已通知相关团队 (至少提前 24 小时)
- [ ] 已创建数据库快照备份 (仅 PII 轮换需要)
- [ ] 已在 staging 环境完成 1 次演练并截图归档

---

## 3. PII_ENCRYPTION_KEY 轮换流程

> 关联脚本: [backend/scripts/rotate_pii_keys.py](../../backend/scripts/rotate_pii_keys.py)
> 支持零停机轮换 (通过 `PII_PREVIOUS_KEYS` 旧密钥回退解密)

### 3.1 影响分析

- 影响字段: `users.email`, `users.phone`, `emergency_contacts.name`, `emergency_contacts.phone`
- 影响索引: `users.email_hash` (盲索引, 需同步更新)
- 风险等级: 高 (错误配置会导致历史数据无法解密)
- 停机时间: 0 (零停机, 通过旧密钥回退)

### 3.2 准备阶段 (T-1 天)

1. **生成新密钥**:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   记录新密钥到密码管理器 (1Password / Bitwarden)。

2. **数据库快照备份**:
   ```bash
   # PostgreSQL
   docker exec dws-postgres pg_dump -U depress_admin depression_system > backup_$(date +%Y%m%d).sql

   # SQLite (开发环境)
   cp backend/depression_system.db backend/depression_system.db.bak.$(date +%Y%m%d)
   ```

3. **通知用户**: "将于明日 02:00 进行 PII 密钥轮换, 预计耗时 10 分钟, 期间服务不停机"

### 3.3 执行阶段 (T 日 02:00 低峰期)

#### 步骤 1: 修改 `.env` 配置

```bash
# 将当前 PII_ENCRYPTION_KEY 的值加入 PII_PREVIOUS_KEYS (逗号分隔, 支持多代回退)
# 然后将 PII_ENCRYPTION_KEY 替换为新密钥
PII_ENCRYPTION_KEY=<NEW_KEY>
PII_PREVIOUS_KEYS=<OLD_KEY_1>,<OLD_KEY_2>
```

**注意**:
- `PII_PREVIOUS_KEYS` 保留最近 3 代密钥, 超过的应清除
- 新旧密钥不能相同 (脚本 preflight_checks 会校验)

#### 步骤 2: 重启后端服务

```bash
docker-compose restart backend celery_worker celery_beat
```

重启后, `decrypt_field` 会自动回退到旧密钥解密旧密文, 服务正常可用。

#### 步骤 3: 演练模式验证 (dry-run)

```bash
cd backend
python scripts/rotate_pii_keys.py
```

输出示例:
```
========================================================================
PII 加密密钥轮换脚本 (P2-4)
模式: DRY-RUN (预演)
批大小: 100
当前密钥长度: 44 chars
旧密钥数量: 1
========================================================================

前置检查通过
------------------------------------------------------------------------

-> 处理 users.phone (field=phone)
  [DRY-RUN] users.phone: 将重加密 150 行 (跳过 50, 失败 0)

-> 处理 emergency_contacts.name (field=emergency_name)
  [DRY-RUN] emergency_contacts.name: 将重加密 120 行 (跳过 10, 失败 0)

-> 处理 emergency_contacts.phone (field=emergency_phone)
  [DRY-RUN] emergency_contacts.phone: 将重加密 120 行 (跳过 10, 失败 0)

-> 处理 users.email (field=email)
  [DRY-RUN] users.email: 将重加密 150 行 (含 email_hash 盲索引同步更新) (跳过 50, 失败 0)
```

#### 步骤 4: 实际执行轮换

```bash
python scripts/rotate_pii_keys.py --apply
```

可指定批大小 (默认 100, 大表建议 200~500):
```bash
python scripts/rotate_pii_keys.py --apply --batch-size 200
```

#### 步骤 5: 验证

```bash
# 1. 健康检查
curl http://localhost:8000/health/ready

# 2. 登录测试 (验证 JWT 不受影响)
curl -X POST http://localhost:8000/api/v1/auth/login -d '...'

# 3. PII 字段查询测试 (验证解密成功)
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/users/me
```

### 3.4 验证阶段 (T+0 ~ T+7 天)

- [ ] T+0: 健康检查通过 `/health/ready`
- [ ] T+0: 登录测试 (验证 JWT 不受影响)
- [ ] T+0: PII 字段查询测试 (验证解密成功, email/phone 可读)
- [ ] T+1: 监控 Sentry 无 `pii_decrypt_failed` 错误
- [ ] T+1: 监控应用日志无 `PiiCrypto` 相关异常
- [ ] T+7: 清空 `PII_PREVIOUS_KEYS`, 完成 1 个观察周期

### 3.5 回滚流程

若轮换后出现异常 (如部分字段无法解密):

1. **恢复 `.env.backup`**:
   ```bash
   cp .env.backup .env
   ```

2. **从数据库快照恢复**:
   ```bash
   # PostgreSQL
   docker exec -i dws-postgres psql -U depress_admin depression_system < backup_YYYYMMDD.sql

   # SQLite
   cp backend/depression_system.db.bak.YYYYMMDD backend/depression_system.db
   ```

3. **重启服务**:
   ```bash
   docker-compose restart backend celery_worker celery_beat
   ```

4. **验证回滚成功**: 重复 3.3 步骤 5 的验证

---

## 4. JWT_SECRET_KEY 轮换流程

### 4.1 影响

- 所有已签发的 access_token 和 refresh_token 立即失效
- 用户需重新登录
- refresh_token cookie 失效
- 影响范围: 全部已登录用户

### 4.2 执行步骤

1. **生成新密钥**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **更新 `.env`**:
   ```bash
   JWT_SECRET_KEY=<NEW_KEY>
   ```

3. **重启服务**:
   ```bash
   docker-compose restart backend celery_worker celery_beat
   ```

4. **通知用户重新登录**: 通过站内通知 / 邮件告知 "安全维护, 请重新登录"

### 4.3 验证

- [ ] 旧 token 返回 401 (Token invalid)
- [ ] 新登录可正常获取 token
- [ ] refresh_token 端点正常工作

---

## 5. ALERTMANAGER_WEBHOOK_SECRET 轮换流程

### 5.1 影响

- AlertManager 发送的 webhook 请求会被后端拒绝 (401)
- 影响范围: 告警通知链路 (不影响告警触发)

### 5.2 执行步骤

1. **生成新密钥**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **更新后端 `.env`**:
   ```bash
   ALERTMANAGER_WEBHOOK_SECRET=<NEW_KEY>
   ```

3. **更新 AlertManager 配置** `infra/alertmanager/alertmanager.yml`:
   ```yaml
   receivers:
     - name: backend-webhook
       webhook_configs:
         - url: http://backend:8000/api/v1/alerts/webhook
           http_config:
             authorization:
               credentials: <NEW_KEY>  # 与后端一致
   ```

4. **重启服务**:
   ```bash
   docker-compose restart backend alertmanager
   ```

### 5.3 验证

- [ ] AlertManager 触发测试告警, 后端收到 webhook (200 OK)
- [ ] 后端日志无 `401 Unauthorized` 错误

---

## 6. METRICS_ACCESS_TOKEN 轮换流程

### 6.1 影响

- Prometheus 抓取 `/metrics` 端点会失败 (401)
- 影响范围: 监控指标采集 (不影响业务功能)

### 6.2 执行步骤

1. **生成新密钥**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **更新后端 `.env`**:
   ```bash
   METRICS_ACCESS_TOKEN=<NEW_KEY>
   ```

3. **更新 Prometheus scrape 配置** `infra/prometheus/prometheus.yml`:
   ```yaml
   scrape_configs:
     - job_name: 'backend'
       bearer_token: <NEW_KEY>  # 与后端一致
       static_configs:
         - targets: ['backend:8000']
   ```

4. **重启服务**:
   ```bash
   docker-compose restart backend prometheus
   ```

### 6.3 验证

- [ ] Prometheus targets 页面显示 backend 为 UP
- [ ] Grafana 仪表盘数据正常刷新
- [ ] 后端 `/metrics` 端点返回 200

---

## 7. 应急联系

| 角色 | 姓名 | 联系方式 | 备注 |
|------|------|---------|------|
| 安全负责人 | _(待填写)_ | _(待填写)_ | Secrets 轮换审批 |
| 运维负责人 | _(待填写)_ | _(待填写)_ | 服务重启 / 回滚操作 |
| DBA | _(待填写)_ | _(待填写)_ | 数据库备份 / 恢复 |
| 后端开发 | _(待填写)_ | _(待填写)_ | 脚本异常排查 |

---

## 8. 轮换记录

> 每次轮换后在此记录, 用于审计

| Secret 名称 | 轮换日期 | 执行人 | 审批人 | 演练环境 | 验证结果 | 备注 |
|------------|---------|--------|--------|---------|---------|------|
| _(首次轮换后填充)_ | | | | | | |

---

## 9. 变更日志

| 日期 | 变更内容 | 作者 |
|------|---------|------|
| 2026-07-03 | 初始版本, 创建 4 类 Secrets 轮换 SOP | 系统优化团队 |
