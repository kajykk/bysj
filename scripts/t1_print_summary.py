"""读取 T1 评估汇总报告并格式化输出."""
import json
from pathlib import Path

summary_path = Path(r"e:\code\bysj\models\artifacts\t1_group_cv_summary.json")
data = json.loads(summary_path.read_text(encoding="utf-8"))

print("=" * 70)
print("T1 全模态 GroupKFold 评估汇总")
print("=" * 70)
print(f"实验ID: {data['experiment_id']}")
print(f"耗时: {data['elapsed_s']}s")
print(f"模态数: {data['n_modalities']}")
print()

for r in data["results"]:
    mod = r["modality"]
    g = r["group_cv"]
    s = r["stratified_cv"]
    gap = r["gap"]
    acc = r["acceptance"]

    print(f"--- {mod} ---")
    print(f"  GroupKFold:      F1={g['f1_mean']:.4f}±{g['f1_std']:.4f} (CI95: [{g['f1_ci_lower']:.4f}, {g['f1_ci_upper']:.4f}])")
    print(f"                   AUC={g['auc_mean']:.4f}±{g['auc_std']:.4f} (CI95: [{g['auc_ci_lower']:.4f}, {g['auc_ci_upper']:.4f}])")
    print(f"  StratifiedKFold: F1={s['f1_mean']:.4f}±{s['f1_std']:.4f}")
    print(f"                   AUC={s['auc_mean']:.4f}±{s['auc_std']:.4f}")
    print(f"  差距: F1_gap={gap['f1_gap']:.4f}, AUC_gap={gap['auc_gap']:.4f}")
    print(f"  泄露级别: {r['leakage_level']}")
    print(f"  目标 F1>=0.60: GroupKFold={'✓' if acc['group_cv_meets_target'] else '✗'}, Stratified={'✓' if acc['stratified_cv_meets_target'] else '✗'}")
    print(f"  解读: {gap['interpretation']}")
    print()

print("=" * 70)
print("协议:")
proto = data["protocol"]
print(f"  折数: {proto['n_folds']}, 种子: {proto['seeds']}")
print(f"  分类器: {proto['classifier']}")
print(f"  分组键: {proto['group_key']}")
print(f"  备注: {proto['note']}")
