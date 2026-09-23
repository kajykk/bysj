# v1.13-coverage-sprint-40to60 下一步建议

> **迭代名称**: v1.13-coverage-sprint-40to60
> **日期**: 2026-04-30

---

## 选项 A: 修复/验证 (推荐)

### A.1 推送代码触发 CI 验证
**操作**:
```bash
git add backend/tests/test_core_config.py backend/tests/test_core_deps.py .github/workflows/coverage.yml
git commit -m "test(v1.13): add core config and deps tests, raise coverage threshold to 60%"
git push origin develop
```

**预期结果**:
- GitHub Actions 自动运行 coverage.yml workflow
- 验证覆盖率是否达到 60%
- 如未达标，根据 CI 报告补充测试

### A.2 解决环境限制问题
**方向 1**: 在 WSL2 或 Docker 中运行测试
**方向 2**: 使用 GitHub Codespaces 或远程 Linux 环境
**方向 3**: 配置本地虚拟环境，排查 exit code -1073741510 根本原因

---

## 选项 B: 优化

### B.1 补充未覆盖代码路径
根据 CI 覆盖率报告，针对以下模块补充测试:
- `app/core/config.py` — 模块级 side-effect 代码 (JWT 启动检查、警告)
- `app/core/database.py` — 数据库连接和会话管理
- `app/core/middlewares.py` — 中间件逻辑
- `app/core/rate_limit.py` — 限流逻辑
- `app/api/v1/admin.py` — 管理后台 API (当前缺失 53/99)
- `app/api/v1/auth.py` — 认证 API (当前缺失 88/128)

### B.2 提升测试质量
- 为 async 测试添加更多边界条件
- 增加并发测试覆盖
- 补充性能基准测试

---

## 选项 C: 新迭代

### C.1 v1.14 候选方向
1. **覆盖率冲刺 60%→80%**: 针对未覆盖的 API 和 services 补充测试
2. **E2E 测试增强**: 使用 Playwright 补充端到端测试
3. **性能优化迭代**: 基于性能测试数据优化热点代码
4. **安全加固迭代**: 渗透测试、依赖漏洞扫描、安全头加固
5. **文档完善迭代**: API 文档、架构文档、部署文档

---

## 建议的下一步行动

1. **立即**: 推送代码到 GitHub，观察 CI 覆盖率结果
2. **根据 CI 结果**:
   - 如果 >= 60%: 完成迭代交付，进入用户验收
   - 如果 < 60%: 根据缺失覆盖补充测试，重新推送
3. **长期**: 解决本地 Windows 测试环境问题，确保开发-测试闭环

---

> **文档版本**: v1.0
> **生成日期**: 2026-04-30
