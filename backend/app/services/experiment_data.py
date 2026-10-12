from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

DATA_ROOT = Path(settings.model_dir) / "datasets"
EXPERIMENT_ROOT = Path(settings.model_dir) / "experiments"

SYNTHETIC_DATASET_WARNING = (
    "数据集 {name} 不存在，正在生成**合成演示数据**参与训练/评估——"
    "结果不具备任何临床意义，禁止用于指标上报或上线决策。"
    "本行为需显式传 allow_synthetic=True 才会发生；若为生产路径，"
    "请改为先落盘真实数据集。"
)


class ExperimentDataManager:
    def __init__(self) -> None:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        EXPERIMENT_ROOT.mkdir(parents=True, exist_ok=True)

    def physiological_dataset_path(self, dataset_name: str) -> Path:
        return DATA_ROOT / f"{dataset_name}_physiological.csv"

    def export_dataset_snapshot(self, dataset_name: str) -> dict[str, Any]:
        snapshot = {
            "dataset_name": dataset_name,
            "dataset_path": str(self.dataset_path(dataset_name)),
            "train_path": str(self.train_path(dataset_name)),
            "validation_path": str(self.val_path(dataset_name)),
            "test_path": str(self.test_path(dataset_name)),
        }
        (DATA_ROOT / f"{dataset_name}.snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return snapshot

    def load_physiological_dataset(
        self, dataset_name: str, *, allow_synthetic: bool = False
    ) -> pd.DataFrame:
        """读取生理数据集。

        AUDIT-2026-10-13 (P1-26)：数据集缺失时**不再静默生成合成数据**。
        改前只要文件不存在就自动生成 240 行合成样本并照常训练/评估 ——
        调用方拿到的评估指标看起来完全正常，实际测的是随机数。指标一旦被
        写进报告或用于上线决策，属于实质性的数据造假路径。
        现改为：默认抛 ``FileNotFoundError``（fail-closed）；只有显式传
        ``allow_synthetic=True`` 才生成，并留 warning 日志。
        """
        path = self.physiological_dataset_path(dataset_name)
        if not path.exists():
            if not allow_synthetic:
                raise FileNotFoundError(
                    f"生理数据集 {dataset_name!r} 不存在：{path}。"
                    "拒绝静默生成合成数据（评估结果将不具备临床意义）；"
                    "如确需演示数据，请显式传 allow_synthetic=True。"
                )
            logger.warning(SYNTHETIC_DATASET_WARNING.format(name=dataset_name))
            self._create_demo_physiological_dataset(path)
        df = pd.read_csv(path)
        required = {
            "sleep_hours",
            "sleep_quality",
            "exercise_minutes",
            "heart_rate",
            "systolic_bp",
            "diastolic_bp",
            "steps",
            "label",
        }
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"生理数据集缺少必要列: {', '.join(sorted(missing))}")
        return df

    def dataset_path(self, dataset_name: str) -> Path:
        return DATA_ROOT / f"{dataset_name}.csv"

    def meta_path(self, dataset_name: str) -> Path:
        return DATA_ROOT / f"{dataset_name}.meta.json"

    def train_path(self, dataset_name: str) -> Path:
        return EXPERIMENT_ROOT / f"{dataset_name}_train.csv"

    def val_path(self, dataset_name: str) -> Path:
        return EXPERIMENT_ROOT / f"{dataset_name}_validation.csv"

    def test_path(self, dataset_name: str) -> Path:
        return EXPERIMENT_ROOT / f"{dataset_name}_test.csv"

    def import_dataset(
        self,
        dataset_name: str,
        source_type: str,
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
        *,
        allow_synthetic: bool = False,
    ) -> dict[str, Any]:
        """导入并划分数据集。

        AUDIT-2026-10-13 (P1-26)：同 ``load_physiological_dataset``，数据集缺失
        时默认抛 ``FileNotFoundError`` 而非静默生成合成数据。训练任务
        （``tasks/model_training.py``）因此会在缺数据集时**显式失败**，而不是
        训练出一个基于合成数据的模型并把它标记为成功。
        """
        from sklearn.model_selection import train_test_split

        csv_path = self.dataset_path(dataset_name)
        if not csv_path.exists():
            if not allow_synthetic:
                raise FileNotFoundError(
                    f"数据集 {dataset_name!r} 不存在：{csv_path}。"
                    "拒绝静默生成合成数据；如确需演示数据，请显式传 "
                    "allow_synthetic=True。"
                )
            logger.warning(SYNTHETIC_DATASET_WARNING.format(name=dataset_name))
            self._create_demo_dataset(csv_path)

        df = pd.read_csv(csv_path)
        if "label" not in df.columns:
            raise ValueError("数据集必须包含 label 列")

        normalized_source_type = (source_type or "").strip().lower()
        if (
            normalized_source_type in {"bert", "text", "nlp"}
            and "text" not in df.columns
        ):
            raise ValueError("文本类训练数据集必须包含 text 列")

        ratios = train_ratio + val_ratio + test_ratio
        if abs(ratios - 1.0) > 1e-6:
            raise ValueError("train_ratio + val_ratio + test_ratio 必须等于 1")
        if min(train_ratio, val_ratio, test_ratio) <= 0:
            raise ValueError("train_ratio、val_ratio 和 test_ratio 必须都大于 0")
        if len(df) < 3:
            raise ValueError("数据集样本量太少，至少需要 3 条记录")

        label_counts = df["label"].value_counts()
        # M-Svc-3 修复：stratify 前检查每类至少 2 样本，不足时抛 ValueError
        # 避免静默禁用分层抽样导致训练/验证/测试集类别分布不一致
        if label_counts.min() < 2:
            raise ValueError(
                f"分层抽样需要每个类别至少 2 个样本，当前最小类别样本数为 {int(label_counts.min())}"
            )
        stratify = df["label"]
        train_df, temp_df = train_test_split(
            df,
            test_size=(1 - train_ratio),
            random_state=42,
            shuffle=True,
            stratify=stratify,
        )
        # M-Svc-3 修复：二分划分后同样校验 temp_df 每类至少 2 样本
        temp_label_counts = temp_df["label"].value_counts()
        if temp_label_counts.min() < 2:
            raise ValueError(
                f"二分划分后分层抽样需要每个类别至少 2 个样本，当前最小类别样本数为 {int(temp_label_counts.min())}"
            )
        temp_stratify = temp_df["label"]
        val_test_total = val_ratio + test_ratio
        if val_test_total <= 0:
            raise ValueError("val_ratio + test_ratio 必须大于 0")
        val_size = val_ratio / val_test_total
        val_df, test_df = train_test_split(
            temp_df,
            test_size=(1 - val_size),
            random_state=42,
            shuffle=True,
            stratify=temp_stratify,
        )

        if train_df.empty or val_df.empty or test_df.empty:
            raise ValueError("数据集划分后存在空集，请调整划分比例或样本量")

        train_df.to_csv(self.train_path(dataset_name), index=False)
        val_df.to_csv(self.val_path(dataset_name), index=False)
        test_df.to_csv(self.test_path(dataset_name), index=False)

        meta = {
            "dataset_name": dataset_name,
            "source_type": source_type,
            "columns": list(df.columns),
            "train_ratio": train_ratio,
            "val_ratio": val_ratio,
            "test_ratio": test_ratio,
            "total_samples": int(len(df)),
            "label_distribution": {
                str(k): int(v) for k, v in label_counts.to_dict().items()
            },
        }
        self.meta_path(dataset_name).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "dataset_name": dataset_name,
            "source_type": source_type,
            "total_samples": int(len(df)),
            "splits": {
                "train": int(len(train_df)),
                "validation": int(len(val_df)),
                "test": int(len(test_df)),
            },
            "message": "数据集导入并完成划分",
        }

    def _create_demo_dataset(self, csv_path: Path) -> None:
        rows: list[dict[str, Any]] = []
        texts = [
            "最近总是失眠，感觉压力很大",
            "今天状态一般，但还能正常学习",
            "持续心情低落，对事情没有兴趣",
            "和朋友聊天后感觉好多了",
            "经常感到焦虑和疲惫",
        ]
        for i in range(240):
            text = texts[i % len(texts)]
            rows.append(
                {
                    "text": text,
                    "age": 18 + (i % 8),
                    "stress_level": i % 6,
                    "sleep_duration": round(4.0 + ((i % 50) / 10.0), 1),
                    "social_support": i % 6,
                    "label": 1 if i % 3 == 0 else 0,
                }
            )
        pd.DataFrame(rows).to_csv(csv_path, index=False)

    def _create_demo_physiological_dataset(self, csv_path: Path) -> None:
        rows: list[dict[str, Any]] = []
        for i in range(240):
            rows.append(
                {
                    "sleep_hours": round(4.0 + ((i % 60) / 12.0), 1),
                    "sleep_quality": (i % 5) + 1,
                    "exercise_minutes": (i * 7) % 91,
                    "heart_rate": 58 + (i % 53),
                    "systolic_bp": 105 + (i % 46),
                    "diastolic_bp": 65 + (i % 34),
                    "steps": 1000 + ((i * 137) % 11000),
                    "label": 1 if i % 4 == 0 else 0,
                }
            )
        pd.DataFrame(rows).to_csv(csv_path, index=False)
