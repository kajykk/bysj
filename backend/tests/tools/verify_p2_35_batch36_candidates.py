"""第三十六批存在性核查：接线 2 处 + 16 条不接，18 文件 18 条。

挑簇口径（第三十五批起第四代信号：location 登记表零收录）：
- 第三十五批改用「候选文件从未出现在任何 location 登记表
  `| a.b.c | path/x.py |` 行里」的结构信号（登记表共收录 22 文件），
  减去第二十至三十四批已处理簇 + 逐簇人工核对 ⇒ 命中 8 文件 8 条。
- 本批沿用同款信号，排除集 = 三份审计文档（P2_11/P2_12/P2_13）的
  location 登记表行 + 全部批章节登记的候选路径（**允许 `path.py:行号`
  形式——第三十五批起的裁定表用带行号登记，不剥行号会漏排已处理文件，
  本批挑簇时实测抓到这个坑并修复正则**）+ scan 已接线候选。
  命中 15 个文件 18 条，逐簇人工核对后 2 接 16 不接。

本批接线（X 118→116，W 100→102）：
    app/core/text_m2_bert_predictor.py:162  推理失败 → return None
      —— 与第十六批 services.shadow_mode.compare_failed 同链同语义
      （单次对拍样本从一致率统计中静默消失，影子期切换决策依据出现
      无痕缺口）；调用方 _shadow_predict L98-99 `if m2_result is None:
      return` 不记统计，get_stats 消费方与「未采样到」不可分辨。
    app/core/log_sanitizer.py:449  脱敏失败 → 未脱敏放行
      —— 实测生产可达：exc_info 是异常实例（非 tuple）时 L443
      `len(record.exc_info)` 抛 TypeError ⇒ 整个 exc_info 脱敏被跳过，
      异常消息里的敏感值未脱敏放行；本仓 5 处 `exc_info=<实例>` 用法
      （含 pii_crypto PII 解密失败）都会走到。filter 永远返回 True
      ⇒ 同形；仅 debug 级信号（生产默认级别不可见）。

不接 16 条（逐条硬判据见 P2_13「一之三十七」节）：
  instance.py:25 V / model_registry.py:351 V / startup_status.py:100 S 同源 /
  text_tokenizer.py:37 F / hyperparameter_tuning.py:38 V+D /
  hyperparameter_tuning.py:51 V / model_loader.py:46 V /
  model_validation.py:135 V / scaler.py:47 P / auth_service.py:277 V/F /
  auth_service.py:436 C/V / experiment_evaluator.py:126 V /
  experiment_metrics.py:43 V / pdf_report_service.py:295 V /
  pdf_report_service.py:450 V / tasks/observability.py:79 V+R

运行时证据见 `probe_p2_35_batch36_runtime.py`。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]
TOOLS = BACKEND / "tests" / "tools"

# (文件, 行号, 所属函数, 本批人工裁定)
TARGETS = [
    ("app/core/instance.py", 25, "get_instance_id", "V"),
    ("app/core/log_sanitizer.py", 451, "filter", "W-接线"),
    ("app/core/model_registry.py", 351, "resolve_model_path", "V"),
    ("app/core/startup_status.py", 100, "record", "S-同源"),
    ("app/core/text_m2_bert_predictor.py", 162, "predict", "W-接线"),
    ("app/core/text_tokenizer.py", 37, "_get_jieba", "F"),
    ("app/ml/hyperparameter_tuning.py", 38, "_load_tuning_cache", "V+D"),
    ("app/ml/hyperparameter_tuning.py", 51, "_append_tuning_cache", "V"),
    ("app/ml/model_loader.py", 46, "_resolve_artifacts_dir", "V"),
    ("app/ml/model_validation.py", 135, "_bootstrap_auc_ci_with_count", "V"),
    ("app/ml/scaler.py", 47, "__getattr__", "P"),
    ("app/services/auth_service.py", 277, "change_password", "V/F"),
    ("app/services/auth_service.py", 436, "logout", "C/V"),
    ("app/services/experiment_evaluator.py", 126, "compare", "V"),
    ("app/services/experiment_metrics.py", 43, "metrics", "V"),
    ("app/services/pdf_report_service.py", 295, "generate_pdf", "V"),
    ("app/services/pdf_report_service.py", 450, "generate_pdf_stream", "V"),
    ("app/tasks/observability.py", 79, "_flush_lock_stats_impl", "V+R"),
]


def load(modname: str):
    spec = importlib.util.spec_from_file_location(modname, TOOLS / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def enclosing_func(tree: ast.AST, line: int) -> str | None:
    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1] if best else None


def main() -> int:
    scan = load("scan_p2_35_batch6")
    classify = load("classify_p2_35_batch6")
    scan.main()  # 重跑 scan 落盘，保证不是陈旧快照
    result = json.loads(
        (TOOLS / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8")
    )
    by_key = {
        (r["file"], r["line"]): r for r in result["real_list"] + result["probe_list"]
    }

    print("=" * 78)
    print("第三十六批存在性核查（2 接线 + 16 不接，18 条）")
    print("=" * 78)

    missing = 0
    drift = 0
    wired_count = 0
    buckets: dict[str, int] = {}

    for rel, line, fn_name, verdict in TARGETS:
        rec = by_key.get((rel, line))
        if rec is None:
            missing += 1
            print(f"  MISSING  {rel}:{line} ({fn_name})  <- scan 未收录")
            continue

        src = (BACKEND / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)

        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.lineno == line:
                target = node
                break
        if target is None:
            missing += 1
            print(f"  MISSING  {rel}:{line} ({fn_name})  <- 该行没有 except handler")
            continue

        actual_fn = enclosing_func(tree, line)
        if actual_fn != fn_name:
            drift += 1
            print(f"  FUNC-DRIFT {rel}:{line} 期望 {fn_name}，实际 {actual_fn}")

        body_src = ast.unparse(target)
        func_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_name:
                if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                    func_src = ast.unparse(fn)

        bucket = classify.classify(rec, body_src, func_src)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        wired = "record_silent_degradation" in body_src
        if wired:
            wired_count += 1
        expect_wired = verdict == "W-接线"
        flag = ""
        if wired != expect_wired:
            flag = "  <<< 接线状态与裁定不符"
        print(
            f"  OK  {rel}:{line} ({fn_name})  "
            f"分类器={bucket}  人工={verdict}  接线={'是' if wired else '否'}{flag}"
        )

    print("-" * 78)
    print(f"MISSING={missing}  FUNC-DRIFT={drift}  接线={wired_count}（期望 2）")
    print(f"分类器桶分布：{buckets}")
    return 0 if (missing == 0 and drift == 0 and wired_count == 2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
