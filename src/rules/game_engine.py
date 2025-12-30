"""ゲームエンジン - 全ルールの統合"""

from typing import Optional
from dataclasses import dataclass
from src.domain.game_state import GameState, create_initial_state
from src.domain.piece_registry import get_piece
from . import movement, promotion, victory


@dataclass
class MoveResult:
    """移動結果"""
    success: bool
    captured: Optional[int] = None  # 取った駒
    path_kills: list[int] = None  # 経路上で取った駒
    promoted: bool = False  # 成ったか
    promoted_to: Optional[int] = None  # 成り先
    triggered_promotions: list = None  # 連鎖成り
    after_effect: Optional[dict] = None  # 射撃等の効果
    winner: Optional[int] = None  # 勝者
    error: Optional[str] = None  # エラーメッセージ

    def __post_init__(self):
        if self.path_kills is None:
            self.path_kills = []
        if self.triggered_promotions is None:
            self.triggered_promotions = []


class GameEngine:
    """ゲームエンジン"""

    def __init__(self, state: Optional[GameState] = None):
        self.state = state or create_initial_state()
        self._pending_shoot: Optional[dict] = None  # 射撃待ち状態
        self._pending_promotion: Optional[tuple[int, int]] = None  # 成り待ち状態

    @property
    def current_player(self) -> int:
        return self.state.current_player

    @property
    def is_game_over(self) -> bool:
        return victory.is_game_over(self.state)

    @property
    def winner(self) -> Optional[int]:
        return self.state.winner

    def get_legal_moves(self, pos: tuple[int, int]) -> list[tuple[int, int]]:
        """合法手を取得"""
        return movement.get_legal_moves(self.state, pos)

    def move(self, from_pos: tuple[int, int], to_pos: tuple[int, int],
             promote: bool = False) -> MoveResult:
        """駒を移動

        Args:
            from_pos: 移動元
            to_pos: 移動先
            promote: 成るかどうか

        Returns:
            移動結果
        """
        # 射撃待ちの場合はエラー
        if self._pending_shoot:
            return MoveResult(success=False, error="射撃先を選択してください")

        # ゲーム終了チェック
        if self.is_game_over:
            return MoveResult(success=False, error="ゲームは終了しています")

        # 駒の確認
        piece_data = self.state.board.get(from_pos[0], from_pos[1])
        if piece_data is None:
            return MoveResult(success=False, error="駒がありません")

        piece_id, player = piece_data
        if player != self.current_player:
            return MoveResult(success=False, error="相手の駒は動かせません")

        # 合法手チェック
        legal_moves = self.get_legal_moves(from_pos)
        if to_pos not in legal_moves:
            return MoveResult(success=False, error="そこには移動できません")

        # 取る駒を記録
        captured_piece = None
        target = self.state.board.get(to_pos[0], to_pos[1])
        if target:
            captured_piece = target[0]

        # 移動実行
        move_result = movement.execute_move(self.state, from_pos, to_pos)

        result = MoveResult(
            success=True,
            captured=move_result["captured"],
            path_kills=move_result["path_kills"],
            after_effect=move_result["after_effect"],
        )

        # 成り判定
        piece = get_piece(piece_id)
        if piece.promotes_to is not None:
            can_promote = promotion.can_promote(
                self.state, from_pos, to_pos, captured_piece, player
            )
            if can_promote:
                if promote:
                    new_id = promotion.execute_promotion(self.state, to_pos)
                    if new_id:
                        result.promoted = True
                        result.promoted_to = new_id

                        # 連鎖成り
                        triggered = promotion.check_triggered_promotions(
                            self.state, new_id, player
                        )
                        result.triggered_promotions = triggered
                else:
                    # 成り待ち状態（オプション）
                    self._pending_promotion = to_pos

        # 移動後効果
        if move_result["after_effect"]:
            effect = move_result["after_effect"]
            if "shoot" in effect:
                # 射撃待ち状態
                self._pending_shoot = {
                    "pos": to_pos,
                    "targets": effect["shoot"]["targets"],
                    "count": effect["shoot"]["count"],
                    "selected": [],
                }
                # ターン終了しない
                return result

            if "area_kill" in effect:
                # 周囲破壊は自動実行
                killed = movement.execute_area_kill(
                    self.state, to_pos, effect["area_kill"], player
                )
                result.path_kills.extend(killed)

        # 成り戻りチェック
        movement.check_revert_all(self.state)

        # 勝敗判定
        winner = victory.check_victory(self.state)
        if winner is not None:
            result.winner = winner
            return result

        # ターン終了
        movement.end_turn(self.state)

        return result

    def get_shoot_targets(self) -> Optional[list[tuple[int, int]]]:
        """射撃可能な対象を取得"""
        if self._pending_shoot:
            return self._pending_shoot["targets"]
        return None

    def shoot(self, targets: list[tuple[int, int]]) -> MoveResult:
        """射撃を実行

        Args:
            targets: 射撃対象の位置リスト

        Returns:
            結果
        """
        if not self._pending_shoot:
            return MoveResult(success=False, error="射撃待ちではありません")

        shoot_info = self._pending_shoot
        count = shoot_info["count"]
        valid_targets = shoot_info["targets"]

        # 対象数チェック
        if len(targets) > count:
            return MoveResult(success=False, error=f"射撃は{count}体までです")

        # 有効な対象かチェック
        for t in targets:
            if t not in valid_targets:
                return MoveResult(success=False, error=f"{t}は射撃対象外です")

        # 射撃実行
        player = self.current_player
        killed = movement.execute_shoot(self.state, shoot_info["pos"], targets, player)

        self._pending_shoot = None

        result = MoveResult(
            success=True,
            path_kills=killed,
        )

        # 成り戻りチェック
        movement.check_revert_all(self.state)

        # 勝敗判定
        winner = victory.check_victory(self.state)
        if winner is not None:
            result.winner = winner
            return result

        # ターン終了
        movement.end_turn(self.state)

        return result

    def skip_shoot(self) -> MoveResult:
        """射撃をスキップ"""
        return self.shoot([])
