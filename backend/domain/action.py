"""アクション型の定義

AIが返す「次に何をするか」を表す型。
GameEngineの具体的なAPIに依存せず、意図を表現する。
"""

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class SelectPieceAction:
    """駒を選択するアクション（PIECE_SELECTフェーズ）"""
    pos: tuple[int, int]


@dataclass(frozen=True)
class SelectDestinationAction:
    """移動先を選択するアクション（DEST_SELECTフェーズ）"""
    pos: tuple[int, int]


@dataclass(frozen=True)
class StopMoveAction:
    """マルチステップ移動を途中で停止するアクション（MULTI_STEP_MOVEフェーズ）"""
    pass


@dataclass(frozen=True)
class SelectNextStepAction:
    """次のステップ位置を選択するアクション（MULTI_STEP_MOVEフェーズ）"""
    pos: tuple[int, int]


@dataclass(frozen=True)
class DecidePromotionAction:
    """成り判断アクション（PROMOTIONフェーズ）"""
    promote: bool


@dataclass(frozen=True)
class ShootAction:
    """射撃アクション（SHOOTINGフェーズ）"""
    target: tuple[int, int]


@dataclass(frozen=True)
class SkipShootAction:
    """射撃をスキップするアクション（SHOOTINGフェーズ）"""
    pass


# 全アクション型のUnion
Action = Union[
    SelectPieceAction,
    SelectDestinationAction,
    StopMoveAction,
    SelectNextStepAction,
    DecidePromotionAction,
    ShootAction,
    SkipShootAction,
]
