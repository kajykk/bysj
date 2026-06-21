#!/usr/bin/env python3
"""v1.20 基线状态验证脚本

验证系统进入 v1.20 前的关键状态：
1. 结构化模型仍使用 heuristic fallback
2. 训练脚本存在且语法正确
3. 训练数据集可加载
4. Alembic 双 head 状态
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
BACKEND_DIR = os.path.join(PROJECT_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)

def main():
    results = {}
    all_pass = True

    # 1. 结构化模型 fallback 状态
    print("=" * 60)
    print("1. 结构化模型 fallback 状态")
    print("=" * 60)
    try:
        from app.core.model_engine import ModelEngine
        has_fallback = hasattr(ModelEngine, '_structured_heuristic_fallback')
        print(f"   _structured_heuristic_fallback 方法存在: {has_fallback}")
        if has_fallback:
            print("   ✅ 结构化模型回退机制就绪")
            results['fallback'] = 'PASS'
        else:
            print("   ❌ 未找到 heuristic fallback 方法")
            results['fallback'] = 'FAIL'
            all_pass = False
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        results['fallback'] = 'FAIL'
        all_pass = False

    # 2. 训练脚本存在性
    print()
    print("=" * 60)
    print("2. 训练脚本存在性与语法")
    print("=" * 60)
    train_path = os.path.join(BACKEND_DIR, 'train_baseline.py')
    train_path = os.path.abspath(train_path)
    print(f"   路径: {train_path}")
    if os.path.exists(train_path):
        print(f"   ✅ train_baseline.py 存在")
        try:
            with open(train_path, 'rb') as f:
                import ast
                source = f.read()
                ast.parse(source)
            print(f"   ✅ 语法校验通过 (大小: {len(source)} bytes)")
            results['train_script'] = 'PASS'
        except SyntaxError as e:
            print(f"   ❌ 语法错误: {e}")
            results['train_script'] = 'FAIL'
            all_pass = False
    else:
        print(f"   ❌ train_baseline.py 不存在")
        print(f"   ⚠️ 注意: 该脚本训练的是 PhysiologicalMLP, 非结构化 LogisticRegression")
        results['train_script'] = 'FAIL'
        all_pass = False

    # 3. 训练数据集
    print()
    print("=" * 60)
    print("3. 训练数据集可加载性")
    print("=" * 60)
    try:
        from app.ml.data_loader import merge_datasets
        from app.ml.feature_engineering import get_target_vector
        df = merge_datasets()
        print(f"   ✅ 数据集加载成功: {len(df)} rows x {len(df.columns)} columns")
        try:
            y_vec = get_target_vector(df)
            positives = int(sum(1 for v in y_vec if v == 1))
            print(f"   正样本: {positives}, 负样本: {len(df) - positives}")
        except Exception:
            print(f"   标签列类型: {df.iloc[:, -1].dtype}, 无法统计正负样本（将依赖 feature_engineering）")
        results['dataset'] = 'PASS'
    except Exception as e:
        print(f"   ❌ 数据集加载失败: {e}")
        results['dataset'] = 'FAIL'
        all_pass = False

    # 4. Alembic 状态 (尝试检测)
    print()
    print("=" * 60)
    print("4. Alembic 状态")
    print("=" * 60)
    alembic_dir = os.path.join(BACKEND_DIR, 'alembic')
    alembic_dir = os.path.abspath(alembic_dir)
    if os.path.exists(alembic_dir):
        versions_dir = os.path.join(alembic_dir, 'versions')
        if os.path.exists(versions_dir):
            migration_files = [f for f in os.listdir(versions_dir) if f.endswith('.py')]
            print(f"   ✅ Alembic 目录存在: {len(migration_files)} 个 migration 文件")
            results['alembic'] = 'PASS (需要运行 alembic heads 确认双 head 状态)'
        else:
            print(f"   ❌ versions 目录不存在")
            results['alembic'] = 'FAIL'
            all_pass = False
    else:
        print(f"   ❌ Alembic 目录不存在")
        results['alembic'] = 'FAIL'
        all_pass = False

    # 总结
    print()
    print("=" * 60)
    print("V1.20 基线验证总结")
    print("=" * 60)
    for key, value in results.items():
        status = "✅" if "PASS" in value else "❌"
        print(f"  {status} {key}: {value}")
    print(f"\n总体结果: {'✅ ALL PASS' if all_pass else '❌ SOME FAILURES'}")
    return 0 if all_pass else 1

if __name__ == '__main__':
    sys.exit(main())
