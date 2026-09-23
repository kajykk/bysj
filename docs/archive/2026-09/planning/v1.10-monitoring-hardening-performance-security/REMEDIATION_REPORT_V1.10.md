# Remediation Report v1.10

> **迭代**: v1.10-monitoring-hardening-performance-security
> **日期**: 2026-04-29
> **状态**: 修复完成
> **修复人**: Ralph Agent

---

## 1. 修复概览

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| bandit High | 1 (MD5) | 0 |
| bandit Medium | 9 | 9 (未变更，均为 B615/B614) |
| bandit Low | 8 | 8 |
| npm audit moderate | 6 | 0 |
| npm audit high | 0 | 0 |

---

## 2. 修复详情

### 2.1 bandit High: MD5 弱哈希 (B324)

| 属性 | 内容 |
|------|------|
| **文件** | `backend/app/ml/canary_controller.py` |
| **行号** | 106 |
| **问题** | `hashlib.md5()` 用于 canary 用户分桶，存在碰撞风险 |
| **修复** | 替换为 `hashlib.sha256()`，分母同步调整为 `2 ** 256` |
| **验证** | bandit 重新扫描，High 降为 0 |

**代码变更**:
```python
# 修复前
hash_value = hashlib.md5(hash_input.encode()).hexdigest()
return int(hash_value, 16) / (2 ** 128)

# 修复后
hash_value = hashlib.sha256(hash_input.encode()).hexdigest()
return int(hash_value, 16) / (2 ** 256)
```

**影响分析**:
- canary 分桶结果会改变（因为哈希算法变了）
- 但这是可接受的：canary 本身就是概率性的，重新分桶不影响业务正确性
- 建议：如果生产环境已有 canary 用户，需观察分桶变化对实验数据的影响

---

### 2.2 npm audit: 6 moderate 漏洞

| 漏洞 | 包 | 修复方式 |
|------|-----|----------|
| GHSA-3p68-rc4w-qgx5 | axios | `npm audit fix` 自动升级 |
| GHSA-39q2-94rc-95cp | dompurify | `npm audit fix` 自动升级 |
| GHSA-67mh-4wv8-2f99 | esbuild | `npm install vite@6.2.6` + `npm audit fix` |
| GHSA-r4q5-vmmm-2653 | follow-redirects | `npm audit fix` 自动升级 |
| GHSA-qx2v-qp2m-jg93 | postcss | `npm audit fix` 自动升级 |

**关键变更**:
- `vite` 从 `^5.4.8` 升级到 `^6.2.6`
- 连带 `esbuild` 升级到安全版本
- 其余依赖通过 `npm audit fix` 自动补丁

**验证**:
```bash
$ npm audit
found 0 vulnerabilities
```

---

## 3. 剩余风险

### 3.1 bandit Medium (9 个)

| 规则 | 数量 | 说明 | 建议 |
|------|------|------|------|
| B615 | 8 | HuggingFace `from_pretrained` 未固定 revision | 低风险：模型路径为本地或受控仓库 |
| B614 | 1 | PyTorch `torch.load` 不安全 | 低风险：加载的是自训练模型文件 |

**决策**: 暂不修复。原因：
1. 这些均为 Medium 级别，非阻塞
2. B615 的模型来源为内部路径，非公共 Hub
3. B614 的模型文件为自训练产出，非外部输入
4. 修复需改动 ML 核心代码，风险收益比不高

### 3.2 bandit Low (8 个)

未在本次修复范围内，建议后续迭代处理。

---

## 4. 验证记录

### 4.1 bandit 扫描

```
Run started: 2026-04-29 09:52:05
Total issues (by severity):
    Undefined: 0
    Low: 8
    Medium: 9
    High: 0
```

### 4.2 npm audit

```
$ npm audit
found 0 vulnerabilities
```

### 4.3 pytest 回归

```
$ python -m pytest tests/test_core_health.py tests/test_core_modules.py tests/test_core_security.py -v
============================= 46 passed in 20.95s =============================

$ python -m pytest tests/api/test_auth_flow.py -v
======================= 20 passed, 3 warnings in 37.35s =======================
```

---

## 5. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/ml/canary_controller.py` | 修改 | MD5 -> SHA256 |
| `frontend/package.json` | 修改 | vite ^5.4.8 -> ^6.2.6 |
| `frontend/package-lock.json` | 修改 | 依赖树更新 |

---

## 6. 下一步建议

1. **CI 集成**: 将 `npm audit` 和 `bandit` 加入 CI pipeline，阻断 High/Critical 漏洞
2. **B615 清理**: 在 v1.11 中为 `from_pretrained` 添加 `revision` 参数
3. **B614 清理**: 使用 `torch.load(..., weights_only=True)`（PyTorch 2.0+）
4. **canary 观察**: 生产环境部署后观察 canary 分桶是否平稳过渡

---

> **产出日期**: 2026-04-29
> **报告状态**: 已验证，可归档
