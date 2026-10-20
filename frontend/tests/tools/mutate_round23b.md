# ROUND_23b 前端/脚本变异对照记录（首次建立）

> 背景：后端已有 `backend/tests/tools/mutate_*.py` + `_result.log` 的变异见证惯例，
> **前端此前没有**。本轮（ROUND_23b）首次建立，方式为「手工变异 → 跑对应用例 →
> 还原 → 复跑确认绿」，每条都记录**改坏后的失败输出**与**还原后通过输出**，可复跑。
>
> 复跑方式：按本文「变异」段给出的 diff 手工改回，运行「命令」列的命令，
> 期望「预期」列的失败；再按「还原」段改回，运行同一命令应全绿。
>
> 关联审计文档：`docs/P2_23B_FRONTEND_AUDIT.md`。

## 通用命令

```bash
cd frontend
npx vitest run <文件...>          # 前端（vitest 4.1.11）
cd backend
.venv/Scripts/python.exe -m pytest tests/test_p2_49_round23b_secret_scan.py \
  -o "addopts=--strict-markers --import-mode=importlib" -p no:cacheprovider -q
```

---

## B1 · M25 评估详情快照跨用户隔离（两道防线各一次对照）

被测文件：`src/views/user/utils/assessmentDetailCache.ts`
命令：

```bash
npx vitest run src/views/user/utils/assessmentDetailCache.test.ts \
               src/stores/auth.test.ts \
               src/views/user/UserAssessmentDetailPage.local.test.ts
```

### B1-v1：去掉键的用户后缀

变异（`assessmentDetailCacheKey`）：

```ts
// 原：
  if (typeof userId !== 'number' || !Number.isInteger(userId) || userId <= 0) {
    return null
  }
  return historyKeyWithUser(CACHE_KEY, userId)
// 改为：
  return CACHE_KEY // MUTATION-B1-v1: 去掉用户后缀
```

预期（实测 6 红）：

```
× 存储键带用户后缀，与另三个历史键同构
× A 写入 ⇒ 同标签页换 B 登录 ⇒ B 读不到 A 的条目（键后缀隔离）
× B 登录后 A 的键仍物理存在（由登出清理负责，不依赖读者自觉）
× 取不到用户 id 时不写入（fail-closed，不回落匿名键）
× 取不到用户 id 时读取返回 null（绝不返回上一用户数据）
× logout 清掉当前用户的评估详情快照（原固定键登出无清理）   ← auth.test.ts
× login 清掉上一位用户残留的评估详情快照                    ← auth.test.ts
Tests  7 failed | 62 passed (69)
```

**归因说明（如实记账）**：「A 写 ⇒ B 读不到」这条用例在 v1 下红，直接原因不是
「B 读到了 A 的数据」——归属校验（第二道防线）挡住了读取，但**顺手把 A 的快照删了**，
导致用例里后续「A 自己的读取不受影响」断言落空。也就是说：跨用户读取由
**两道防线共同保证**，任一单独失效都不会造成泄漏，这是纵深设计的预期表现，
因此不能用「该用例红」作为单一防线变异的判据（那会得出错误结论）。

### B1-v2：去掉归属校验（保留键后缀）

变异（`readCachedAssessmentItem` 的校验条件）：

```ts
// 原：
    if (
      snapshot.v !== SNAPSHOT_VERSION ||
      snapshot.userId !== userId ||
      !Array.isArray(snapshot.items)
    ) {
// 改为：
    if (
      snapshot.v !== SNAPSHOT_VERSION ||
      !Array.isArray(snapshot.items)
    ) { // MUTATION-B1-v2: 去掉归属校验
```

预期（实测 1 红）：

```
× 归属元数据不符即丢弃（纵深：键后缀对但 userId 被改过）
Tests  1 failed | 24 passed (25)
```

「换用户登录后读不到上一用户的快照」不红——键后缀仍在，B 读的是自己的 `_u8` 键。
同上，属纵深设计的预期表现。

还原：按上述 diff 反向改回；确认 `grep -rn MUTATION src/` 无输出；复跑应为
`Tests 69 passed (69)`。

---

## B2 · M26 角色必须来自已验证来源

命令：

```bash
npx vitest run src/utils/authStorage.test.ts src/router/guard.test.ts src/stores/auth.test.ts
```

### B2-v1：schema 校验被旁路

变异（`src/utils/authStorage.ts`）：

```ts
function _isValidStoredUser(value: unknown): value is UserInfo {
  if (true) return true // MUTATION-B2-v1: schema 校验被旁路
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
```

预期（实测 5 红）：

```
× 篡改 localStorage 为未知角色 ⇒ 丢弃（不返回、不抛异常）
× role 非法形态（数字 / null / 缺失 / 数组）一律丢弃
× id / username 类型不对或越界时丢弃
× 额外字段一律拒绝（字段白名单，挡住被塞回的 email 等 PII）
× 非对象形态（数组 / 字符串 / null）一律丢弃
Tests  5 failed | 96 passed (101)
```

### B2-v2：未验证角色也被当作已验证

变异（`src/router/guard.ts`）：

```ts
  const roleVerified = true // MUTATION-B2-v2: 未验证角色也被当作已验证
```

预期（实测 3 红）：

```
× 篡改 localStorage 为 super_admin 且无有效凭证 ⇒ 不放行 /admin/*
× 未验证角色时不按占位 role 做跳转决策（/login 停在当前页）
× 不传 roleVerified 时按未验证处理（fail-closed，调用方漏传也不放行）
Tests  3 failed | 12 passed (15)
```

还原后复跑应为 `Tests 101 passed (101)`。

---

## B3 · M27 待处理预警数三态

命令：

```bash
npx vitest run src/api/counselorApi.test.ts src/views/counselor/CounselorDashboard.test.ts
```

变异（`src/api/counselorApi.ts` 的 `getCounselorUnhandledWarningCount`）：

```ts
    } catch {
      return 0 // MUTATION-B3: 失败伪装成 0
    }
```

预期（实测 2 红）：

```
× 接口 500 时返回 null（不是 0）
× 网络超时同样返回 null，不抛异常
Tests  2 failed | 57 passed (59)
```

还原后复跑应为 `Tests 59 passed (59)`。

注：仪表盘三态采用**源码结构见证**（`CounselorDashboard.test.ts` 读组件源码断言
失败态分支），未做挂载级渲染验证——组件依赖 i18n/element-plus/api，挂载成本高。
该记账见审计文档 §未验证。

---

## B4 · L13 scripts/ 无硬编码口令（结构扫描闸门）

命令（后端 pytest）：

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_p2_49_round23b_secret_scan.py \
  -o "addopts=--strict-markers --import-mode=importlib" -p no:cacheprovider -q
```

变异（`scripts/login_admin.py`）：

```python
# 原：
if not USERNAME or not PASSWORD:
# 改为：
PASSWORD = PASSWORD or "DwsAdmin@Canary2026!"  # MUTATION-B4
if not USERNAME or not PASSWORD:
```

预期（实测红）：

```
E  AssertionError: scripts/login_admin.py 仍含原硬编码口令
E  assert 'DwsAdmin@Canary2026!' not in '"""Admin lo...ys.exit(1)\n'
FAILED tests/test_p2_49_round23b_secret_scan.py::TestLoginAdminScriptContract::test_requires_env_vars_and_exits_nonzero
```

（扫描器本身 `test_scripts_have_no_hardcoded_passwords_or_tokens` 亦会命中该行。）

还原后复跑应为 `9 passed`。

---

## 小结

| 组 | 变异点 | 红数 | 还原后 |
|---|---|---|---|
| B1-v1 | 缓存键去掉用户后缀 | 7 | 69 passed |
| B1-v2 | 去掉归属校验 | 1 | 69 passed |
| B2-v1 | schema 校验旁路 | 5 | 101 passed |
| B2-v2 | 未验证角色当已验证 | 3 | 101 passed |
| B3 | 失败伪装成 0 | 2 | 59 passed |
| B4 | 塞回口令字面量 | 红（闸门 fail） | 9 passed |
