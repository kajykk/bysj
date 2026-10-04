# 历史清除执行坑位清单（入库版）

> 用途：`reports/口令历史清除_runbook_2026-10-02.md` 因**天然含旧口令字面量**被
> `.gitignore:260` 的 `/reports/` 排除在版本控制之外，因此换机器/重建 clone 后取不到。
> 本文件是它的**无密文等价物**，可跨机复用；执行时仍以 `reports/` 下那份为准
> （它含真实旧值，务必只在本地留存）。
> 关联：`reports/历史清除_快照声明_2026-10-02.md`（含旧↔新 hash 对照表，同为本地留存）。

## 坑 1：secrets 文件必须无 BOM（2026-10-02 实际踩到）

用 PowerShell `Set-Content -Encoding UTF8` 写出的替换规则文件，**首行带 UTF-8 BOM**，
filter-repo 读到的第一条规则变成 `\ufeff<旧值>`，于是：

- 该值**未被替换**；
- 命令返回成功、其余几条规则都正常清零 → 极易误判为「filter-repo 失效」。

正确写法：`Set-Content -Encoding utf8NoBOM`（PS 7+）/ `-Encoding ASCII`，或用编辑器存为
「UTF-8 无 BOM」。**判定标准是逐值复扫，不是命令退出码。**

## 坑 2：执行前先 `git worktree list`（本机有真实案例）

本机存在 linked worktree `workbuddy/main-5df3a16f`，检出在改写**前**的提交
（旧 hash `d919706` → 改写后 `f03756b`），它仍持有旧历史对象。历史清除后：

- 此类 worktree **必须重建**（`worktree remove` + 重新 `add`），**不能沿用**；
- 若被 WorkBuddy 桌面端会话占用，先在 WorkBuddy 里关闭相关会话再清理，
  **不要直接删目录**（本项目沙箱内 git 危险操作已三次实锤摧毁对象库）。

```powershell
git -C <repo> worktree list     # 清除前必查
```

## 坑 3：commit-map 与快照声明的落点

| 产物 | 位置 | 处置 |
|---|---|---|
| 旧↔新 hash 映射表 | 备份 clone 内 `filter-repo/commit-map`（本机为 `E:\code\bysj-backup-20261002.git\filter-repo\commit-map`） | **不要删**，是唯一对照 |
| 快照声明 | `reports/历史清除_快照声明_2026-10-02.md`（本地留存，不入库） | 追加式记录，**不改写既有声明** |

## 坑 4：验证口径不能用 `git log -S` / `git log -- <path>`

两者都会**静默漏检 merge 提交**（pickaxe 跳过 merge diff；path-log 被 history
simplification 剪枝），本项目实测：一个含值 merge 提交的 diff 里明明 +1 行含口令，
`-S` 却不报；一个实际有 6 个提交含值的文件，path-log 只报 1 个。

**唯一可信口径**——对全部提交的 blob 直接扫描：

```bash
git grep -l "<旧值>" $(git rev-list --all)     # bash
git grep -l "<旧值>" (git rev-list --all)      # PowerShell（307 提交约 12KB，单次传参安全）
```

四个旧值（12/16/11 位 E2E 三值 + canary 值）**逐值各跑一次**，全空才算过。
（补充：黑名单文件 `seed.py` 与其测试是**有意的死值引用**，验收口径排除这两个文件。）
