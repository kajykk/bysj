#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P2 第十一轮回退对照实验驱动。

纪律：每个闸门一条变异记录 —— 临时把修复/机制改坏 → 闸门**必须变红** →
恢复 → **必须变绿**。只跑"改完还绿"等于没验（第九轮 4 个变异里 1 个抓出假闸门）。

坑位加固（历轮实锤）：
- Windows subprocess 一律 `encoding="utf-8"`（默认 GBK 会把 vitest 失败标记 `×`
  解码成乱码 → failed 集合恒空 → 前端实验"假通过"，第六轮踩过）。
- 变异一律 read → replace → write，**绝不 write_text(片段)**（第八轮：整个文件被
  覆盖成一行 → 模块其余符号未定义 → 崩在 import 而不是断言红，被误判成实验无效）。
- anchor 必须当场校验，缺失直接抛错而不是记成 INVALID。
- 驱动自检：变异轮解析不出 failed 用例名 → 判 INVALID，不当 PASS。
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
REPO = BACKEND.parent
LOG = pathlib.Path(__file__).resolve().parent / "rollback_p2_11_result.log"

PY = str(BACKEND / ".venv/Scripts/python.exe")
VITEST = str(FRONTEND / "node_modules/.bin/vitest.cmd")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(cmd: list[str], cwd: pathlib.Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def be_test(node: str) -> tuple[int, str]:
    return run([PY, "-m", "pytest", node, "-o",
                "addopts=--strict-markers --import-mode=importlib",
                "-p", "no:cacheprovider", "-q", "--no-header"], BACKEND)


def fe_test(node: str) -> tuple[int, str]:
    return run([VITEST, "run", node], FRONTEND)


def py_failed(out: str) -> list[str]:
    return re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)


def fe_failed(out: str) -> list[str]:
    out = ANSI.sub("", out)
    names = re.findall(r"^\s*[×✗] (.+?)(?:\s+\d+(?:\.\d+)?m?s)?$", out, re.M)
    return [n.strip() for n in names if n.strip()]


class TextMut:
    """文本替换型变异。replace_all=True 时替换全部（用于会重复出现的标记）。"""

    def __init__(self, path: pathlib.Path, old: str, new: str, replace_all: bool = False):
        self.path, self.old, self.new, self.replace_all = path, old, new, replace_all

    def apply(self):
        t = self.path.read_text(encoding="utf-8")
        n = t.count(self.old)
        if n < 1:
            raise AssertionError(f"anchor 未命中: {self.path.name} :: {self.old[:60]!r}")
        t = t.replace(self.old, self.new) if self.replace_all else t.replace(self.old, self.new, 1)
        self.path.write_text(t, encoding="utf-8")
        return n

    def restore(self):
        t = self.path.read_text(encoding="utf-8")
        t = t.replace(self.new, self.old) if self.replace_all else t.replace(self.new, self.old, 1)
        self.path.write_text(t, encoding="utf-8")


class NewFileMut:
    def __init__(self, path: pathlib.Path, content: str):
        self.path, self.content = path, content

    def apply(self):
        self.path.write_text(self.content, encoding="utf-8")

    def restore(self):
        if self.path.exists():
            self.path.unlink()


EXPS: list[tuple[str, str, str, str, object]] = [
    # id, 说明, 侧(be/fe), 测试节点, 变异
    ("E1", "F-32 不可达处理函数：把 @click=\"trainBert\" 加回禁用按钮", "be",
     "tests/test_p2_11_round11.py::TestP239DeadCodeSplitRuling::test_unreachable_bert_handlers_removed",
     TextMut(FRONTEND / "src/views/user/components/ExperimentTab.vue",
             '<el-button\n                  type="primary"\n                  :disabled="bertDisabled"',
             '<el-button\n                  type="primary"\n                  @click="trainBert"\n                  :disabled="bertDisabled"')),

    ("E2", "保留侧：bertDisabled 被误当死代码删掉（改成 false/移除）", "be",
     "tests/test_p2_11_round11.py::TestP239DeadCodeSplitRuling::test_bert_ux_constant_retained",
     TextMut(FRONTEND / "src/views/user/components/ExperimentTab.vue",
             "const bertDisabled = true", "const bertDisabled = false")),

    ("E3", "BottomNav 死组件复活（components.d.ts 声明回来了）", "be",
     "tests/test_p2_11_round11.py::TestP239DeadCodeSplitRuling::test_bottomnav_dead_component_removed",
     TextMut(FRONTEND / "src/components.d.ts",
             "    BentoCell: typeof import('./components/common/BentoCell.vue')['default']",
             "    BentoCell: typeof import('./components/common/BentoCell.vue')['default']\n"
             "    BottomNav: typeof import('./components/common/BottomNav.vue')['default']")),

    ("E4", "RES-P1-004 登记正文缺失（'复核触发条件'字段被删）", "be",
     "tests/test_p2_11_round11.py::TestP239DeadCodeSplitRuling::test_retention_registry_has_res_p1_004_body",
     TextMut(REPO / "docs/RETENTION_REGISTRY.md", "复核触发条件", "复核条件", replace_all=True)),

    ("E5", "_flushed_buffer 注释退回'只写死缓冲区'（与保留决策不符）", "be",
     "tests/test_p2_11_round11.py::TestP239DeadCodeSplitRuling::test_flushed_buffer_comment_matches_retention_decision",
     TextMut(BACKEND / "app/services/observability_service.py", "有意保留", "（保留依据被删）", replace_all=True)),

    ("E6", "#33 棘轮：silences.py 加回一处手写 OperationLog", "be",
     "tests/test_p2_11_round11.py::TestP233AuditHelperRatchet",
     TextMut(BACKEND / "app/api/v1/silences.py",
             'logger.info("[silence] enabled',
             'from app.models.admin import OperationLog\n    db.add(OperationLog(operator_id=1))\n    logger.info("[silence] enabled')),

    ("E7", "#33 硬约束：request=request 改成 request=None（ip 来源被绕过）", "be",
     "tests/test_p2_11_round11.py::TestP233AuditHelperRatchet",
     TextMut(BACKEND / "app/api/v1/silences.py",
             "        request=request,\n        tenant_id=current_user.tenant_id,",
             "        request=None,\n        tenant_id=current_user.tenant_id,")),

    ("E8", "#35 棘轮：拔掉 event_bus 的降级接线", "be",
     "tests/test_p2_11_round11.py::TestP235SilentDegradationRatchet",
     TextMut(BACKEND / "app/core/event_bus.py",
             'record_silent_degradation("core.event_bus.publish")',
             'pass  # 接线被拔')),

    ("E9", "#34 分类表同步：新增一处 HTTPException（源码变了文档没同步）", "be",
     "tests/test_p2_11_round11.py::TestP234RaiseClassificationSynced",
     TextMut(BACKEND / "app/api/v1/silences.py",
             'if row is None:\n        raise HTTPException(status_code=404, detail="silence not found")\n    if row.is_active:',
             'if row is None:\n        raise HTTPException(status_code=404, detail="silence not found")\n'
             '    if row is None:\n        raise HTTPException(status_code=400, detail="probe")\n    if row.is_active:')),

    ("E10", "#32 事实锁：MODEL_PATHS 被静默改名（文档还写着未改）", "be",
     "tests/test_p2_11_round11.py::TestP232ModelMetadataContradictionRecorded",
     TextMut(BACKEND / "app/core/model_registry.py",
             "MODEL_PATHS: dict[str, str] = {", "MODEL_PATHS: dict[str, int] = {")),

    ("E11", "#36 竞态守卫：删掉 token !== seq 的丢弃分支", "fe",
     "src/composables/useListQuery.test.ts",
     TextMut(FRONTEND / "src/composables/useListQuery.ts",
             "      if (token !== seq) return // 已有更新的请求发出，丢弃本次响应",
             "      // 变异：守卫被删")),

    ("E12", "#36 页码重置：search() 不再作废在途请求", "fe",
     "src/composables/useListQuery.test.ts",
     TextMut(FRONTEND / "src/composables/useListQuery.ts",
             "    seq += 1\n    await options.setPage?.(1)",
             "    await options.setPage?.(1)")),

    ("E13", "#36 三态：empty 不再区分「从未加载」", "fe",
     "src/composables/useListQuery.test.ts",
     TextMut(FRONTEND / "src/composables/useListQuery.ts",
             "    () => loaded.value && !loading.value && !error.value && rows.value.length === 0",
             "    () => rows.value.length === 0")),

    ("E14", "#39 孤儿组件棘轮：新建一个无引用方的组件", "be",
     "tests/test_p2_11_round11.py::TestOrphanComponentRatchet",
     NewFileMut(FRONTEND / "src/components/common/ZzzProbeOrphan.vue",
                "<template><div>probe</div></template>\n")),
]


def main() -> int:
    lines: list[str] = []
    results: list[tuple[str, str, str]] = []

    def log(s: str) -> None:
        print(s)
        lines.append(s)

    log("P2 第十一轮 回退对照实验（每个闸门一条变异）")
    log("=" * 78)

    only = sys.argv[1] if len(sys.argv) > 1 else ""
    for eid, desc, kind, node, mut in EXPS:
        if only and eid != only:
            continue
        log(f"\n[{eid}] {desc}")
        log(f"    判据: {'后端 ' if kind == 'be' else '前端 '}{node}")
        try:
            hits = mut.apply()
            if isinstance(mut, TextMut):
                log(f"    anchor 命中 {hits} 处")
            rc, out = be_test(node) if kind == "be" else fe_test(node)
            failed = py_failed(out) if kind == "be" else fe_failed(out)
            if rc != 0 and failed:
                verdict = "RED-OK"
            elif rc != 0 and not failed:
                verdict = "INVALID(解析不出 failed)"
            else:
                verdict = "NOT-RED(假闸门!)"
            log(f"    变异轮: rc={rc} failed={len(failed)} -> {verdict}")
            for f in failed[:4]:
                log(f"      - {f}")
            if verdict == "INVALID(解析不出 failed)":
                log("      [诊断] " + (ANSI.sub("", out).strip().splitlines() or [""])[-1][:160])
        except AssertionError as exc:
            verdict = f"ANCHOR-MISSING({exc})"
            log(f"    {verdict}")
        finally:
            mut.restore()

        rc2, out2 = be_test(node) if kind == "be" else fe_test(node)
        failed2 = py_failed(out2) if kind == "be" else fe_failed(out2)
        green = "GREEN-OK" if rc2 == 0 else f"STILL-RED(failed={len(failed2)})"
        log(f"    恢复轮: rc={rc2} failed={len(failed2)} -> {green}")
        results.append((eid, verdict, green))

    log("\n" + "=" * 78)
    log("汇总：")
    for eid, v, g in results:
        log(f"  {eid}: 变异 {v} / 恢复 {g}")
    bad = [r for r in results if not r[1].startswith("RED-OK") or not r[2].startswith("GREEN-OK")]
    log(f"合计 {len(results)} 项，异常 {len(bad)} 项")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n日志落盘: {LOG}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
