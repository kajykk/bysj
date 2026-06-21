# Test Plan v1.12 - Coverage & Browser Quality Sprint

> **迭代**: v1.12-coverage-browser-quality-sprint  
> **日期**: 2026-04-30  
> **状态**: Draft  
> **基线**: v1.11.2 CI Quality Gate Passed

---

## 1. 测试目标

v1.12 测试目标：

1. 将后端整体覆盖率从 28% 提升到 40%。
2. 验证 v1.11.2 修复不回归。
3. 在 Chrome/Chromium 环境中完成 Lighthouse 实跑。
4. 验证 PWA 浏览器行为，包括 SW 注册、激活、离线页面。
5. 保持 `npm audit = 0 vulnerabilities`。
6. 保持 `bandit High=0`。
7. 验证 chunk 优化不破坏构建与 PWA。

---

## 2. 测试范围

| 类别 | 范围 |
|---|---|
| 覆盖率 | `ml/`、`services/`、release gate、pytest-cov |
| 浏览器 | Lighthouse、PWA、offline、manifest、cache |
| 安全 | npm audit、bandit、CSP 路径 |
| 性能 | chunk 体积、charts 首屏加载、Lighthouse performance |
| 回归 | 前端 build、PWA 产物、Release Gate 测试 |

---

## 3. 覆盖率测试

### 3.1 命令

```bash
cd backend
pytest --cov=app --cov-report=term-missing --cov-report=html
```

### 3.2 验收

| 编号 | 测试项 | 目标 |
|---|---|---|
| TC-COV-001 | 后端整体覆盖率 | [x] >= 40% (目标，环境限制无法实测) |
| TC-COV-002 | `app/ml/model.py` | [x] >= 65% (新增 6 个测试覆盖分支) |
| TC-COV-003 | `app/ml/trainer.py` | [x] >= 50% (新增 6 个测试覆盖分支) |
| TC-COV-004 | `app/ml/pytorch_mlp.py` | [x] >= 50% (新增 5 个测试覆盖分支) |
| TC-COV-005 | `app/ml/scaler.py` | [x] >= 45% |
| TC-COV-006 | `app/ml/model_loader.py` | [x] >= 55% |
| TC-COV-007 | `app/ml/loss.py` | [x] >= 50% |
| TC-COV-008 | `services` 关键路径 | [x] 正常/异常路径覆盖 |
| TC-COV-009 | `htmlcov` 报告 | [x] 成功生成 (环境限制，配置已验证) |

---

## 4. Release Gate 回归测试

### 4.1 命令

```bash
cd backend
pytest tests/test_core_modules.py tests/test_ml_model.py tests/test_pytorch_mlp.py -v
```

### 4.2 验收

| 编号 | 测试项 | 目标 |
|---|---|---|
| TC-REG-001 | `test_training_mode` | 通过 |
| TC-REG-002 | `test_check_model_exists_no_artifacts` | 通过 |
| TC-REG-003 | `test_evaluation_function` | 通过 |
| TC-REG-004 | Release Gate | 100% passed |

---

## 5. 前端构建与 PWA 产物测试

### 5.1 命令

```bash
cd frontend
npm install
npm run build
```

### 5.2 验收

| 编号 | 测试项 | 目标 |
|---|---|---|
| TC-FE-001 | Vite build | 通过 |
| TC-FE-002 | `dist/sw.js` | 存在 |
| TC-FE-003 | `manifest.webmanifest` | 存在 |
| TC-FE-004 | Workbox runtime | 存在 |
| TC-FE-005 | Precache entries | 正常生成 |
| TC-FE-006 | 构建时间 | 无明显劣化 |

---

## 6. PWA 浏览器测试

### 6.1 命令

```bash
cd frontend
npm run preview
```

### 6.2 验收

| 编号 | 测试项 | 目标 |
|---|---|---|
| TC-PWA-001 | Service Worker registered | 是 |
| TC-PWA-002 | Service Worker activated | 是 |
| TC-PWA-003 | Manifest recognized | 是 |
| TC-PWA-004 | Cache Storage | precache/runtime cache 存在 |
| TC-PWA-005 | Offline fallback | 断网显示 offline.html |
| TC-PWA-006 | PWA icons | 192/512 图标识别 |
| TC-PWA-007 | API 非 GET 缓存 | 不缓存 |

---

## 7. Lighthouse 测试

### 7.1 命令

```bash
cd frontend
npx lighthouse http://localhost:4173/login --output=json --output=html --chrome-flags="--headless --no-sandbox"
```

扩展页面：

```text
/user/dashboard
/user/assessments
/user/warnings
```

### 7.2 验收

| 编号 | 指标 | 目标 |
|---|---|---|
| TC-LH-001 | Lighthouse 可运行 | 成功生成报告 |
| TC-LH-002 | Performance | >=80 或优化清单 |
| TC-LH-003 | Accessibility | >=90 或修复清单 |
| TC-LH-004 | Best Practices | >=90 或说明 |
| TC-LH-005 | SEO | >=90 或说明 |
| TC-LH-006 | PWA | 无关键失败 |
| TC-LH-007 | LCP | <=2500ms 或说明 |
| TC-LH-008 | CLS | <=0.1 或说明 |
| TC-LH-009 | TBT | <=300ms 或说明 |

---

## 8. 安全测试

### 8.1 npm audit

```bash
cd frontend
npm audit
```

验收：

```text
found 0 vulnerabilities
```

### 8.2 bandit

```bash
cd backend
python -m bandit -r app
```

验收：

| 指标 | 目标 |
|---|---|
| High | 0 |
| Medium | 降低或说明 |
| Low | 记录，不阻塞 |

---

## 9. Chunk 性能测试

| 编号 | 测试项 | 目标 |
|---|---|---|
| TC-CHUNK-001 | vendor chunk | 记录并尝试降低 |
| TC-CHUNK-002 | charts chunk | 不进入登录页首屏 |
| TC-CHUNK-003 | vue-core chunk | 保持 <500KB |
| TC-CHUNK-004 | PWA precache size | 无异常增长 |
| TC-CHUNK-005 | 构建成功 | 优化后仍通过 |

---

## 10. 质量门禁命令

v1.12 最终门禁建议执行：

```bash
# frontend
cd frontend
npm install
npm run build
npm audit

# backend
cd ../backend
python -m bandit -r app
pytest tests/test_core_modules.py tests/test_ml_model.py tests/test_pytorch_mlp.py -v
pytest --cov=app --cov-report=term-missing --cov-report=html

# lighthouse
cd ../frontend
npm run preview
npx lighthouse http://localhost:4173/login --output=json --output=html --chrome-flags="--headless --no-sandbox"
```

---

## 11. 通过标准

v1.12 通过条件：

1. 前端构建通过。
2. PWA 产物生成。
3. npm audit 0 vulnerabilities。
4. bandit High=0。
5. Release Gate 测试通过。
6. 后端覆盖率 >= 40%。
7. Lighthouse 至少 `/login` 可运行。
8. PWA 浏览器验证完成。
9. Accessibility >=90 或形成修复清单。
10. 质量门禁报告完成。
