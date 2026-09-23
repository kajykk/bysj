# Learnings v1.12 - Coverage & Browser Quality Sprint

> **迭代**: v1.12-coverage-browser-quality-sprint  
> **日期**: 2026-04-30  
> **状态**: Draft  
> **用途**: 总结 v1.11.2 CI 质量门禁经验，并指导 v1.12 执行

---

## 1. v1.11.2 成功经验

| 经验 | 效果 | v1.12 延续方式 |
|---|---|---|
| 先建立 CI 可运行环境 | 解除环境限制，真实验证 build/audit/bandit/pytest | v1.12 继续以真实命令为准 |
| npm audit 实跑 | 确认 high 漏洞真正清零 | 保持为 P0 门禁 |
| 前端 build 实跑 | 确认 PWA 产物未回归 | 每次 PWA/性能改动后必跑 |
| bandit 实跑 | 确认 High=0，Medium/Low 可登记治理 | v1.12 做 Medium 风险治理 |
| 失败测试分类 | 将 214 failed 拆成 ENV/DATA/IMPORT/LOGIC 等可处理类别 | v1.12 优先修 DATA/IMPORT/LOGIC |
| 小 release gate | 快速定位 3 个真实失败并修复 | v1.12 保持 release gate，扩展覆盖率 |
| NumPy 2.x 兼容修复 | `np.trapz` 问题被发现并修复 | 后续关注依赖版本兼容 |

---

## 2. v1.11.2 教训

| 问题 | 原因 | v1.12 改进 |
|---|---|---|
| 覆盖率仍为 28% | 测试集中在部分 ML 模块，services 覆盖不足 | v1.12 设定 40% 可达目标 |
| Lighthouse 仍未执行 | 环境缺少 Chrome | v1.12 必须配置 Chrome/Chromium |
| PWA 只验证产物 | 缺少浏览器行为验证 | v1.12 验证 SW registered/activated/offline |
| Chunk 仍 >500KB | charts/vendor 依赖较重 | v1.12 做 chunk 分析和首屏验证 |
| bandit Medium 仍有 9 个 | ML 模型加载安全需评估 | v1.12 制定 revision/weights_only 策略 |
| 目标口径曾不一致 | 40%/60% 覆盖率目标混用 | v1.12 明确目标为 40%，60% 延后 |

---

## 3. v1.12 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 覆盖率目标 | 40% | 从 28% 到 40% 更现实，60% 后续专项 |
| 浏览器验证 | Chrome/Chromium 必须配置 | Lighthouse 和 PWA 行为必须真实验证 |
| Lighthouse 范围 | `/login` P0，其余页面 P1 | 先保证能跑，再扩大页面范围 |
| Chunk 优化 | 首屏优先 | charts 大但不进入首屏即可降低用户影响 |
| bandit Medium | 治理或风险接受 | 不强制一次清零，避免影响 ML 功能 |
| CI 门禁 | build/audit/bandit/pytest/lighthouse 分 job | 便于定位失败 |
| PWA 验证 | 浏览器行为优先 | 产物存在不等于 SW 行为正确 |

---

## 4. v1.12 风险预判

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 覆盖率提升耗时超预期 | 中 | 中 | 优先 ML/services 高收益模块 |
| Lighthouse 分数不达标 | 中 | 中 | 不立即阻塞，形成修复清单 |
| Chrome 环境仍不可用 | 低 | 高 | 使用 GitHub Actions 或 Playwright Chromium |
| PWA 浏览器验证发现缓存问题 | 中 | 中 | 清理旧 cache，检查 Workbox 策略 |
| Chunk 优化破坏懒加载 | 中 | 中 | 每次优化后跑 build 和页面验证 |
| bandit Medium 修复影响模型加载 | 中 | 中 | 先评估，再局部修复或豁免 |
| 覆盖率测试引入 flaky | 中 | 中 | 避免真实外部依赖，使用 fixture/mock |

---

## 5. 执行原则

1. 所有结论必须以真实命令或明确环境限制为依据。
2. 覆盖率优先提升到 40%，不追求一次到 60%。
3. 新增测试优先覆盖真实风险路径，不写低价值覆盖率测试。
4. Lighthouse 至少跑通 `/login`，其余页面可分阶段。
5. PWA 必须做浏览器行为验证，不能只看构建产物。
6. npm audit 和 bandit High 不允许回归。
7. bandit Medium 可以治理或风险接受，但必须有记录。
8. Chunk 优化以首屏体验为优先，不机械追求所有 chunk <300KB。
9. 最终质量门禁报告必须引用实际命令输出。

---

## 6. v1.13 延续方向

v1.12 完成后，v1.13 可考虑：

| 方向 | 内容 |
|---|---|
| 覆盖率 | 40% → 60% |
| E2E | Playwright 关键路径回归 |
| PWA | 离线写入、IndexedDB、后台同步 |
| CSP | Production Enforcement |
| 性能 | 深度 chunk 拆分和懒加载优化 |
| 安全 | bandit Medium 全量清理 |
| 监控 | Web Vitals 持久化和趋势分析 |

---

## 7. 成功标准

v1.12 成功的标志：

```text
coverage >= 40%
Lighthouse can run
PWA browser behavior verified
npm audit = 0 vulnerabilities
bandit High = 0
frontend build passes
QUALITY_GATE_V1.12.md archived
FINAL_REPORT_V1.12.md archived
```
