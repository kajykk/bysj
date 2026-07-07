# ADR-007: PII 加密使用 Fernet 对称加密而非非对称加密

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统存储大量个人身份信息 (PII): 用户邮箱 (email)、手机号 (phone)、紧急联系人姓名与电话 (emergency_name / emergency_phone)。这些字段在 `User` 模型中以明文形式存在时, 一旦数据库备份泄露或开发环境数据库被误共享, 即构成 GDPR / 《个人信息保护法》项下的数据泄露事件。

需求约束:
1. **字段级加密**: 仅加密敏感字段, 非敏感字段 (user_id, role, created_at) 保持明文以便查询与索引;
2. **可逆加密**: 系统需在「危机干预」流程中向咨询师展示真实联系方式, 不可使用单向 hash;
3. **密钥轮换**: 安全规范要求支持定期轮换 (季度) 与应急轮换 (疑似泄露), 轮换期间旧密文可解密、新写入用新密钥;
4. **开发/生产一致**: 开发环境 (SQLite) 与生产环境 (PostgreSQL) 行为一致, 避免环境差异导致的 bug;
5. **性能可控**: 加解密在请求路径上执行, 单次操作 < 1ms, 不能显著增加 API 延迟。

## 决策 (Decision)
采用 Python `cryptography.fernet.Fernet` 对称加密, 实现位于 `app/core/pii_crypto.py`。

具体设计:
- **算法**: Fernet = AES-128-CBC + HMAC-SHA256, 加密时同时生成 IV、密文与 HMAC, 解密时先验 HMAC 再解密, 防止密文篡改 (authenticated encryption);
- **密钥来源**: 主密钥通过环境变量 `PII_ENCRYPTION_KEY` 注入 (44 字节 base64 Fernet 密钥); 生产环境强制校验, 开发环境未配置时自动生成临时密钥 (重启失效, 仅本地用);
- **字段级密钥派生**: 不直接使用主密钥, 而是通过 HKDF-SHA256 + 字段特定 salt 派生每个字段的 Fernet 密钥 (`_FIELD_SALTS` 字典), 避免「同一密钥加密多字段」带来的关联风险, 也防止跨字段重放;
- **密文标识**: 所有密文以 `enc:v1:` 前缀存储, 便于运行时检测是否已加密、便于平滑迁移与批量重加密;
- **多代密钥回退**: 通过 `PII_PREVIOUS_KEYS` (逗号分隔) 配置历史密钥, 解密时先尝试当前密钥, 失败后依次回退到旧密钥 (`_get_previous_fernets`), 保证轮换期间旧数据可读;
- **轮换 SOP**: `scripts/rotate_pii_keys.py` 实现在线轮换: 读取旧密钥 → 解密 → 用新密钥重新加密 → 批量写回, 配合 `docs/ops/secrets-rotation-sop.md` 操作手册;
- **使用约束** (代码 docstring 明确):
  - 加密字段不能用作唯一约束 (密文非确定性);
  - 不能用 `LIKE` / `WHERE` 查询加密字段, 需先全量取出再内存过滤;
  - 跨密钥迁移数据时必须保留旧密钥直到全部重加密完成。

## 替代方案 (Alternatives Considered)
1. **RSA / AES-GCM 非对称加密** — 用公钥加密、私钥解密。优点是公钥可分发到日志/导出服务; 缺点: RSA 性能差 (单次加密 ~1ms vs Fernet ~0.05ms), 密文膨胀大 (RSA-2048 加密手机号需 256 字节), 密钥管理 (私钥保护、证书链) 远比对称密钥复杂, 而本系统加解密在同一进程内完成, 无需分离密钥角色。
2. **应用层 hash + 查表** — 对 email/phone 做 SHA-256 hash 存储, 需要原文时查反向映射表。不可逆, 无法满足「危机干预时展示真实联系方式」需求, 且彩虹表攻击风险高。
3. **数据库透明加密 (TDE)** — PostgreSQL 不原生支持字段级 TDE, 仅支持整库加密 (通过 LUKS/ext4-crypt); 开发环境 SQLite 完全不支持。无法满足「字段级」与「多环境一致」需求。
4. **仅依赖 DB 权限不加密** — 通过 PostgreSQL GRANT/REVOKE 限制访问。问题: 备份文件、DBA、误执行的 `pg_dump` 仍可读明文, 不满足 GDPR 字段级保护要求, 也无法应对开发环境数据库泄露场景。

## 后果 (Consequences)
- **正面**:
  - 性能优秀: Fernet 单次加解密 < 0.1ms, 对 API 延迟无可观测影响;
  - 字段级加密粒度, 非敏感字段保持明文, 不影响常规查询与索引;
  - HMAC 认证加密, 防篡改, 满足合规审计要求;
  - HKDF 字段级密钥派生 + 多代密钥回退, 密钥轮换 SOP 完善, 可在线轮换不停服;
  - `enc:v1:` 前缀方案支持渐进式迁移与未加密数据检测。
- **负面**:
  - 密钥泄露风险: 主密钥一旦泄露, 所有 PII 可解密。通过环境变量管理 (不入库、不进 Git) + `docs/ops/secrets-rotation-sop.md` SOP + 定期轮换缓解;
  - 加密字段无法 SQL `WHERE` 过滤, 需在应用层解密后内存匹配, 大数据量查询时需分页或维护 hash 索引列 (本项目通过 `email_hash` 列辅助精确查找);
  - 多代密钥回退增加解密路径复杂度, 单次解密可能尝试多次。
- **中性**:
  - 开发环境自动生成的临时密钥每次重启都变, 导致开发环境 PII 数据每次重启后无法解密 — 这是预期行为 (强制开发者使用测试数据, 不存真实 PII), 但需在 onboarding 文档中说明;
  - 加密字段类型在 DDL 中需为 `TEXT`/`VARCHAR` 而非定长类型, 因密文长度不固定。

## 关联 (Related)
- 实现: `backend/app/core/pii_crypto.py` (Fernet + HKDF 字段级派生 + 多代密钥回退)
- 配置: `backend/app/core/config.py` (`pii_encryption_key` / `pii_previous_keys` 字段, 第 277 行)
- 轮换脚本: `backend/scripts/rotate_pii_keys.py`
- SOP: `docs/ops/secrets-rotation-sop.md`
- 测试: `backend/tests/test_gdpr_pii.py`, `backend/tests/test_pii_key_rotation.py`
- 迁移: `backend/alembic/versions/h9d4e5f6a7b8_add_pii_encryption_email_hash.py` (引入加密字段 + email_hash 索引列)
- 相关 ADR: ADR-010 (Alembic 迁移 — PII 加密字段通过版本化迁移引入)
