"""T6（P2-1）：TRIPOD+AI 逐条对照导出.

把模型卡 + ROUND_16 验证读数组织成 TRIPOD+AI（Collins et al., BMJ 2024;385:e078378,
PMID 38626948）27 项对照字段。**如实分账**：每项状态 ∈
{evidence（仓内有据）/ partial（部分覆盖）/ missing（缺位）/ na（不适用）}，
缺位不粉饰；ROUND_16 本轮补齐的项单独标注 improved_by="ROUND_16"。

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/export_tripod_ai_appendix.py
产出:
    docs/planning/P2_R16_TRIPOD_AI_APPENDIX.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
OUT = REPO_ROOT / "docs" / "planning" / "P2_R16_TRIPOD_AI_APPENDIX.json"

PROBE_STRUCT = BACKEND_ROOT / "tests" / "tools" / "probe_p2_40_round16_struct_result.json"
PROBE_TEXT = BACKEND_ROOT / "tests" / "tools" / "probe_p2_40_round16_text_result.json"
METRICS_JSON = BACKEND_ROOT / "models" / "text" / "improved_bilingual_metrics.json"

# (item, section, de, status, summary, evidence, note)
ROWS: list[tuple[str, str, str, str, str, str, str]] = [
    ("1", "Title", "D;E", "partial", "研究类型/目标人群/结局可从模型卡读出，但无 TRIPOD+AI 式标题陈述",
     "backend/models/v1.23_external_lr/model_card.md", "注册资料撰写时按 checklist 重组标题"),
    ("2", "Abstract", "D;E", "missing", "无结构化摘要（TRIPOD+AI for Abstracts 13 项）", "-",
     "留待论文/注册资料阶段"),
    ("3a", "Introduction", "D;E", "evidence", "医疗情境与立项理由（心理健康预警）+ 既有模型引用",
     "docs/planning/P2_R15_CLINICAL_READINESS.md", ""),
    ("3b", "Introduction", "D;E", "evidence", "目标人群 = 学生群体；用途 = 风险预警辅助决策",
     "backend/models/v1.23_external_lr/model_card.md", ""),
    ("3c", "Introduction", "D;E", "evidence", "人群健康不平等：性别分组差距已量化（ROUND_16 T3）",
     "probe_p2_40_round16_struct_result.json#t3_fairness_assessment", "ROUND_16 补齐"),
    ("4", "Objectives", "D;E", "evidence", "目标：外部验证 + 临床效用证据（R14/R15/R16 章程）",
     "docs/planning/P2_R14_PROJECT_CHARTER.md", ""),
    ("5a", "Methods: Data", "D;E", "evidence", "三队列数据源分别登记（结构化/文本/生理互不相交）",
     "docs/ML_LEAKAGE_AUDIT.md；probe_p2_40_round16_struct_result.json#t2_cohort_disjointness", ""),
    ("5b", "Methods: Data", "D;E", "partial", "采集日期未在库内登记（reddit/中文语料仅版本名）",
     "datasets/text/*.csv", "日期链待补"),
    ("6a", "Participants", "D;E", "partial", "场景=高校学生心理健康筛查；中心数=不适用（多源公开数据）",
     "docs/planning/P2_R15_CLINICAL_READINESS.md", ""),
    ("6b", "Participants", "D;E", "evidence", "入组标准：PHQ-9 量表标注 / 文本长度>=5（v1_27 脚本明示）",
     "backend/scripts/modeling/v1_27/04_retrain_bilingual_text_groupwise.py", ""),
    ("6c", "Participants", "D;E", "na", "无治疗干预变量", "-", ""),
    ("7", "Data preparation", "D;E", "evidence", "预处理与质检：imputer 兼容(S-02)/cleaner 统计量/特征工程函数化",
     "backend/app/core/model_engine/loading.py；backend/app/ml/feature_engineering.py", ""),
    ("8a", "Outcome", "D;E", "evidence", "结局=depression_binary（PHQ-9 派生，阈值口径已登记）",
     "data/processed/v1_23_external/test.csv；ml_decision_thresholds.py", ""),
    ("8b", "Outcome", "D;E", "na", "量表自评，无第三方评定者", "-", ""),
    ("8c", "Outcome", "D;E", "na", "无盲法要求（自评量表）", "-", ""),
    ("9a", "Predictors", "D", "evidence", "预测因子选择=12 项结构化特征（schema 登记 + 文献来源）",
     "backend/models/v1.23_external_lr/feature_schema.json", ""),
    ("9b", "Predictors", "D;E", "evidence", "全部预测因子定义/量纲/范围在 schema 内登记",
     "backend/models/v1.23_external_lr/feature_schema.json", ""),
    ("9c", "Predictors", "D;E", "na", "无主观解释型预测因子", "-", ""),
    ("10", "Sample size", "D;E", "partial", "样本量已报（n=8379 语料/n=4318 外部留出/21 消融场景），无功效计算",
     "probe_p2_40_round16_text_result.json#t1_text_dca_ece", "功效分析缺位"),
    ("11", "Missing data", "D;E", "evidence", "缺失策略：median 填充（schema default_strategy）+ SimpleImputer",
     "backend/models/v1.23_external_lr/feature_schema.json", ""),
    ("12a", "Analytical methods", "D", "evidence", "数据用途与划分：groupwise 分层 K 折（按用户分组，禁跨用户泄漏）",
     "backend/app/ml/fusion_ablation.py:groupwise_kfold_indices；docs/ML_LEAKAGE_AUDIT.md", "R14 起持续强化"),
    ("12b", "Analytical methods", "D", "evidence", "预测因子处理：标准化/编码由 preprocessor Pipeline 固化",
     "backend/models/v1.23_external_lr/preprocessor.pkl", ""),
    ("12c", "Analytical methods", "D", "evidence", "模型类型+超参+内部验证：LR(C=1.0, class_weight=balanced)/MLP(BN)",
     "backend/scripts/modeling/v1_27/04_retrain_bilingual_text_groupwise.py；backend/models/artifacts/physiological/model.json", ""),
    ("12d", "Analytical methods", "D;E", "partial", "簇异质性：数据源异质性已记账；TRIPOD-Cluster 未做",
     "probe_p2_40_round16_struct_result.json#t2_cohort_disjointness", ""),
    ("12e", "Analytical methods", "D;E", "evidence", "性能度量全家桶：AUROC+CI/Brier/ECE/校准曲线/**DCA 净获益**",
     "probe_p2_40_round16_struct_result.json#t1_structured；probe_p2_40_round16_text_result.json#t1_text_dca_ece", "ROUND_16 T1 补齐 DCA/ECE"),
    ("12f", "Analytical methods", "E", "na", "评估未触发模型更新（无 recalibration 决策）", "-", ""),
    ("12g", "Analytical methods", "E", "partial", "预测计算路径已文档化（predict_text/predict_lite/settings 阈值）",
     "backend/app/core/model_engine/predict.py", "端到端公式复现件待补"),
    ("13", "Class imbalance", "D;E", "evidence", "类别不平衡处置：class_weight='balanced'（LR）",
     "backend/scripts/modeling/v1_27/04_retrain_bilingual_text_groupwise.py:LR_KWARGS", ""),
    ("14", "Fairness", "D;E", "evidence", "公平性：分组指标+差距量化（TPR/FPR/FNR/EOC）+缓解分账（建议未启用）",
     "backend/app/ml/fairness_mitigation.py；probe_p2_40_round16_struct_result.json#t3_*", "ROUND_16 T3 补齐（评估）"),
    ("15", "Model output", "D", "evidence", "输出=概率/风险分；阈值口径 SSOT 化（0.30 决策 + 0.50 headline 分离登记）",
     "backend/app/core/ml_decision_thresholds.py；models/text/improved_bilingual_metrics.json", "ROUND_16 T5 补齐"),
    ("16", "Methods: other", "D;E", "partial", "开发/评估数据差异：三模态队列不相交已如实登记（增量无法量化）",
     "probe_p2_40_round16_struct_result.json#t2_fusion_fixture_ablation", "ROUND_16 T2 阴性立项"),
    ("17", "Ethics", "D;E", "missing", "伦理审批信息未入库（公开数据集二次使用）", "-", "留待决策项"),
    ("18a", "Open science", "D;E", "evidence", "经费来源：无（毕业设计自筹）", "docs/planning/P2_R16_MODEL_VALIDATION_EVIDENCE.md", ""),
    ("18b", "Open science", "D;E", "evidence", "利益冲突：无", "docs/planning/P2_R16_MODEL_VALIDATION_EVIDENCE.md", ""),
    ("18c", "Open science", "D;E", "partial", "方案/章程在库（ROUND 提示词链），无预注册", "docs/planning/", ""),
    ("18d", "Open science", "D;E", "partial", "数据共享：含隐私语料受限，公开源可指认", "datasets/", ""),
    ("18e", "Open science", "D;E", "evidence", "代码共享：本仓库（含探针/变异/闸门）", "backend/tests/tools/", ""),
    ("18f", "Open science", "D;E", "evidence", "软件版本锁定：requirements.lock + sklearn 兼容补丁登记",
     "backend/requirements.lock；backend/app/core/model_engine/loading.py", ""),
    ("19", "PPI", "D;E", "missing", "无患者/公众参与记录", "-", "留待补充"),
    ("20a", "Results", "D;E", "evidence", "受试者流转：语料过滤（len>=5）/去重/分组规则可复现",
     "probe_p2_40_round16_text.py", ""),
    ("20b", "Results", "D;E", "evidence", "受试者特征：性别/来源分布已报", "probe_p2_40_round16_struct_result.json#t3", ""),
    ("21", "Results", "D;E", "evidence", "各分析集的阳性率与事件数：positive_rate 全域登记",
     "probe_p2_40_round16_text_result.json#t1", ""),
    ("22", "Results", "D", "evidence", "完整模型规格：特征系数/权重/特征名落档",
     "backend/models/v1.23_external_lr/feature_coefficients.csv", ""),
    ("23", "Results", "D;E", "evidence", "性能估计带 CI（bootstrap）+ 关键亚组（性别）+ DCA 净获益",
     "probe_p2_40_round16_struct_result.json；test_p2_40_model_validation_round16.py", "ROUND_16 强化"),
    ("24", "Results", "E", "na", "无模型更新", "-", ""),
    ("25", "Discussion", "D;E", "partial", "解读含公平性与泄漏教训（R14/B.5 更正链）",
     "docs/ML_LEAKAGE_REMEDIATION.md", ""),
    ("26", "Discussion", "D;E", "evidence", "局限性：阴性结论如实立项（融合增量/纵向早期检测）",
     "docs/planning/P2_R15_EARLY_DETECTION_RESULT.md；P2_R16 本档 T2", ""),
    ("27a", "Discussion", "D;E", "partial", "低质/缺失输入：NaN 拦截+安全网存在，端到端降级行为未逐条文档化",
     "backend/app/core/risk_thresholds.py", ""),
    ("27b", "Discussion", "D;E", "partial", "所需专业技能：心理测评解读+AI 输出复核（报告已述）",
     "backend/models/v1.23_external_lr/model_card.md", ""),
    ("27c", "Discussion", "D;E", "partial", "后续步骤：NEXT_RELEASE 提案链在库",
     "docs/planning/P2_NEXT_RELEASE_PROPOSALS.md", ""),
]


def load_probe(name: str) -> dict | None:
    p = {"struct": PROBE_STRUCT, "text": PROBE_TEXT}[name]
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> None:
    struct = load_probe("struct")
    text = load_probe("text")

    items = []
    for item, section, de, status, summary, evidence, note in ROWS:
        improved = ""
        if "ROUND_16" in note:
            improved = "ROUND_16"
        items.append(
            {
                "item": item,
                "section": section,
                "dev_eval": de,
                "status": status,
                "summary": summary,
                "evidence": evidence,
                "note": note,
                "improved_by": improved,
            }
        )

    counts: dict[str, int] = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1

    readings: dict[str, object] = {}
    if metrics := (METRICS_JSON.exists() and json.loads(METRICS_JSON.read_text(encoding="utf-8"))):
        readings["bilingual_groupwise_ooF"] = {
            k: metrics["groupwise_ooF"][k]
            for k in ("n", "recall", "precision", "f1", "roc_auc", "brier")
        }
        readings["threshold_governance"] = metrics.get("threshold_governance")
    if struct:
        readings["t1_structured_dca_ece"] = struct["sections"]["t1_structured"]
        readings["t2_fusion_ablation"] = struct["sections"]["t2_fusion_fixture_ablation"]
        readings["t3_fairness_disparities"] = struct["sections"]["t3_fairness_assessment"]["disparities"]
    if text:
        readings["t1_text_dca_ece"] = text["t1_text_dca_ece"]
        readings["t5_threshold_repro"] = text["t5_threshold_repro"]

    payload = {
        "title": "TRIPOD+AI 对照附录（ROUND_16 导出）",
        "guideline": {
            "citation": "Collins GS, et al. TRIPOD+AI. BMJ 2024;385:e078378. PMID 38626948",
            "items": 27,
            "sections": [
                "Title", "Abstract", "Introduction", "Methods", "Open science",
                "Patient and public involvement", "Results", "Discussion",
            ],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status_counts": counts,
        "items": items,
        "validation_readings": readings,
        "disclaimer": (
            "本导出为工程侧自评映射：status=evidence 仅代表仓内有对应材料，"
            "不等于通过 PROBAST+AI 评审；missing/partial 项如实留档，待注册资料/论文阶段补齐。"
        ),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status_counts": counts, "written": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
