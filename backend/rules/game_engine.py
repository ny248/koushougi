"""ゲームエンジン - サービスとして状態遷移を計算

設計原則:
- GameEngineはサービス（状態を持たない）
- GameStateを受け取り、新しいGameStateを返す
- 状態を変更せず、コピーして変更した新しい状態を返す
"""

import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from backend.domain.game_state import GameState, GamePhase, create_initial_state
from backend.domain.kifu import Move, Kifu, KifuMode, KifuWriter
from backend.domain.piece_registry import get_piece
from backend.domain.pieces.utils import shoot_targets
from . import movement, promotion, victory

logger = logging.getLogger('GameEngine')

# 後方互換性のためGamePhaseを再エクスポート
__all__ = ['GameEngine', 'GamePhase', 'MoveResult']


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
    step_completed: bool = False  # マルチステップ移動完了か

    def __post_init__(self):
        if self.path_kills is None:
            self.path_kills = []
        if self.triggered_promotions is None:
            self.triggered_promotions = []


class GameEngine:
    """ゲームエンジン - サービス + ラッパー

    設計原則:
    - GameStateが全ての状態を保持
    - GameEngineはGameStateを操作するサービス
    - 後方互換性のためインスタンスメソッドも維持
    - 内部状態は全てself.stateに移譲
    """

    def __init__(self, state: Optional[GameState] = None,
                 kifu_mode: KifuMode = KifuMode.NONE,
                 kifu_path: Optional[str] = None):
        self.state = state or create_initial_state()
        # フェーズ関連の状態はGameStateに移動済み
        # _pending_move_resultは一時的な計算結果なのでここに残す
        self._pending_move_result: Optional[MoveResult] = None
        self._kifu_move: Optional[Move] = None  # 棋譜記録用

        # 棋譜保存
        self._kifu_mode = kifu_mode
        self._kifu_path = kifu_path
        self._kifu_writer: Optional[KifuWriter] = None
        if kifu_mode == KifuMode.STREAMING and kifu_path:
            self._kifu_writer = KifuWriter(kifu_path)
            self._kifu_writer.start()

    # ===================
    # プロパティ（GameStateへの委譲）
    # ===================

    @property
    def phase(self) -> GamePhase:
        """現在のフェーズ"""
        if self.is_game_over:
            return GamePhase.GAME_OVER
        return self.state.phase

    @property
    def current_player(self) -> int:
        return self.state.current_player

    @property
    def is_game_over(self) -> bool:
        return victory.is_game_over(self.state)

    @property
    def winner(self) -> Optional[int]:
        return self.state.winner

    @property
    def selected_piece(self) -> Optional[tuple[int, int]]:
        """選択中の駒位置"""
        return self.state.selected_piece

    # ===================
    # フェーズ1: 駒選択
    # ===================

    def get_movable_pieces(self) -> list[tuple[int, int]]:
        """動かせる駒の位置リスト"""
        pieces = []
        player = self.current_player
        for x in range(19):
            for y in range(19):
                piece_data = self.state.board.get(x, y)
                if piece_data and piece_data[1] == player:
                    # 合法手があるか確認
                    moves = movement.get_legal_moves(self.state, (x, y))
                    if moves:
                        pieces.append((x, y))
        return pieces

    def select_piece(self, pos: tuple[int, int]) -> bool:
        """駒を選択

        Returns:
            成功したかどうか
        """
        if self.state.phase != GamePhase.PIECE_SELECT:
            return False

        piece_data = self.state.board.get(pos[0], pos[1])
        if piece_data is None:
            return False

        piece_id, player = piece_data
        if player != self.current_player:
            return False

        # 合法手があるか確認
        moves = movement.get_legal_moves(self.state, pos)
        if not moves:
            return False

        # 棋譜に記録
        select_move = Move(
            player=player,
            move_type="select",
            from_pos=pos,
            piece_id=piece_id,
        )
        self._record_move(select_move)

        self.state.selected_piece = pos
        self.state.phase = GamePhase.DEST_SELECT
        return True

    def cancel_piece_selection(self) -> bool:
        """駒選択をキャンセル"""
        if self.state.phase != GamePhase.DEST_SELECT:
            return False

        self.state.selected_piece = None
        self.state.phase = GamePhase.PIECE_SELECT
        return True

    # ===================
    # フェーズ2: 移動先選択
    # ===================

    def get_legal_destinations(self) -> list[tuple[int, int]]:
        """選択中の駒の合法移動先"""
        if self.state.selected_piece is None:
            return []
        return movement.get_legal_moves(self.state, self.state.selected_piece)

    def select_destination(self, to_pos: tuple[int, int]) -> MoveResult:
        """移動先を選択して移動実行

        マルチステップ駒の場合は1歩目として扱い、MULTI_STEP_MOVEフェーズに遷移。
        通常駒の場合は従来通り移動完了。

        Returns:
            移動結果
        """
        if self.state.phase != GamePhase.DEST_SELECT:
            return MoveResult(success=False, error="移動先選択フェーズではありません")

        if self.state.selected_piece is None:
            return MoveResult(success=False, error="駒が選択されていません")

        from_pos = self.state.selected_piece

        # 駒情報取得
        piece_data = self.state.board.get(from_pos[0], from_pos[1])
        piece_id, player = piece_data
        piece = get_piece(piece_id)

        # マルチステップ駒かどうか
        if piece.is_multi_step():
            return self._handle_first_step(from_pos, to_pos, piece_id, player)
        else:
            return self._handle_normal_move(from_pos, to_pos, piece_id, player)

    def _handle_first_step(self, from_pos: tuple[int, int], to_pos: tuple[int, int],
                           piece_id: int, player: int) -> MoveResult:
        """マルチステップ駒の1歩目を処理"""
        piece = get_piece(piece_id)
        config = piece.get_multi_step_config()

        # 1歩目の候補を取得
        first_step_options = piece.get_next_step_options(
            from_pos, self.state.board, player, 0, None
        )
        if to_pos not in first_step_options:
            return MoveResult(success=False, error="そこには移動できません")

        # 方向を計算
        dx = to_pos[0] - from_pos[0]
        dy = to_pos[1] - from_pos[1]
        first_direction = (dx, dy)

        # 棋譜記録用のMoveを作成（1歩目）
        self._kifu_move = Move(
            player=player,
            move_type="step",
            from_pos=from_pos,
            to_pos=to_pos,
            piece_id=piece_id,
        )

        # 経路上の敵駒を取る（経路取りがある駒の場合）
        path_kills = []
        target = self.state.board.get(to_pos[0], to_pos[1])
        if target and target[1] != player:
            killed_id = target[0]
            killed_was_promoted = self.state.board.get_promoted(to_pos[0], to_pos[1])
            path_kills.append((to_pos, killed_id, killed_was_promoted))
            self.state.board.remove(to_pos[0], to_pos[1])

        # 駒を移動
        already_promoted = self.state.board.get_promoted(from_pos[0], from_pos[1])
        self.state.board.remove(from_pos[0], from_pos[1])
        self.state.board.set(to_pos[0], to_pos[1], piece_id, player, is_promoted=already_promoted)

        # 棋譜に経路取りを記録
        if path_kills:
            self._kifu_move.captured_piece = path_kills[0][1]
            self._kifu_move.captured_pos = path_kills[0][0]
            self._kifu_move.captured_was_promoted = path_kills[0][2]

        # 棋譜を記録
        self._record_move(self._kifu_move)
        self._kifu_move = None

        # マルチステップ状態を初期化
        self.state.multi_step_state = {
            "original_pos": from_pos,
            "current_pos": to_pos,
            "remaining_steps": config.total_steps - 1,
            "step_history": [from_pos, to_pos],
            "first_direction": first_direction,
            "can_stop_early": config.can_stop_early,
            "piece_id": piece_id,
            "already_promoted": already_promoted,
        }

        self.state.selected_piece = None

        # 残りステップがあればMULTI_STEP_MOVEフェーズへ
        if self.state.multi_step_state["remaining_steps"] > 0:
            self.state.phase = GamePhase.MULTI_STEP_MOVE
            return MoveResult(
                success=True,
                path_kills=path_kills,
                step_completed=False,
            )
        else:
            # 1歩のみの場合（ありえないが念のため）
            return self._complete_multi_step_move()

    def _handle_normal_move(self, from_pos: tuple[int, int], to_pos: tuple[int, int],
                            piece_id: int, player: int) -> MoveResult:
        """通常駒の移動を処理（従来のロジック）"""
        # 合法手チェック
        legal_moves = self.get_legal_destinations()
        if to_pos not in legal_moves:
            return MoveResult(success=False, error="そこには移動できません")

        already_promoted = self.state.board.get_promoted(from_pos[0], from_pos[1])

        # 棋譜記録用のMoveを作成
        self._kifu_move = Move(
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
            self._kifu_move.captured_piece = captured_piece
            self._kifu_move.captured_was_promoted = self.state.board.get_promoted(to_pos[0], to_pos[1])

        # 移動実行
        move_result = movement.execute_move(self.state, from_pos, to_pos)

        result = MoveResult(
            success=True,
            captured=move_result["captured"],
            captured_pos=to_pos if move_result["captured"] else None,
            path_kills=move_result["path_kills"],
            after_effect=move_result["after_effect"],
            step_completed=True,
        )

        self._pending_move_result = result
        self.state.selected_piece = None

        # 成り判定（すでに成っている駒は成れない）
        piece = get_piece(piece_id)
        if piece.promotes_to is not None and not already_promoted:
            can_promote = promotion.can_promote(
                self.state, from_pos, to_pos, captured_piece, player
            )
            if can_promote:
                # PROMOTIONフェーズに入る前に棋譜を記録（1状態遷移=1棋譜エントリ）
                self._record_move(self._kifu_move)
                self.state.phase = GamePhase.PROMOTION
                return result

        # 成れない場合は射撃/ターン終了へ
        return self._after_promotion_check(result, to_pos)

    # ===================
    # フェーズ2.5: マルチステップ移動
    # ===================

    def get_next_step_options(self) -> list[tuple[int, int]]:
        """次ステップの移動先候補を取得"""
        if self.state.phase != GamePhase.MULTI_STEP_MOVE or self.state.multi_step_state is None:
            return []

        ms_state = self.state.multi_step_state
        piece = get_piece(ms_state["piece_id"])
        step_index = piece.get_multi_step_config().total_steps - ms_state["remaining_steps"]

        return piece.get_next_step_options(
            ms_state["current_pos"],
            self.state.board,
            self.current_player,
            step_index,
            ms_state["first_direction"]
        )

    def get_remaining_steps(self) -> int:
        """残りステップ数を取得"""
        if self.state.multi_step_state is None:
            return 0
        return self.state.multi_step_state["remaining_steps"]

    def can_stop_now(self) -> bool:
        """今停止可能か"""
        if self.state.phase != GamePhase.MULTI_STEP_MOVE or self.state.multi_step_state is None:
            return False
        return self.state.multi_step_state["can_stop_early"]

    def get_multi_step_state(self) -> Optional[dict]:
        """マルチステップ状態を取得（AI訓練用）"""
        return self.state.multi_step_state

    def select_next_step(self, to_pos: tuple[int, int]) -> MoveResult:
        """次のステップを選択

        Args:
            to_pos: 次の位置

        Returns:
            移動結果
        """
        if self.state.phase != GamePhase.MULTI_STEP_MOVE:
            return MoveResult(success=False, error="マルチステップ移動中ではありません")

        if self.state.multi_step_state is None:
            return MoveResult(success=False, error="マルチステップ状態がありません")

        ms_state = self.state.multi_step_state
        next_options = self.get_next_step_options()

        if to_pos not in next_options:
            return MoveResult(success=False, error="そこには移動できません")

        from_pos = ms_state["current_pos"]
        piece_id = ms_state["piece_id"]
        player = self.current_player

        # 棋譜記録用のMoveを作成
        kifu_move = Move(
            player=player,
            move_type="step",
            from_pos=from_pos,
            to_pos=to_pos,
            piece_id=piece_id,
        )

        # 経路上の敵駒を取る
        path_kills = []
        target = self.state.board.get(to_pos[0], to_pos[1])
        if target and target[1] != player:
            killed_id = target[0]
            killed_was_promoted = self.state.board.get_promoted(to_pos[0], to_pos[1])
            path_kills.append((to_pos, killed_id, killed_was_promoted))
            self.state.board.remove(to_pos[0], to_pos[1])
            kifu_move.captured_piece = killed_id
            kifu_move.captured_pos = to_pos
            kifu_move.captured_was_promoted = killed_was_promoted

        # 駒を移動
        self.state.board.remove(from_pos[0], from_pos[1])
        self.state.board.set(to_pos[0], to_pos[1], piece_id, player,
                             is_promoted=ms_state["already_promoted"])

        # 棋譜を記録
        self._record_move(kifu_move)

        # 状態を更新
        ms_state["current_pos"] = to_pos
        ms_state["remaining_steps"] -= 1
        ms_state["step_history"].append(to_pos)

        # 残りステップがあれば継続
        if ms_state["remaining_steps"] > 0:
            return MoveResult(
                success=True,
                path_kills=path_kills,
                step_completed=False,
            )

        # 全ステップ完了
        return self._complete_multi_step_move()

    def stop_move(self) -> MoveResult:
        """マルチステップ移動を早期停止"""
        if self.state.phase != GamePhase.MULTI_STEP_MOVE:
            return MoveResult(success=False, error="マルチステップ移動中ではありません")

        if self.state.multi_step_state is None:
            return MoveResult(success=False, error="マルチステップ状態がありません")

        if not self.state.multi_step_state["can_stop_early"]:
            return MoveResult(success=False, error="この駒は途中で止まれません")

        # 停止を棋譜に記録（undo用にマルチステップ状態を保存）
        ms_state = self.state.multi_step_state
        kifu_move = Move(
            player=self.current_player,
            move_type="stop",
            from_pos=ms_state["current_pos"],
            to_pos=ms_state["current_pos"],
            piece_id=ms_state["piece_id"],
            multi_step_state=ms_state.copy(),  # undo用に状態を保存
        )
        self._record_move(kifu_move)

        return self._complete_multi_step_move()

    def cancel_multi_step(self) -> MoveResult:
        """マルチステップ移動をキャンセル（元の位置に戻る）"""
        if self.state.phase != GamePhase.MULTI_STEP_MOVE:
            return MoveResult(success=False, error="マルチステップ移動中ではありません")

        if self.state.multi_step_state is None:
            return MoveResult(success=False, error="マルチステップ状態がありません")

        ms_state = self.state.multi_step_state
        original_pos = ms_state["original_pos"]
        current_pos = ms_state["current_pos"]
        piece_id = ms_state["piece_id"]
        player = self.current_player

        # 駒を元の位置に戻す
        self.state.board.remove(current_pos[0], current_pos[1])
        self.state.board.set(original_pos[0], original_pos[1], piece_id, player,
                             is_promoted=ms_state["already_promoted"])

        # 棋譜からステップを削除し、取った駒を復元
        steps_taken = len(ms_state["step_history"]) - 1  # 元の位置を除く
        for _ in range(steps_taken):
            step_move = self.state.kifu.pop()
            # 各stepで取った駒を復元
            if step_move and step_move.captured_piece is not None:
                cap_pos = step_move.to_pos  # stepでは移動先に取った駒がいた
                self.state.board.set(
                    cap_pos[0], cap_pos[1],
                    step_move.captured_piece, 1 - player,
                    is_promoted=step_move.captured_was_promoted
                )

        # 状態をリセット
        self.state.multi_step_state = None
        self.state.phase = GamePhase.PIECE_SELECT

        return MoveResult(success=True)

    def _complete_multi_step_move(self) -> MoveResult:
        """マルチステップ移動を完了"""
        ms_state = self.state.multi_step_state
        to_pos = ms_state["current_pos"]
        original_pos = ms_state["original_pos"]
        piece_id = ms_state["piece_id"]
        player = self.current_player

        piece = get_piece(piece_id)

        # 棋譜から経路上で取った駒を取得（成り判定用）
        steps_taken = len(ms_state["step_history"]) - 1
        captured_piece = None
        for i in range(steps_taken):
            idx = len(self.state.kifu) - steps_taken + i
            if idx >= 0 and idx < len(self.state.kifu):
                step_move = self.state.kifu[idx]
                if step_move.captured_piece is not None:
                    captured_piece = step_move.captured_piece  # 最後に取った駒を記録

        already_promoted = ms_state["already_promoted"]
        self.state.multi_step_state = None

        # 移動後効果を取得
        after_effect = None
        if hasattr(piece._module, "after_move"):
            after_effect = piece._module.after_move(
                self.state, original_pos, to_pos, player
            )

        result = MoveResult(
            success=True,
            after_effect=after_effect,
            step_completed=True,
        )

        self._pending_move_result = result

        # 成り判定（すでに成っている駒は成れない）
        if piece.promotes_to is not None and not already_promoted:
            can_promote = promotion.can_promote(
                self.state, original_pos, to_pos, captured_piece, player
            )
            if can_promote:
                self.state.phase = GamePhase.PROMOTION
                return result

        # 成れない場合は射撃/ターン終了へ
        return self._after_promotion_check(result, to_pos)

    # ===================
    # フェーズ3: 成り判断
    # ===================

    def can_promote_now(self) -> bool:
        """現在成り判断待ちか"""
        return self.state.phase == GamePhase.PROMOTION

    def decide_promotion(self, promote: bool) -> MoveResult:
        """成り判断

        Args:
            promote: 成るかどうか

        Returns:
            結果
        """
        if self.state.phase != GamePhase.PROMOTION:
            return MoveResult(success=False, error="成り判断フェーズではありません")

        if self._kifu_move is None:
            return MoveResult(success=False, error="移動情報がありません")

        result = self._pending_move_result or MoveResult(success=True)
        to_pos = self._kifu_move.to_pos
        player = self._kifu_move.player

        # 成り判断を棋譜に記録（1状態遷移=1棋譜エントリ）
        promo_move = Move(
            player=player,
            move_type="promote",
            from_pos=to_pos,
            piece_id=self._kifu_move.piece_id,
            promoted=promote,
        )

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
                promo_move.chain_promotions = triggered

        self._record_move(promo_move)
        self._kifu_move = None  # 移動の棋譜はすでに記録済み

        return self._after_promotion_check(result, to_pos)

    def _after_promotion_check(self, result: MoveResult, to_pos: tuple[int, int]) -> MoveResult:
        """成り判断後の処理（射撃/ターン終了）"""
        move_result_dict = {
            "after_effect": result.after_effect
        }

        # 移動後効果
        if result.after_effect:
            effect = result.after_effect
            if "shoot" in effect:
                # SHOOTINGフェーズに入る前に棋譜を記録（1状態遷移=1棋譜エントリ）
                if self._kifu_move:
                    self._record_move(self._kifu_move)
                    self._kifu_move = None

                # 射撃待ち状態
                shoot_count = effect["shoot"]["count"]
                self.state.pending_shoot = {
                    "pos": to_pos,
                    "targets": effect["shoot"]["targets"],
                    "count": shoot_count,
                    "remaining": shoot_count,  # 残り射撃回数
                    "params": effect["shoot"].get("params"),  # 再計算用パラメータ
                }
                result.can_shoot = True
                self.state.phase = GamePhase.SHOOTING
                return result

            if "area_kill" in effect:
                # 周囲破壊は自動実行
                player = self._kifu_move.player if self._kifu_move else self.current_player
                killed = movement.execute_area_kill(
                    self.state, effect["area_kill"], player
                )
                result.path_kills.extend(killed)
                if self._kifu_move:
                    self._kifu_move.collateral_kills = killed

        # ターン終了処理
        return self._finalize_turn(result)

    # ===================
    # フェーズ4: 射撃
    # ===================

    def get_shoot_targets(self) -> list[tuple[int, int]]:
        """射撃可能な対象を取得"""
        if self.state.pending_shoot:
            return self.state.pending_shoot["targets"]
        return []

    def get_remaining_shoot_count(self) -> int:
        """残り射撃回数を取得"""
        if self.state.pending_shoot:
            return self.state.pending_shoot.get("remaining", 0)
        return 0

    def shoot(self, target: tuple[int, int]) -> MoveResult:
        """射撃を実行（1体）

        Args:
            target: 射撃対象の位置

        Returns:
            結果
        """
        if self.state.phase != GamePhase.SHOOTING:
            return MoveResult(success=False, error="射撃フェーズではありません")

        if not self.state.pending_shoot:
            return MoveResult(success=False, error="射撃待ちではありません")

        shoot_info = self.state.pending_shoot
        valid_targets = shoot_info["targets"]

        if target not in valid_targets:
            return MoveResult(success=False, error=f"{target}は射撃対象外です")

        # 射撃実行
        player = self.current_player
        killed = movement.execute_shoot(self.state, [target], player)

        # 射撃を棋譜に記録
        kifu_move = Move(
            player=player,
            move_type="shoot",
            from_pos=shoot_info["pos"],
            to_pos=target,
            captured_piece=killed[0][1] if killed else None,
            captured_pos=killed[0][0] if killed else None,
            captured_was_promoted=killed[0][2] if killed else False,
            shoot_state=shoot_info.copy(),  # undo用に状態を保存
        )
        self._record_move(kifu_move)

        # 残り回数を減らす
        shoot_info["remaining"] -= 1

        result = MoveResult(
            success=True,
            path_kills=killed,
        )

        # まだ射撃回数が残っている場合はターゲットを再計算
        if shoot_info["remaining"] > 0:
            params = shoot_info.get("params")
            if params:
                # パラメータがある場合は再計算
                new_targets = shoot_targets(
                    shoot_info["pos"],
                    self.state.board,
                    player,
                    shoot_range=params.get("shoot_range", 1),
                    penetrate=params.get("penetrate", False),
                    penetrate_block=params.get("penetrate_block"),
                    immune=params.get("immune"),
                    min_range=params.get("min_range"),
                )
                shoot_info["targets"] = new_targets
            else:
                # 後方互換: パラメータがない場合は撃った駒を除外するだけ
                shoot_info["targets"] = [t for t in shoot_info["targets"] if t != target]

            if shoot_info["targets"]:
                result.can_shoot = True
                return result

        # 射撃終了
        self.state.pending_shoot = None
        return self._finalize_turn(result)

    def skip_shoot(self) -> MoveResult:
        """射撃をスキップ"""
        if self.state.phase != GamePhase.SHOOTING:
            return MoveResult(success=False, error="射撃フェーズではありません")

        # 射撃スキップを棋譜に記録（undo用に射撃状態を保存）
        if self.state.pending_shoot:
            kifu_move = Move(
                player=self.current_player,
                move_type="skip_shoot",
                from_pos=self.state.pending_shoot["pos"],
                shoot_state=self.state.pending_shoot.copy(),  # undo用に状態を保存
            )
            self._record_move(kifu_move)

        self.state.pending_shoot = None
        result = MoveResult(success=True)
        return self._finalize_turn(result)

    # ===================
    # ターン終了処理
    # ===================

    def _finalize_turn(self, result: MoveResult) -> MoveResult:
        """ターン終了処理"""
        before_player = self.current_player
        logger.debug(f"_finalize_turn開始: player={before_player}")

        # 成り戻りチェック
        demotions = movement.check_revert_all(self.state)
        if self._kifu_move:
            self._kifu_move.demotions = demotions

        # 棋譜に記録
        if self._kifu_move:
            self._record_move(self._kifu_move)
            self._kifu_move = None

        # 勝敗判定
        winner = victory.check_victory(self.state)
        if winner is not None:
            result.winner = winner
            self.state.kifu.winner = winner
            self.state.kifu.win_reason = "capture"
            self.state.phase = GamePhase.GAME_OVER
            logger.debug(f"_finalize_turn: ゲーム終了 winner={winner}")
            return result

        # ターン終了
        movement.end_turn(self.state)
        self.state.phase = GamePhase.PIECE_SELECT
        self._pending_move_result = None

        logger.debug(f"_finalize_turn終了: {before_player} -> {self.current_player}")
        return result

    # ===================
    # Undo
    # ===================

    def undo(self) -> bool:
        """棋譜ベースのUndo

        各move_typeに対応:
        - "move": 通常移動（マルチステップの1歩目を含む）を戻す
        - "step": マルチステップの2歩目以降を戻す
        - "stop": マルチステップの早期停止を取り消し、MULTI_STEP_MOVEに戻る
        - "shoot": 射撃を戻す
        - "skip_shoot": 射撃スキップを取り消し、SHOOTINGに戻る
        """
        last_move = self.state.kifu.pop()
        if last_move is None:
            return False

        # 共通の副作用を元に戻す
        self._undo_side_effects(last_move)

        if last_move.move_type == "select":
            self._undo_select(last_move)

        elif last_move.move_type == "move":
            self._undo_move(last_move)

        elif last_move.move_type == "step":
            self._undo_step(last_move)

        elif last_move.move_type == "stop":
            self._undo_stop(last_move)

        elif last_move.move_type == "promote":
            self._undo_promote(last_move)

        elif last_move.move_type == "shoot":
            self._undo_shoot(last_move)

        elif last_move.move_type == "skip_shoot":
            self._undo_skip_shoot(last_move)

        return True

    def _undo_select(self, last_move: Move) -> None:
        """駒選択のundo → PIECE_SELECTに戻る"""
        self.state.selected_piece = None
        self.state.phase = GamePhase.PIECE_SELECT
        # 手番は戻さない（ターン終了していないため）

    def _undo_promote(self, last_move: Move) -> None:
        """成り判断のundo → PROMOTIONに戻る"""
        pos = last_move.from_pos  # 成り判断時のfrom_posは駒の位置
        piece_id = last_move.piece_id

        # 成った場合は元に戻す
        if last_move.promoted:
            piece_data = self.state.board.get(pos[0], pos[1])
            if piece_data:
                # 成り前の駒IDに戻す
                self.state.board.set(pos[0], pos[1], piece_id, piece_data[1], is_promoted=False)

        # 棋譜のmoveエントリを復元して_kifu_moveにセット
        # （直前のエントリは移動のはず）
        if len(self.state.kifu) > 0:
            self._kifu_move = self.state.kifu.moves[-1]

        self.state.phase = GamePhase.PROMOTION
        # 手番は戻さない（ターン終了していないため）

    def _undo_side_effects(self, last_move: Move) -> None:
        """共通の副作用を元に戻す"""
        # 成り戻しを元に戻す
        for pos, old_id, new_id in reversed(last_move.demotions):
            piece_data = self.state.board.get(pos[0], pos[1])
            if piece_data:
                self.state.board.set(pos[0], pos[1], old_id, piece_data[1])

        # 連鎖成りを元に戻す
        for pos, old_id, new_id in reversed(last_move.chain_promotions):
            piece_data = self.state.board.get(pos[0], pos[1])
            if piece_data:
                self.state.board.set(pos[0], pos[1], old_id, piece_data[1])

        # 道連れを元に戻す
        for pos, piece_id, killed_is_promoted in last_move.collateral_kills:
            self.state.board.set(pos[0], pos[1], piece_id, 1 - last_move.player, is_promoted=killed_is_promoted)

    def _undo_move(self, last_move: Move) -> None:
        """通常移動のundo"""
        from_pos = last_move.from_pos
        to_pos = last_move.to_pos
        piece_id = last_move.piece_id

        # 成りを元に戻す
        was_promoted_before = False
        if last_move.promoted:
            original_id = piece_id
            for pid in range(1, 60):
                try:
                    p = get_piece(pid)
                    if p.promotes_to == piece_id:
                        original_id = pid
                        break
                except:
                    pass
            piece_id = original_id
            was_promoted_before = False
        else:
            was_promoted_before = self.state.board.get_promoted(to_pos[0], to_pos[1])

        # 駒を元の位置に戻す
        self.state.board.remove(to_pos[0], to_pos[1])
        self.state.board.set(from_pos[0], from_pos[1], piece_id, last_move.player, is_promoted=was_promoted_before)

        # 取った駒を復元
        if last_move.captured_piece is not None:
            self.state.board.set(
                to_pos[0], to_pos[1], last_move.captured_piece, 1 - last_move.player,
                is_promoted=last_move.captured_was_promoted
            )

        # 手番を戻す
        self.state.current_player = last_move.player
        self.state.move_count -= 1
        self.state.winner = None

        # DEST_SELECTに戻る（selectエントリはまだ棋譜に残っている）
        self.state.selected_piece = from_pos
        self.state.phase = GamePhase.DEST_SELECT

    def _undo_step(self, last_move: Move) -> None:
        """マルチステップの1ステップをundo"""
        from_pos = last_move.from_pos
        to_pos = last_move.to_pos
        piece_id = last_move.piece_id
        player = last_move.player

        # 駒を元の位置に戻す
        already_promoted = self.state.board.get_promoted(to_pos[0], to_pos[1])
        self.state.board.remove(to_pos[0], to_pos[1])
        self.state.board.set(from_pos[0], from_pos[1], piece_id, player, is_promoted=already_promoted)

        # 取った駒を復元
        if last_move.captured_piece is not None:
            self.state.board.set(
                to_pos[0], to_pos[1], last_move.captured_piece, 1 - player,
                is_promoted=last_move.captured_was_promoted
            )

        # 1歩目かどうかを判定（直前の棋譜エントリがselectなら1歩目）
        is_first_step = (len(self.state.kifu) > 0 and
                         self.state.kifu.moves[-1].move_type == "select")

        if is_first_step:
            # 1歩目のundo → DEST_SELECTに戻る
            self.state.multi_step_state = None
            self.state.selected_piece = from_pos
            self.state.phase = GamePhase.DEST_SELECT
        else:
            # 2歩目以降のundo → MULTI_STEP_MOVEのまま
            if self.state.multi_step_state:
                ms_state = self.state.multi_step_state
                ms_state["current_pos"] = from_pos
                ms_state["remaining_steps"] += 1
                if ms_state["step_history"] and ms_state["step_history"][-1] == to_pos:
                    ms_state["step_history"].pop()
            self.state.phase = GamePhase.MULTI_STEP_MOVE

    def _undo_stop(self, last_move: Move) -> None:
        """マルチステップ停止のundo → MULTI_STEP_MOVEに戻る"""
        # 保存されたマルチステップ状態を復元
        if last_move.multi_step_state:
            self.state.multi_step_state = last_move.multi_step_state.copy()
        else:
            # 状態が保存されていない場合、最低限の状態を再構築
            self.state.multi_step_state = {
                "current_pos": last_move.from_pos,
                "piece_id": last_move.piece_id,
                "remaining_steps": 1,  # 少なくとも1歩残っていたはず
                "can_stop_early": True,
            }

        # 手番を戻す（stopはターン終了を伴う）
        self.state.current_player = last_move.player
        self.state.move_count -= 1
        self.state.winner = None

        self.state.phase = GamePhase.MULTI_STEP_MOVE

    def _undo_shoot(self, last_move: Move) -> None:
        """射撃のundo"""
        # 取った駒を復元
        if last_move.captured_piece is not None and last_move.captured_pos is not None:
            self.state.board.set(
                last_move.captured_pos[0], last_move.captured_pos[1],
                last_move.captured_piece, 1 - last_move.player,
                is_promoted=last_move.captured_was_promoted
            )

        # 射撃状態を復元
        if last_move.shoot_state:
            self.state.pending_shoot = last_move.shoot_state.copy()

        self.state.phase = GamePhase.SHOOTING
        # 手番は戻さない（射撃フェーズ中はターン終了していない）

    def _undo_skip_shoot(self, last_move: Move) -> None:
        """射撃スキップのundo → SHOOTINGに戻る"""
        # 射撃状態を復元
        if last_move.shoot_state:
            self.state.pending_shoot = last_move.shoot_state.copy()

        self.state.phase = GamePhase.SHOOTING
        # 手番は戻さない（ターン終了していないため）

    # ===================
    # 棋譜保存
    # ===================

    def _record_move(self, move: Move) -> None:
        """棋譜に手を記録（ストリーミング時は即座に書き込み）"""
        logger.debug(f"_record_move: player={move.player}, type={move.move_type}, from={move.from_pos}, to={move.to_pos}, mode={self._kifu_mode}")
        self.state.kifu.append(move)
        if self._kifu_mode == KifuMode.STREAMING and self._kifu_writer:
            self._kifu_writer.write_move(move)
            logger.debug(f"  -> ストリーミング書き込み完了")

    def save_kifu(self) -> None:
        """棋譜を保存（BATCHモード用、またはゲーム終了時）"""
        if self._kifu_mode == KifuMode.BATCH and self._kifu_path:
            self.state.kifu.save(self._kifu_path)
        elif self._kifu_writer:
            self._kifu_writer.finish(self.state.winner, self.state.kifu.win_reason)

    def close(self) -> None:
        """リソースを解放（途中終了時）"""
        if self._kifu_writer:
            self._kifu_writer.close()

    # ===================
    # ユーティリティ
    # ===================

    def get_legal_moves(self, pos: tuple[int, int]) -> list[tuple[int, int]]:
        """合法手を取得（ユーティリティ）"""
        return movement.get_legal_moves(self.state, pos)
