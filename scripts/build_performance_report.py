from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def benchmark_status(value: float, benchmark: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "PASS" if value >= benchmark else "FAIL"
    return "PASS" if value <= benchmark else "FAIL"


def generate_report(offline: dict[str, Any], api: dict[str, Any]) -> str:
    b = offline.get("benchmarks", {})
    structured = offline.get("results", {}).get("structured", {})
    text = offline.get("results", {}).get("text", {})
    physio = offline.get("results", {}).get("physiological", {})
    fusion = offline.get("results", {}).get("fusion", {})

    lines: list[str] = []
    lines.append("# 模型性能评估总报告")
    lines.append("")
    lines.append("## 测试范围")
    lines.append("")
    lines.append("- 结构化模型")
    lines.append("- 文本模型")
    lines.append("- 生理数据模型")
    lines.append("- 多模态融合引擎")
    lines.append("- HTTP API 并发与错误处理")
    lines.append("")

    lines.append("## 预设基准与结论")
    lines.append("")
    lines.append(f"- 结构化模型 F1 >= {b.get('structured_f1_min', 0.85):.2f}，实际 {structured.get('f1', 0.0):.4f}，{benchmark_status(float(structured.get('f1', 0.0)), float(b.get('structured_f1_min', 0.85)))}")
    lines.append(f"- 文本模型 F1 >= {b.get('text_f1_min', 0.90):.2f}，实际 {text.get('f1', 0.0):.4f}，{benchmark_status(float(text.get('f1', 0.0)), float(b.get('text_f1_min', 0.90)))}")
    lines.append(f"- 融合延迟 <= {b.get('fusion_latency_ms_max', 200.0):.0f} ms，实际 {fusion.get('latency_ms', {}).get('avg_ms', 0.0):.2f} ms，{benchmark_status(float(fusion.get('latency_ms', {}).get('avg_ms', 0.0)), float(b.get('fusion_latency_ms_max', 200.0)), higher_is_better=False)}")
    lines.append(f"- 内存 <= {b.get('memory_mb_max', 2048.0):.0f} MB，实际值请结合运行时采样结果确认")
    lines.append("")

    lines.append("## 离线评估结果")
    lines.append("")
    for title, payload in [("结构化模型", structured), ("文本模型", text), ("生理数据模型", physio), ("多模态融合引擎", fusion)]:
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"- Samples: {payload.get('samples', 0)}")
        if "accuracy" in payload:
            lines.append(f"- Accuracy: {payload.get('accuracy', 0.0):.4f}")
        if "precision" in payload:
            lines.append(f"- Precision: {payload.get('precision', 0.0):.4f}")
        if "recall" in payload:
            lines.append(f"- Recall: {payload.get('recall', 0.0):.4f}")
        if "f1" in payload:
            lines.append(f"- F1: {payload.get('f1', 0.0):.4f}")
        latency = payload.get("latency_ms", {})
        if latency:
            lines.append(f"- Latency avg/p95/p99: {latency.get('avg_ms', 0.0):.2f} / {latency.get('p95_ms', 0.0):.2f} / {latency.get('p99_ms', 0.0):.2f} ms")
        lines.append("")

    lines.append("## 在线 API 压测结果")
    lines.append("")
    for name in ["structured", "text", "fusion"]:
        lines.append(f"### {name}")
        lines.append("")
        payload = api.get(name, {})
        for level, stats in payload.items():
            lines.append(f"- {level}: avg {stats.get('avg_ms', 0.0):.2f} ms, p95 {stats.get('p95_ms', 0.0):.2f} ms, errors {len(stats.get('errors', []))}")
        lines.append("")

    lines.append("## 错误处理验证")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(api.get("error_cases", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    lines.append("## 瓶颈分析与优化建议")
    lines.append("")
    lines.append("- 若高并发下 p95 延迟显著升高，优先考虑模型预加载、减少重复实例化和优化线程池使用。")
    lines.append("- 若文本模型 F1 未达 90%，建议提升文本清洗、一致性标注与类别不均衡处理。")
    lines.append("- 若结构化模型 F1 接近阈值但未达标，可尝试特征工程与阈值校准。")
    lines.append("- 若融合延迟超 200ms，应拆分慢路径模型、降低串行调用次数并缓存中间结果。")
    lines.append("- 若内存逼近 2GB，建议延后加载非核心模型，并减少同时驻留的推理对象数量。")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified performance report")
    parser.add_argument("--offline-json", default=str(ROOT / "reports/performance/model_performance_report.json"))
    parser.add_argument("--api-json", default=str(ROOT / "reports/performance/api_performance_report.json"))
    parser.add_argument("--output", default=str(ROOT / "reports/performance/unified_performance_report.md"))
    args = parser.parse_args()

    offline = load_json(Path(args.offline_json))
    api = load_json(Path(args.api_json))
    report = generate_report(offline, api)
    Path(args.output).write_text(report, encoding="utf-8")
    print(json.dumps({"output": args.output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()