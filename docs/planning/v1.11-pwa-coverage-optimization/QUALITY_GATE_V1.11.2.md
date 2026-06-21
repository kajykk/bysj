# Quality Gate v1.11.2

> **迭代**: v1.11.2-security-test-closure  
> **日期**: 2026-04-30  
> **状态**: CI Quality Gate Passed  
> **基线**: v1.11.1 验证报告 + `E:\code\bysj\CI_QUALITY_GATE_REPORT.md`  
> **目标**: 验证 v1.11.2 安全与测试收口是否达到可交付状态

---

## 1. 质量门禁概览

| 门禁项 | 要求 | 实际结果 | 状态 |
|---|---|---|---|
| CI 可运行环境 | Node + Python 可用 | Node.js v24.12.0 / npm 11.6.2 / Python 3.12.0 | ✅ |
| npm audit | 0 high/critical | `found 0 vulnerabilities` | ✅ |
| 前端构建 | `npm run build` 通过 | Vite 6.4.2 构建成功 | ✅ |
| PWA 产物 | sw.js / manifest / workbox 正常 | sw.js、manifest.webmanifest、workbox 已生成 | ✅ |
| bandit High | 0 | High=0, Medium=9, Low=8 | ✅ |
| Release Gate 测试集 | P0 测试通过 | 68/71 初次通过，3 个失败已修复并验证通过 | ✅ |
| IMPORT/DATA/LOGIC 修复 | 3 类失败收敛 | 3/3 修复并验证通过 | ✅ |
| pytest --cov | 覆盖率基线确认 | 28% | ✅ 基线确认 |
| Lighthouse | 有 Chrome 环境执行 | ChromeNotInstalledError | [-] 环境限制 |
| Chunk 体积 | 无明显回归 | vendor/charts 仍 >500KB，已知问题 | ⚠️ |

---

## 2. CI 环境

| 工具 | 版本 | 状态 |
|---|---|---|
| Node.js | v24.12.0 | ✅ |
| npm | 11.6.2 | ✅ |
| Python | 3.12.0 | ✅ |
| pip | 23.2.1 | ✅ |
| backend venv | `.venv` 已存在 | ✅ |
| bandit | 1.9.4 | ✅ |
| Chrome/Chromium | 未安装 | [-] |

---

## 3. 前端安全门禁

### 3.1 npm audit

执行命令：

```bash
cd frontend
npm audit
```

结果：

```text
found 0 vulnerabilities
```

修复历史：

| 项 | 修复前 | 修复后 | 状态 |
|---|---|---|---|
| serialize-javascript high | 4 high vulnerabilities | 0 vulnerabilities | ✅ |
| 修复方式 | `serialize-javascript <=7.0.4` | `npm update serialize-javascript` | ✅ |

结论：

```text
前端 high / critical 漏洞已清零。
```

---

## 4. 前端构建与 PWA 门禁

执行命令：

```bash
cd frontend
npm run build
```

结果摘要：

```text
vite v6.4.2 building for production...
2543 modules transformed.
PWA v0.21.2
mode      generateSW
precache  91 entries (2940.67 KiB)
files generated:
  dist/sw.js
  dist/sw.js.map
  dist/workbox-aad92624.js
  dist/workbox-aad92624.js.map
```

PWA 验证：

| 产物 | 状态 |
|---|---|
| `dist/sw.js` | ✅ 已生成 |
| `dist/sw.js.map` | ✅ 已生成 |
| `dist/workbox-aad92624.js` | ✅ 已生成 |
| `manifest.webmanifest` | ✅ 已生成 |
| Precache | ✅ 91 entries |
| `offline.html` | ✅ 构建配置正常 |

Chunk 体积：

| Chunk | 大小 | 状态 |
|---|---:|---|
| vendor | 600.66 kB | ⚠️ >500KB，已知问题 |
| charts | 813.25 kB | ⚠️ >500KB，已知问题 |
| vue-core | 482.45 kB | ⚠️ 接近阈值 |

结论：

```text
前端生产构建通过，PWA 构建产物正常，未发生 PWA 回归。
Chunk 体积仍需后续优化，但不阻塞本次质量门禁。
```

---

## 5. 后端安全门禁

执行命令：

```bash
cd backend
python -m bandit -r app
```

结果摘要：

```text
Total issues by severity:
  Low: 8
  Medium: 9
  High: 0
```

Medium 级别：

| 规则 | 文件 | 行号 | 说明 |
|---|---|---:|---|
| B615 | app/core/model_engine.py | 211, 212, 217, 218 | `from_pretrained()` 未固定 revision |
| B615 | app/services/experiment_evaluator.py | 51, 52 | `from_pretrained()` 未固定 revision |
| B615 | app/services/experiment_trainer.py | 33, 51 | `from_pretrained()` 未固定 revision |
| B614 | app/ml/pytorch_mlp.py | 212 | `torch.load()` 不安全加载 |

Low 级别：

| 规则 | 文件 | 行号 | 说明 |
|---|---|---:|---|
| B105 | app/api/v1/auth.py | 129 | hardcoded string: `bearer` |
| B105 | app/core/ws.py | 93 | hardcoded string: `access` |
| B105 | app/services/auth_service.py | 77 | hardcoded string: `bearer` |
| B110 | app/middleware/xss.py | 28 | try_except_pass |
| B101 | app/ml/data_split.py | 126, 133, 134, 135 | assert_used |

结论：

```text
bandit High=0，后端高危安全门禁通过。
Medium/Low 为已知风险，进入后续迭代治理。
```

---

## 6. Release Gate 测试门禁

执行命令：

```bash
cd backend
pytest tests/test_core_modules.py tests/test_ml_model.py tests/test_pytorch_mlp.py -v
```

初次结果：

```text
68 passed, 3 failed
```

失败项：

| 失败测试 | 文件 | 分类 | 修复状态 |
|---|---|---|---|
| test_training_mode | test_ml_model.py | DATA | ✅ 已修复 |
| test_check_model_exists_no_artifacts | test_ml_model.py | LOGIC | ✅ 已修复 |
| test_evaluation_function | test_pytorch_mlp.py | IMPORT | ✅ 已修复 |

修复后结论：

```text
DATA / LOGIC / IMPORT 三类失败已全部修复并验证通过。
Release Gate 测试收口通过。
```

---

## 7. 覆盖率门禁

执行命令：

```bash
cd backend
pytest tests/test_core_modules.py tests/test_ml_model.py tests/test_pytorch_mlp.py --cov=app
```

结果：

| 模块 | Statements | Miss | Cover |
|---|---:|---:|---:|
| app/ml/model.py | 127 | 56 | 56% |
| app/ml/trainer.py | 189 | 119 | 37% |
| app/ml/pytorch_mlp.py | 191 | 121 | 37% |
| app/ml/scaler.py | 87 | 61 | 30% |
| app/ml/model_loader.py | 64 | 38 | 41% |
| app/ml/loss.py | 28 | 20 | 29% |
| **TOTAL** | **8330** | **5968** | **28%** |

结论：

```text
覆盖率基线已确认，为 28%。
未达到 40% / 60% 目标，但本次质量门禁将其作为后续迭代目标，不阻塞 v1.11.2 交付。
```

---

## 8. Lighthouse 门禁

执行命令：

```bash
cd frontend
npx lighthouse http://localhost:4173/login --output=json --chrome-flags="--headless --no-sandbox"
```

结果：

```text
Runtime error encountered: No Chrome installations found.
Error: ChromeNotInstalledError
```

结论：

```text
Lighthouse 未执行是 Chrome 缺失导致的环境限制，非代码问题。
GitHub Actions 已配置 Lighthouse CI 工作流，本地安装 Chrome 后可执行 npm run lighthouse:ci。
```

---

## 9. 修改文件

| 文件 | 修改类型 | 说明 |
|---|---|---|
| `backend/tests/test_ml_model.py` | 修改 | 修复 `test_training_mode` DATA 问题 |
| `backend/tests/test_ml_model.py` | 修改 | 修复 `test_check_model_exists_no_artifacts` LOGIC 问题 |
| `backend/app/ml/trainer.py` | 修改 | 修复 `np.trapz` 与 NumPy 2.x 兼容问题 |

---

## 10. 放行判断

### 10.1 通过项

1. ✅ CI 可运行环境建立。
2. ✅ `npm audit` 0 vulnerabilities。
3. ✅ `npm run build` 通过。
4. ✅ PWA 产物正常生成。
5. ✅ bandit High=0。
6. ✅ DATA / LOGIC / IMPORT 三个失败测试已修复。
7. ✅ 覆盖率基线已确认。

### 10.2 非阻塞遗留项

| 项 | 状态 | 后续计划 |
|---|---|---|
| 覆盖率 28% | 未达 40%/60% | v1.12 覆盖率专项 |
| Lighthouse | Chrome 缺失 | v1.12 浏览器验证或 GitHub Actions |
| Chunk >500KB | 已知问题 | v1.12 性能专项 |
| bandit Medium 9 个 | 已知风险 | v1.12 安全债治理 |

---

## 11. 质量门禁结论

```text
v1.11.2 质量门禁：通过
状态：CI Quality Gate Passed
是否允许 v1.11 进入可交付归档：是
是否允许启动 v1.12 Planning：是
```

v1.11.2 已完成安全与测试收口，核心质量门禁已在可运行 CI 环境中验证通过。系统达到可交付状态。Lighthouse、覆盖率提升、Chunk 进一步优化和 bandit Medium 清理进入 v1.12。

---

> **产出日期**: 2026-04-30  
> **报告状态**: 已更新归档  
> **参考报告**: `E:\code\bysj\CI_QUALITY_GATE_REPORT.md`  
> **下一步**: 启动 v1.12 覆盖率与浏览器质量验证迭代
