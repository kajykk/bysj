"""生理数据及多模态融合对比实验"""
import asyncio
from app.core.model_engine import ModelEngine


async def run_experiment():
    engine = ModelEngine()

    # 实验样本定义
    structured_features = {
        'age': 22, 'gender': 1, 'study_year': 3, 'cgpa': 3.5,
        'stress_level': 3, 'sleep_duration': 7, 'social_support': 4,
        'financial_pressure': 2, 'family_history': 0,
        'academic_pressure': 3, 'exercise_frequency': 2,
        'anxiety': 2, 'panic_attack': 0, 'treatment_seeking': 1
    }

    text = '最近感觉压力很大，睡不好觉，对什么都提不起兴趣'

    physiological_high_risk = {
        'sleep_hours': 5.0, 'sleep_quality': 2,
        'exercise_minutes': 10, 'heart_rate': 95,
        'systolic_bp': 140, 'diastolic_bp': 90, 'steps': 2000
    }

    physiological_low_risk = {
        'sleep_hours': 8.0, 'sleep_quality': 5,
        'exercise_minutes': 60, 'heart_rate': 65,
        'systolic_bp': 110, 'diastolic_bp': 70, 'steps': 12000
    }

    print('=== 生理数据及多模态融合对比实验 ===')

    print('\n[实验1] 结构化数据预测:')
    r1 = await engine.predict_structured(structured_features)
    print(f'  risk_score={r1["risk_score"]}, risk_level={r1["risk_level"]}, model={r1["model_used"]}')

    print('\n[实验2] 文本分析预测:')
    r2 = await engine.predict_text(text)
    print(f'  sentiment_score={r2["sentiment_score"]}, sentiment_label={r2["sentiment_label"]}, model={r2["model_used"]}')

    print('\n[实验3a] 生理数据预测 (高风险样本):')
    r3a = await engine._predict_physiological(physiological_high_risk)
    print(f'  physiological_score={r3a}')

    print('\n[实验3b] 生理数据预测 (低风险样本):')
    r3b = await engine._predict_physiological(physiological_low_risk)
    print(f'  physiological_score={r3b}')

    print('\n[实验4] 多模态融合预测 (全部数据 + 高风险生理):')
    r4 = await engine.predict_fusion(structured_features, text, physiological_high_risk)
    print(f'  fused_risk_score={r4["risk_score"]}, risk_level={r4["risk_level"]}, severity={r4["severity"]}')
    print(f'  modality_scores={r4["fusion_detail"]["modality_scores"]}')
    print(f'  weights={r4["fusion_detail"]["weights"]}')
    print(f'  gate_weights={r4["fusion_detail"]["gate_weights"]}')
    print(f'  intervention_level={r4["intervention_level"]}')
    print(f'  intervention_actions={r4["intervention_actions"]}')

    print('\n[实验5] 多模态融合预测 (全部数据 + 低风险生理):')
    r5 = await engine.predict_fusion(structured_features, text, physiological_low_risk)
    print(f'  fused_risk_score={r5["risk_score"]}, risk_level={r5["risk_level"]}, severity={r5["severity"]}')
    print(f'  modality_scores={r5["fusion_detail"]["modality_scores"]}')

    print('\n[实验6] 多模态融合预测 (仅生理数据高风险):')
    r6 = await engine.predict_fusion(None, None, physiological_high_risk)
    print(f'  fused_risk_score={r6["risk_score"]}, risk_level={r6["risk_level"]}')

    print('\n[实验7] 多模态融合预测 (结构化+生理高风险):')
    r7 = await engine.predict_fusion(structured_features, None, physiological_high_risk)
    print(f'  fused_risk_score={r7["risk_score"]}, risk_level={r7["risk_level"]}')

    print('\n=== 对比实验结束 ===')

    metrics = engine.get_metrics_snapshot()
    print(f'\n[性能指标]')
    print(f'  cached_models={metrics["cache_size"]}')
    print(f'  predict_stats={metrics["predict_stats"]}')


if __name__ == '__main__':
    asyncio.run(run_experiment())
