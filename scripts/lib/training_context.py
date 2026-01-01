"""訓練進捗管理

進捗情報のみをJSONで永続化する。
計画定義はPythonファイル（training_config.py）で管理。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


PROGRESS_FILENAME = "training_progress.json"


class PhaseProgress(BaseModel):
    """フェーズ内進捗"""

    phase_name: str
    phase_type: str  # "generate", "train", "eval"
    completed_count: int = 0  # 完了した局数/エポック数
    total_count: int = 0  # 目標局数/エポック数


class TrainingProgress(BaseModel):
    """訓練進捗（JSONでシリアライズ）"""

    completed_phases: List[str] = Field(default_factory=list)
    current_phase: Optional[PhaseProgress] = None  # フェーズ内進捗
    variables: Dict[str, Any] = Field(default_factory=dict)
    latest_model: Optional[str] = None
    best_model: Optional[str] = None
    best_win_rate: float = 0.0
    all_game_files: List[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    finished_at: Optional[str] = None


def load_progress(path: Path) -> TrainingProgress:
    """進捗をロード"""
    if path.exists():
        with open(path) as f:
            return TrainingProgress.model_validate(json.load(f))
    return TrainingProgress()


def save_progress(progress: TrainingProgress, path: Path):
    """進捗を保存"""
    progress.updated_at = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(progress.model_dump(), f, indent=2)
