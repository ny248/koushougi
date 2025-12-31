"""ゲームエンジン - 全ルールの統合"""

from typing import Optional
from dataclasses import dataclass
from backend.domain.game_state import GameState, StateSnapshot, create_initial_state
from backend.domain.kifu import Move, Kifu
from backend.domain.piece_registry import get_piece
from . import movement, promotion, victory


@dataclass
class MoveResult:
    """移動結果"""
    success: bool
    captured: Optional[int] = None  # 取った駒
    captured_pos: Optional[tuple[int, int]] = None  # 取った位置
    path_kills: list = None  # 経路上で取った駒 [(pos, id), ...]
    promoted: bool = False  # 成ったか
    promoted_to: Optional[int] = None  # 成り先
    triggered_promotions: list = None  # 連鎖成り
    after_effect: Optional[dict] = None  # 射撃等の効果
    can_shoot: bool = False  # 射撃可能か
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
        # Minimax用の軽量スナップショットスタック
        self._snapshot_stack: list[tuple[StateSnapshot, Optional[dict], Optional[tuple[int, int]]]] = []

    def push_state(self) -> None:
        """現在の状態をスタックに保存（Minimax用）"""
        snapshot = self.state.create_snapshot()
        self._snapshot_stack.append((
            snapshot,
            self._pending_shoot.copy() if self._pending_shoot else None,
            self._pending_promotion,
        ))

    def pop_state(self) -> bool:
        """状態をスタックから復元（Minimax用）

        Returns:
            成功したかどうか
        """
        if not self._snapshot_stack:
            return False

        snapshot, pending_shoot, pending_promotion = self._snapshot_stack.pop()
        self.state.restore_snapshot(snapshot)
        self._pending_shoot = pending_shoot
        self._pending_promotion = pending_promotion
        return True

    def clear_stack(self) -> None:
        """スナップショットスタックをクリア"""
        self._snapshot_stack.clear()

    def undo(self) -> bool:
        """棋譜ベースのUndo（人間用）

        Returns:
            成功したかどうか
        """
        last_move = self.state.kifu.pop()
        if last_move is None:
            return False

        # 成り戻しを元に戻す
        for pos, old_id, new_id in reversed(last_move.demotions):
            self.state.board.set(pos[0], pos[1], old_id, self.state.board.get(pos[0], pos[1])[1])

        # 連鎖成りを元に戻す
        for pos, old_id, new_id in reversed(last_move.chain_promotions):
            player = self.state.board.get(pos[0], pos[1])[1]
            self.state.board.set(pos[0], pos[1], old_id, player)

        # 道連れを元に戻す
        for pos, piece_id in last_move.collateral_kills:
            # 相手プレイヤーの駒として復元
            self.state.board.set(pos[0], pos[1], piece_id, 1 - last_move.player)

        if last_move.move_type == "move":
            # 移動を元に戻す
            from_pos = last_move.from_pos
            to_pos = last_move.to_pos
            piece_id = last_move.piece_id

            # 成りを元に戻す
            if last_move.promoted:
                piece = get_piece(piece_id)
                original_id = piece_id
                # promotes_toの逆引きが必要
                for pid in range(1, 60):
                    try:
                        p = get_piece(pid)
                        if p.promotes_to == piece_id:
                            original_id = pid
                            break
                    except:
                        pass
                piece_id = original_id

            # 駒を元の位置に戻す
            self.state.board.remove(to_pos[0], to_pos[1])
            self.state.board.set(from_pos[0], from_pos[1], piece_id, last_move.player)

            # 取った駒を復元
            if last_move.captured_piece is not None:
                self.state.board.set(to_pos[0], to_pos[1], last_move.captured_piece, 1 - last_move.player)

            # 経路上で取った駒を復元
            for pos, killed_id in last_move.path_kills:
                self.state.board.set(pos[0], pos[1], killed_id, 1 - last_move.player)

        elif last_move.move_type == "shoot":
            # 射撃で取った駒を復元
            if last_move.captured_piece is not None and last_move.captured_pos is not None:
                self.state.board.set(
                    last_move.captured_pos[0], last_move.captured_pos[1],
                    last_move.captured_piece, 1 - last_move.player
                )
            for pos, killed_id in last_move.path_kills:
                self.state.board.set(pos[0], pos[1], killed_id, 1 - last_move.player)

        # 手番を戻す
        self.state.current_player = last_move.player
        self.state.move_count -= 1
        self.state.winner = None

        return True

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

        # 棋譜記録用のMoveを作成
        kifu_move = Move(
            player=player,
            move_type="move",
            from_pos=from_pos,
            to_pos=to_pos,
            piece_id=piece_id,
        )

        # 取る駒を記録
        captured_piece = None
        target = self.state.board.get(to_pos[0], to_pos[1])
        if target:
            captured_piece = target[0]
            kifu_move.captured_piece = captured_piece

        # 移動実行
        move_result = movement.execute_move(self.state, from_pos, to_pos)

        # path_killsは [(pos, id), ...] 形式になった
        kifu_move.path_kills = move_result["path_kills"]

        result = MoveResult(
            success=True,
            captured=move_result["captured"],
            captured_pos=to_pos if move_result["captured"] else None,
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
                        kifu_move.promoted = True

                        # 連鎖成り
                        triggered = promotion.check_triggered_promotions(
                            self.state, new_id, player
                        )
                        result.triggered_promotions = triggered
                        kifu_move.chain_promotions = triggered
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
                    "kifu_move": kifu_move,  # 棋譜記録を保持
                }
                result.can_shoot = True
                # ターン終了しない
                return result

            if "area_kill" in effect:
                # 周囲破壊は自動実行
                killed = movement.execute_area_kill(
                    self.state, to_pos, effect["area_kill"], player
                )
                result.path_kills.extend(killed)
                kifu_move.collateral_kills = killed

        # 成り戻りチェック
        demotions = movement.check_revert_all(self.state)
        kifu_move.demotions = demotions

        # 棋譜に記録
        self.state.kifu.append(kifu_move)

        # 勝敗判定
        winner = victory.check_victory(self.state)
        if winner is not None:
            result.winner = winner
            self.state.kifu.winner = winner
            self.state.kifu.win_reason = "capture"
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
        kifu_move = shoot_info.get("kifu_move")

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

        # 棋譜に射撃情報を追加
        if kifu_move:
            # 移動と射撃を1つのMoveとして記録
            for pos, piece_id in killed:
                kifu_move.path_kills.append((pos, piece_id))

        result = MoveResult(
            success=True,
            path_kills=killed,
        )

        # 成り戻りチェック
        demotions = movement.check_revert_all(self.state)
        if kifu_move:
            kifu_move.demotions = demotions

        # 棋譜に記録
        if kifu_move:
            self.state.kifu.append(kifu_move)

        # 勝敗判定
        winner = victory.check_victory(self.state)
        if winner is not None:
            result.winner = winner
            self.state.kifu.winner = winner
            self.state.kifu.win_reason = "capture"
            return result

        # ターン終了
        movement.end_turn(self.state)

        return result

    def skip_shoot(self) -> MoveResult:
        """射撃をスキップ"""
        return self.shoot([])
