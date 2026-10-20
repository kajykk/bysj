"""作品集数字自检（ROUND_22 / T4）—— 文档钉事实。

用途
----
`README.md` 与 `docs/EVALUATION_TRUST_SUMMARY.md` 是对外材料，里面的数字必须能复算。
本脚本把「文档里的字面量」与「仓库内可复算的产物」逐条比对，任何一条对不上就返回非零。

两类探针
--------
1. **可执行复算（probe）**：从代码 / 测试 / JSON 现场算出真值，例如
   `git ls-files + AST` 得到的划分入口数、有效路由展开（`route_counting.py`）
  得到的端点数、`classify_p2_35_batch6_result.json` 里的桶计数。
2. **报告对齐（report）**：数字的源头是需要数据集才能重跑的实验报告（CI 无数据集），
   因此判据改为「概览层数字 == 权威报告里的同一字面量」——即跨文档漂移检测。
   这类检查在 `CHECKS` 里以 `report_of` 字段标注，不假装自己能复算。

判据强度
--------
每条检查钉的是**带单位的完整字面量**（如 ``40 个交付脚本 / 88 处划分与挑优调用点``），
不是"文档里出现过 88 这个数字"。理由：后者会被页面别处的同值命中，改了真地方也不会红。

刻意不纳入闸门的数字
--------------------
测试用例数（`pytest --collect-only` / `vitest list`）：每次提交都在变，钉死只会把闸门
变成噪声。README 里以"带日期的快照 + 复现命令"呈现，并在同一行说明这一点。

用法
----
    cd backend
    python tests/tools/check_portfolio_numbers.py            # 逐条核对，失败返回 1
    python tests/tools/check_portfolio_numbers.py --show     # 只打印探针算出的真值
    python tests/tools/check_portfolio_numbers.py --show scale
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
DOCS = REPO / "docs"

README = REPO / "README.md"
SUMMARY = DOCS / "EVALUATION_TRUST_SUMMARY.md"

# 权威报告（report 类探针的对照源）
AUDIT_REPORT = DOCS / "ML_LEAKAGE_AUDIT.md"
EARLY_REPORT = DOCS / "planning" / "P2_R15_EARLY_DETECTION_RESULT.md"

# 可执行产物的路径
SCANNER = BACKEND / "tests" / "tools" / "leakage_audit_scan.py"
BUCKET_JSON = BACKEND / "tests" / "tools" / "classify_p2_35_batch6_result.json"
METRICS_JSON = DOCS / "planning" / "backend_text_bilingual_v2_metrics.json"
AUTH_GATE = BACKEND / "tests" / "test_p2_41_round17_auth_gate.py"
COMPOSE = REPO / "docker-compose.yml"

# 路由计数子进程：哨兵行前缀 + 超时。哨兵是为了在 stderr/stdout 混入
# 无关告警时也能定位到我们那行 JSON（不假设"最后一行就是结果"）。
# 计数逻辑在 tests/tools/route_counting.py：跨 fastapi 版本展开 include 标记，
# 详见该模块 docstring（2026-10-21 根因：0.151 的 include_router 不再扁平化）。
_ROUTE_PROBE_SENTINEL = "__ROUTE_PROBE__"
_ROUTE_PROBE_TIMEOUT_S = 240
TOOLS = BACKEND / "tests" / "tools"

_ROUTE_PROBE_TEMPLATE = '''
import json
import sys

sys.path.insert(0, %(backend)r)
sys.path.insert(0, %(tools)r)

from route_counting import count_app_routes

from app.main import app

print(
    %(sentinel)r
    + json.dumps(count_app_routes(app))
)
'''


# ── 文本归一化 ─────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """去掉 markdown 强调符与行内代码符，让"字面量"不受排版影响。

    只去掉 `*` 与反引号：这两个是唯一会插进数字短语中间的装饰符
    （``**341 处 except 候选**`` → ``341 处 except 候选``）。
    不做空白折叠——中文文档里多一个空格就是排版错误，应当被看见。
    """
    return text.replace("*", "").replace("`", "")


# ── 探针：可执行复算 ───────────────────────────────────────────────────


def _load_module(path: Path, name: str):
    """按路径加载脚本模块（tests/tools 不是包，无法直接 import）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - 路径写错时才会发生
        raise RuntimeError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    # 必须先登记到 sys.modules：模块里带 `from __future__ import annotations` 时，
    # dataclass 会用 cls.__module__ 回查 sys.modules 来解析字符串注解，
    # 查不到就会在 `"str"` 这种内置类型上抛 TypeError。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def probe_scan() -> dict[str, int]:
    """ML 划分/挑优入口：涉及文件数 + 调用点数（git ls-files + AST）。

    与 `leakage_audit_scan.py` 的默认口径保持一致：**排除 tests/** 下的调用**
    （测试代码里的 `train_test_split` 不是评估口径）。少了这一步会多算 6 处、
    把数字从 88 抬到 94 —— 这正是"口径必须与权威报告同形"的实例。
    """
    module = _load_module(SCANNER, "leakage_audit_scan_for_numbers")
    files = module._iter_py_files()
    findings: list[dict] = []
    for path in files:
        findings.extend(hit for hit in module.scan_file(path) if not hit["in_test"])
    return {
        "files": len({hit["file"] for hit in findings}),
        "entries": len(findings),
    }


def probe_metrics() -> dict[str, float]:
    """文本模态双口径读数（同一模型、同一份语料）。"""
    data = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
    return {
        "groupwise_f1": data["groupwise_ooF"]["f1"],
        "textwise_f1": data["textwise_ooF"]["f1"],
        "n": data["groupwise_ooF"]["n"],
    }


def probe_buckets() -> dict[str, int]:
    """#35 静默降级桶计数（分类产物是入库 JSON）。"""
    data = json.loads(BUCKET_JSON.read_text(encoding="utf-8"))
    counts = data["counts"]
    return {
        "total": len(data["rows"]),
        "wired": counts["W"],
        "degraded": counts["X"],
        "fail_closed": counts["G"],
    }


def probe_auth_gate() -> dict[str, int]:
    """鉴权入口登记表：总入口数 / 强制 / 豁免（AST 读 REGISTRY，不查字符串）。"""
    tree = ast.parse(AUTH_GATE.read_text(encoding="utf-8"))
    registry: ast.Dict | None = None
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if isinstance(target, ast.Name) and target.id == "REGISTRY":
            if isinstance(node.value, ast.Dict):
                registry = node.value
    if registry is None:  # pragma: no cover - 结构被改名时才会发生
        raise RuntimeError("test_p2_41_round17_auth_gate.py 里找不到 REGISTRY 字典")
    buckets = {"enforced": 0, "exempt": 0}
    for value in registry.values:
        if not isinstance(value, ast.Call) or not value.args:
            continue
        first = value.args[0]
        if isinstance(first, ast.Constant) and first.value in buckets:
            buckets[str(first.value)] += 1
    return {
        "entries": len(registry.keys),
        "enforced": buckets["enforced"],
        "exempt": buckets["exempt"],
    }


def probe_routes() -> dict[str, int]:
    """运行时端点：FastAPI 里真实注册的 REST / WebSocket 路由数。

    为什么必须开**独立解释器**来数（2026-10-20 实测）
    ------------------------------------------------
    最初是在当前进程里 `from app.main import app` 直接数 `app.routes`。本地独立跑
    对得上（206/3），但 CI 全量套件跑到本闸门时实测 **5 个 REST + 3 个 WS** ——
    恰好等于 `app/main.py` 自注册的那 5 条 `@app.get` 与 3 条 `@app.websocket`，
    也就是说那一刻的 `app` 实例**一条 include_router 进来的 v1 路由都没有**。
    仓库里对这类现象早有记录：`tests/test_observability_api.py` 为避免同一问题
    直接把该断言 `pytest.skip` 掉了（注释：「全量套件下 api_router 因模块加载
    顺序为空」）。

    结论：`app.routes` 是**进程内可变全局**，它的读数取决于前面 7000+ 个用例把
    模块表搅成什么样。以此为判据的闸门必然随执行顺序漂移；而 README 声称的
    「运行时端点」本意是**交付形态**（干净解释器 import 一次得到的东西）。
    故改为子进程：`sys.executable -c` 里 import 一次、数一次、打印哨兵行。

    为什么必须数**有效路由**而不是扁平 isinstance（2026-10-21 实测）
    ---------------------------------------------------------------
    子进程化之后 CI 仍红，且子进程同样数到 5：CI 的 `requirements.txt` 无上界，
    装到 fastapi 0.151.0 + starlette 1.9.0，其 `include_router()` 不再把子路由
    扁平拷进 `app.routes`，而是挂 `_IncludedRouter` 标记对象（请求匹配时展开）。
    影子安装实测：flat=5/3、展开后 206/3；本地 fastapi 0.135.3 则是 flat=206/3、
    展开恒等。即 README 的数字在两个版本下都成立，旧指针方法被新表示打破。
    故计数委托 `tests/tools/route_counting.py`：沿 `original_router` 递归展开后
    再分类，`markers` 字段在 CI 日志里留证「展开确实发生过」。

    失败一律抛错，**不返回 0** —— 数不出来就说数不出来，不拿 0 当读数。
    """
    measured = _measure_routes_in_child()
    return measured


def _measure_routes_in_child() -> dict[str, int]:
    """实际去子进程里数（`probe_routes` 的实现细节；变异见证 T4 翻转的就是这一层）。"""
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    source = _ROUTE_PROBE_TEMPLATE % {
        "backend": str(BACKEND),
        "tools": str(TOOLS),
        "sentinel": _ROUTE_PROBE_SENTINEL,
    }
    try:
        proc = subprocess.run(  # noqa: S603 - 参数固定，无 shell，无用户输入
            [sys.executable, "-c", source],
            cwd=str(BACKEND),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_ROUTE_PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"路由计数子进程无法执行（不返回 0）：{exc!r}") from exc

    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-8:])
        raise RuntimeError(
            f"路由计数子进程失败（exit={proc.returncode}）；不返回 0：\n{tail}"
        )
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith(_ROUTE_PROBE_SENTINEL):
            payload = json.loads(line[len(_ROUTE_PROBE_SENTINEL) :])
            try:
                return {
                    "rest": int(payload["rest"]),
                    "ws": int(payload["ws"]),
                    "unknown": int(payload["unknown"]),
                    "markers": int(payload["markers"]),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"路由计数子进程返回了无法解析的读数（不返回 0）：{exc!r}"
                ) from exc
    raise RuntimeError(
        "路由计数子进程没有输出哨兵行 "
        f"{_ROUTE_PROBE_SENTINEL}；stdout 尾部：{(proc.stdout or '')[-400:]!r}"
    )


def probe_scale() -> dict[str, int]:
    """项目规模：文件数 / 表声明数 / compose 服务数（口径写死，可复算）。"""

    def count_py(rel: str) -> int:
        return sum(
            1
            for p in (BACKEND / rel).rglob("*.py")
            if "__pycache__" not in p.parts
        )

    tables = 0
    for path in (BACKEND / "app" / "models").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        tables += 1

    services = 0
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "services:")
    for line in lines[start + 1 :]:
        if line and not line.startswith((" ", "\t", "#")):
            break
        if re.match(r"^  [A-Za-z0-9_.-]+:\s*$", line):
            services += 1

    return {
        "route_files": count_py("app/api"),
        "service_files": count_py("app/services"),
        "core_files": count_py("app/core"),
        "ml_files": count_py("app/ml"),
        "tables": tables,
        "compose_services": services,
    }


# ── 探针：报告对齐（源头在实验报告里，CI 无数据集，故做跨文档一致性）──


def probe_report_leakage() -> dict[str, str]:
    """泄漏红利与 L4 证据：只认权威报告里的字面量。"""
    text = _normalize(AUDIT_REPORT.read_text(encoding="utf-8"))
    return {
        "delta_f1": "+0.3111" if "+0.3111" in text else "<缺失>",
        "delta_auc": "+0.1573" if "+0.1573" in text else "<缺失>",
        "single_auc": "1.0000" if "1.0000" in text else "<缺失>",
        "corr": "**1.0**" if "**1.0**" in text else "<缺失>",
    }


def probe_report_early_detection() -> dict[str, str]:
    """阴性结论读数：只认早期检测报告里的字面量。"""
    text = _normalize(EARLY_REPORT.read_text(encoding="utf-8"))
    return {
        "erde_a": "0.0052" if "0.0052" in text else "<缺失>",
        "erde_c": "0.1958" if "0.1958" in text else "<缺失>",
        "f_a": "0.6721" if "0.6721" in text else "<缺失>",
        "f_c": "0.5820" if "0.5820" in text else "<缺失>",
    }


PROBES = {
    "scan": probe_scan,
    "metrics": probe_metrics,
    "buckets": probe_buckets,
    "auth_gate": probe_auth_gate,
    "routes": probe_routes,
    "scale": probe_scale,
    "report_leakage": probe_report_leakage,
    "report_early": probe_report_early_detection,
}


# ── 检查表 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Check:
    """一条"文档断言"。

    Attributes:
        cid: 稳定编号，红的时候按它定位。
        doc: 被检查的文档。
        template: ``str.format(**probe值)`` 得到的**完整字面量**；文档里必须原样出现。
        probe: 对应的探针键。
        kind: ``probe`` = 现场复算；``report`` = 与权威报告对齐。
        why: 这个数字想说明什么（红的时候一起打出来，省得回头查）。
    """

    cid: str
    doc: Path
    template: str
    probe: str
    kind: str
    why: str


CHECKS: tuple[Check, ...] = (
    Check(
        "readme.routes",
        README,
        "{rest} 个 REST 端点 + {ws} 个 WebSocket 长连接",
        "routes",
        "probe",
        "对外声称的接口规模，数的是运行时真实注册的路由",
    ),
    Check(
        "readme.tables",
        README,
        "3 个 WebSocket 长连接、{tables} 张数据表",
        "scale",
        "probe",
        "表数量按 __tablename__ 声明计数",
    ),
    Check(
        "readme.scan",
        README,
        "{files} 个交付脚本 / {entries} 处划分与挑优调用点",
        "scan",
        "probe",
        "泄漏审计盘清的家底（git ls-files + AST，不含未入库脚本）",
    ),
    Check(
        "readme.groupwise",
        README,
        "F1 {groupwise_f1:.4f}（同一模型随机划分 {textwise_f1:.4f}）",
        "metrics",
        "probe",
        "文本模态泛化口径 vs 随机划分；后者不可当泛化引用",
    ),
    Check(
        "readme.buckets",
        README,
        "{total} 处 except 候选全部裁定：已接线 {wired} / 真降级留档 {degraded} / fail-closed {fail_closed}",
        "buckets",
        "probe",
        "#35 静默降级分桶；桶计数由分类产物钉住",
    ),
    Check(
        "readme.auth_gate",
        README,
        "{entries} 个 token 操作入口（{enforced} 强制 + {exempt} 显式豁免）",
        "auth_gate",
        "probe",
        "鉴权入口清单由 AST 发现集与登记表全等比对",
    ),
    Check(
        "readme.scale.api",
        README,
        "{route_files} 个 API 路由文件",
        "scale",
        "probe",
        "backend/app/api/**/*.py",
    ),
    Check(
        "readme.scale.services",
        README,
        "{service_files} 个业务服务文件",
        "scale",
        "probe",
        "backend/app/services/**/*.py",
    ),
    Check(
        "readme.scale.core",
        README,
        "{core_files} 个核心模块文件",
        "scale",
        "probe",
        "backend/app/core/**/*.py",
    ),
    Check(
        "readme.scale.ml",
        README,
        "{ml_files} 个 ML 模块文件",
        "scale",
        "probe",
        "backend/app/ml/**/*.py",
    ),
    Check(
        "readme.scale.tables",
        README,
        "{tables} 张数据表声明",
        "scale",
        "probe",
        "AST 统计 __tablename__",
    ),
    Check(
        "readme.scale.routes",
        README,
        "运行时 {rest} 个 REST 端点 + {ws} 个 WebSocket",
        "routes",
        "probe",
        "app.routes 计数（与概览表同一来源，措辞不同故单列）",
    ),
    Check(
        "readme.scale.compose",
        README,
        "{compose_services} 个 Docker 服务",
        "scale",
        "probe",
        "docker-compose.yml 的 services 段",
    ),
    Check(
        "summary.delta_f1",
        SUMMARY,
        "ΔF1 {delta_f1} / ΔAUC {delta_auc}",
        "report_leakage",
        "report",
        "中文语料的泄漏红利（需数据集重跑，CI 只做跨文档对齐）",
    ),
    Check(
        "summary.single_auc",
        SUMMARY,
        "单特征 AUC {single_auc}",
        "report_leakage",
        "report",
        "L4 目标泄漏的判别力证据",
    ),
    Check(
        "summary.scan",
        SUMMARY,
        "{files} 个交付脚本 / {entries} 处划分与挑优调用点",
        "scan",
        "probe",
        "与 README 同一来源",
    ),
    Check(
        "summary.negative",
        SUMMARY,
        "ERDE50 {erde_c} vs {erde_a}、F_latency {f_c} vs {f_a}",
        "report_early",
        "report",
        "阴性结论读数；只认早期检测报告，不重算",
    ),
    # ── 作品集素材（T5）：只复用已钉数字，不引入新事实 ──────────────────
    Check(
        "readme.bullet_leakage",
        README,
        "全仓 {files} 个交付脚本里的 {entries} 处评估入口",
        "scan",
        "probe",
        "作品集第 1 条：审计覆盖面",
    ),
    Check(
        "readme.bullet_degradation",
        README,
        "{total} 处 except 候选逐条裁定为",
        "buckets",
        "probe",
        "作品集第 2 条：静默降级分桶",
    ),
    Check(
        "readme.bullet_auth",
        README,
        "{entries} 个 token 操作入口的租户封禁校验",
        "auth_gate",
        "probe",
        "作品集第 3 条：鉴权入口覆盖",
    ),
    Check(
        "readme.bullet_checks",
        README,
        "{checks} 个关键数字逐条对回仓库产物",
        "self",
        "probe",
        "作品集第 4 条：自检脚本覆盖的条数（由 CHECKS 自身长度决定）",
    ),
)

# 自指探针：检查表自己的条数。放进 PROBES 是因为它要等 CHECKS 定义完才能算。
PROBES["self"] = lambda: {"checks": len(CHECKS)}


def run_checks() -> list[str]:
    """执行全部检查，返回失败描述列表（空 = 全绿）。"""
    cache: dict[str, dict] = {}
    doc_cache: dict[Path, str] = {}
    failures: list[str] = []

    for check in CHECKS:
        if check.probe not in cache:
            cache[check.probe] = PROBES[check.probe]()
        try:
            expected = check.template.format(**cache[check.probe])
        except KeyError as exc:  # pragma: no cover - 模板与探针不匹配时才会发生
            failures.append(f"[{check.cid}] 模板占位符 {exc} 在探针 {check.probe} 里不存在")
            continue

        if check.doc not in doc_cache:
            doc_cache[check.doc] = _normalize(check.doc.read_text(encoding="utf-8"))
        text = doc_cache[check.doc]

        if expected not in text:
            failures.append(
                f"[{check.cid}] {check.doc.name} 里找不到期望字面量：{expected}\n"
                f"    这个数字想说明：{check.why}"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="作品集数字自检")
    parser.add_argument(
        "--show",
        nargs="?",
        const="__all__",
        help="只打印探针算出的真值（可指定探针名，如 scale）",
    )
    args = parser.parse_args(argv)

    if args.show:
        keys = list(PROBES) if args.show == "__all__" else [args.show]
        for key in keys:
            if key not in PROBES:
                print(f"未知探针: {key}（可选：{', '.join(PROBES)}）")
                return 2
            print(f"[{key}] {json.dumps(PROBES[key](), ensure_ascii=False)}")
        return 0

    failures = run_checks()
    total = len(CHECKS)
    if failures:
        print(f"数字自检 FAIL：{len(failures)}/{total} 条不一致\n")
        for item in failures:
            print(f"  ✗ {item}")
        print("\n修复方式：改文档使其与仓库产物一致，或改产物并同步文档（两边都必须动）。")
        return 1

    print(f"数字自检 OK：{total}/{total} 条与仓库产物一致")
    for check in CHECKS:
        print(f"  ✓ {check.cid:<22} {check.kind:<7} {check.doc.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
