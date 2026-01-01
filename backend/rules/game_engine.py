"""ゲームエンジン - フェーズ分離型アーキテクチャ"""

from typing import Optional
from dataclasses import dataclass
from enum import Enum, auto
from backend.domain.game_state import GameState, create_initial_state
from backend.domain.kifu import Move, Kifu
from backend.domain.piece_registry import get_piece
from . import movement, promotion, victory


class GamePhase(Enum):
    """ゲームのフェーズ"""
    PIECE_SELECT = auto()    # 駒選択待ち
    DEST_SELECT = auto()     # 移動先選択待ち
    MULTI_STEP_MOVE = auto() # マルチステップ移動中
    PROMOTION = auto()       # 成り判断待ち
    SHOOTING = auto()        # 射撃待ち
    GAME_OVER = auto()       # ゲーム終了


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
    """ゲームエンジン - フェーズ分離型"""

    def __init__(self, state: Optional[GameState] = None):
        self.state = state or create_initial_state()
        self._phase = GamePhase.PIECE_SELECT
        self._selected_piece: Optional[tuple[int, int]] = None  # 選択中の駒位置
        self._pending_move_result: Optional[MoveResult] = None  # 移動結果（成り判断用）
        self._pending_shoot: Optional[dict] = None  # 射撃待ち状態
        self._kifu_move: Optional[Move] = None  # 棋譜記録用
        self._multi_step_state: Optional[dict] = None  # マルチステップ移動状態

    # ===================
    # プロパティ
    # ===================

    @property
    def phase(self) -> GamePhase:
        """現在のフェーズ"""
        if self.is_game_over:
            return GamePhase.GAME_OVER
        return self._phase

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
        return self._selected_piece

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
        if self._phase != GamePhase.PIECE_SELECT:
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

        self._selected_piece = pos
        self._phase = GamePhase.DEST_SELECT
        return True

    def cancel_piece_selection(self) -> bool:
        """駒選択をキャンセル"""
        if self._phase != GamePhase.DEST_SELECT:
            return False

        self._selected_piece = None
        self._phase = GamePhase.PIECE_SELECT
        return True

    # ===================
    # フェーズ2: 移動先選択
    # ===================

    def get_legal_destinations(self) -> list[tuple[int, int]]:
        """選択中の駒の合法移動先"""
        if self._selected_piece is None:
            return []
        return movement.get_legal_moves(self.state, self._selected_piece)

    def select_destination(self, to_pos: tuple[int, int]) -> MoveResult:
        """移動先を選択して移動実行

        マルチステップ駒の場合は1歩目として扱い、MULTI_STEP_MOVEフェーズに遷移。
        通常駒の場合は従来通り移動完了。

        Returns:
            移動結果
        """
        if self._phase != GamePhase.DEST_SELECT:
            return MoveResult(success=False, error="移動先選択フェーズではありません")

        if self._selected_piece is None:
            return MoveResult(success=False, error="駒が選択されていません")

        from_pos = self._selected_piece

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
        self.state.kifu.append(self._kifu_move)
        self._kifu_move = None

        # マルチステップ状態を初期化
        self._multi_step_state = {
            "original_pos": from_pos,
            "current_pos": to_pos,
            "remaining_steps": config.total_steps - 1,
            "step_history": [from_pos, to_pos],
            "first_direction": first_direction,
            "can_stop_early": config.can_stop_early,
            "path_kills": path_kills,
            "piece_id": piece_id,
            "already_promoted": already_promoted,
        }

        self._selected_piece = None

        # 残りステップがあればMULTI_STEP_MOVEフェーズへ
        if self._multi_step_state["remaining_steps"] > 0:
            self._phase = GamePhase.MULTI_STEP_MOVE
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
        self._kifu_move.path_kills = move_result["path_kills"]

        result = MoveResult(
            success=True,
            captured=move_result["captured"],
            captured_pos=to_pos if move_result["captured"] else None,
            path_kills=move_result["path_kills"],
            after_effect=move_result["after_effect"],
            step_completed=True,
        )

        self._pending_move_result = result
        self._selected_piece = None

        # 成り判定（すでに成っている駒は成れない）
        piece = get_piece(piece_id)
        if piece.promotes_to is not None and not already_promoted:
            can_promote = promotion.can_promote(
                self.state, from_pos, to_pos, captured_piece, player
            )
            if can_promote:
                self._phase = GamePhase.PROMOTION
                return result

        # 成れない場合は射撃/ターン終了へ
        return self._after_promotion_check(result, to_pos)

    # ===================
    # フェーズ2.5: マルチステップ移動
    # ===================

    def get_next_step_options(self) -> list[tuple[int, int]]:
        """次ステップの移動先候補を取得"""
        if self._phase != GamePhase.MULTI_STEP_MOVE or self._multi_step_state is None:
            return []

        state = self._multi_step_state
        piece = get_piece(state["piece_id"])
        step_index = piece.get_multi_step_config().total_steps - state["remaining_steps"]

        return piece.get_next_step_options(
            state["current_pos"],
            self.state.board,
            self.current_player,
            step_index,
            state["first_direction"]
        )

    def get_remaining_steps(self) -> int:
        """残りステップ数を取得"""
        if self._multi_step_state is None:
            return 0
        return self._multi_step_state["remaining_steps"]

    def can_stop_now(self) -> bool:
        """今停止可能か"""
        if self._phase != GamePhase.MULTI_STEP_MOVE or self._multi_step_state is None:
            return False
        return self._multi_step_state["can_stop_early"]

    def get_multi_step_state(self) -> Optional[dict]:
        """マルチステップ状態を取得（AI訓練用）"""
        return self._multi_step_state

    def select_next_step(self, to_pos: tuple[int, int]) -> MoveResult:
        """次のステップを選択

        Args:
            to_pos: 次の位置

        Returns:
            移動結果
        """
        if self._phase != GamePhase.MULTI_STEP_MOVE:
            return MoveResult(success=False, error="マルチステップ移動中ではありません")

        if self._multi_step_state is None:
            return MoveResult(success=False, error="マルチステップ状態がありません")

        state = self._multi_step_state
        next_options = self.get_next_step_options()

        if to_pos not in next_options:
            return MoveResult(success=False, error="そこには移動できません")

        from_pos = state["current_pos"]
        piece_id = state["piece_id"]
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
                             is_promoted=state["already_promoted"])

        # 棋譜を記録
        self.state.kifu.append(kifu_move)

        # 状態を更新
        state["current_pos"] = to_pos
        state["remaining_steps"] -= 1
        state["step_history"].append(to_pos)
        state["path_kills"].extend(path_kills)

        # 残りステップがあれば継続
        if state["remaining_steps"] > 0:
            return MoveResult(
                success=True,
                path_kills=path_kills,
                step_completed=False,
            )

        # 全ステップ完了
        return self._complete_multi_step_move()

    def stop_move(self) -> MoveResult:
        """マルチステップ移動を早期停止"""
        if self._phase != GamePhase.MULTI_STEP_MOVE:
            return MoveResult(success=False, error="マルチステップ移動中ではありません")

        if self._multi_step_state is None:
            return MoveResult(success=False, error="マルチステップ状態がありません")

        if not self._multi_step_state["can_stop_early"]:
            return MoveResult(success=False, error="この駒は途中で止まれません")

        # 停止を棋譜に記録
        state = self._multi_step_state
        kifu_move = Move(
            player=self.current_player,
            move_type="stop",
            from_pos=state["current_pos"],
            to_pos=state["current_pos"],
            piece_id=state["piece_id"],
        )
        self.state.kifu.append(kifu_move)

        return self._complete_multi_step_move()

    def cancel_multi_step(self) -> MoveResult:
        """マルチステップ移動をキャンセル（元の位置に戻る）"""
        if self._phase != GamePhase.MULTI_STEP_MOVE:
            return MoveResult(success=False, error="マルチステップ移動中ではありません")

        if self._multi_step_state is None:
            return MoveResult(success=False, error="マルチステップ状態がありません")

        state = self._multi_step_state
        original_pos = state["original_pos"]
        current_pos = state["current_pos"]
        piece_id = state["piece_id"]
        player = self.current_player

        # 駒を元の位置に戻す
        self.state.board.remove(current_pos[0], current_pos[1])
        self.state.board.set(original_pos[0], original_pos[1], piece_id, player,
                             is_promoted=state["already_promoted"])

        # 経路上で取った駒を復元
        for pos, killed_id, was_promoted in state["path_kills"]:
            self.state.board.set(pos[0], pos[1], killed_id, 1 - player, is_promoted=was_promoted)

        # 棋譜からステップを削除
        steps_taken = len(state["step_history"]) - 1  # 元の位置を除く
        for _ in range(steps_taken):
            self.state.kifu.pop()

        # 状態をリセット
        self._multi_step_state = None
        self._phase = GamePhase.PIECE_SELECT

        return MoveResult(success=True)

    def _complete_multi_step_move(self) -> MoveResult:
        """マルチステップ移動を完了"""
        state = self._multi_step_state
        to_pos = state["current_pos"]
        original_pos = state["original_pos"]
        piece_id = state["piece_id"]
        player = self.current_player

        piece = get_piece(piece_id)

        # マルチステップ状態をクリア
        path_kills = state["path_kills"]
        already_promoted = state["already_promoted"]
        self._multi_step_state = None

        # 移動後効果を取得
        after_effect = None
        if hasattr(piece._module, "after_move"):
            after_effect = piece._module.after_move(
                self.state, original_pos, to_pos, player
            )

        result = MoveResult(
            success=True,
            path_kills=path_kills,
            after_effect=after_effect,
            step_completed=True,
        )

        self._pending_move_result = result

        # 成り判定（すでに成っている駒は成れない）
        if piece.promotes_to is not None and not already_promoted:
            # 経路で取った駒で成れるか確認
            captured_piece = None
            if path_kills:
                captured_piece = path_kills[-1][1]  # 最後に取った駒

            can_promote = promotion.can_promote(
                self.state, original_pos, to_pos, captured_piece, player
            )
            if can_promote:
                self._phase = GamePhase.PROMOTION
                return result

        # 成れない場合は射撃/ターン終了へ
        return self._after_promotion_check(result, to_pos)

    # ===================
    # フェーズ3: 成り判断
    # ===================

    def can_promote_now(self) -> bool:
        """現在成り判断待ちか"""
        return self._phase == GamePhase.PROMOTION

    def decide_promotion(self, promote: bool) -> MoveResult:
        """成り判断

        Args:
            promote: 成るかどうか

        Returns:
            結果
        """
        if self._phase != GamePhase.PROMOTION:
            return MoveResult(success=False, error="成り判断フェーズではありません")

        result = self._pending_move_result
        to_pos = self._kifu_move.to_pos
        player = self._kifu_move.player

        if promote:
            new_id = promotion.execute_promotion(self.state, to_pos)
            if new_id:
                result.promoted = True
                result.promoted_to = new_id
                self._kifu_move.promoted = True

                # 連鎖成り
                triggered = promotion.check_triggered_promotions(
                    self.state, new_id, player
                )
                result.triggered_promotions = triggered
                self._kifu_move.chain_promotions = triggered

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
                # 射撃待ち状態
                shoot_count = effect["shoot"]["count"]
                self._pending_shoot = {
                    "pos": to_pos,
                    "targets": effect["shoot"]["targets"],
                    "count": shoot_count,
                    "remaining": shoot_count,  # 残り射撃回数
                }
                result.can_shoot = True
                self._phase = GamePhase.SHOOTING
                return result

            if "area_kill" in effect:
                # 周囲破壊は自動実行
                killed = movement.execute_area_kill(
                    self.state, effect["area_kill"], self._kifu_move.player
                )
                result.path_kills.extend(killed)
                self._kifu_move.collateral_kills = killed

        # ターン終了処理
        return self._finalize_turn(result)

    # ===================
    # フェーズ4: 射撃
    # ===================

    def get_shoot_targets(self) -> list[tuple[int, int]]:
        """射撃可能な対象を取得"""
        if self._pending_shoot:
            return self._pending_shoot["targets"]
        return []

    def get_remaining_shoot_count(self) -> int:
        """残り射撃回数を取得"""
        if self._pending_shoot:
            return self._pending_shoot.get("remaining", 0)
        return 0

    def shoot(self, target: tuple[int, int]) -> MoveResult:
        """射撃を実行（1体）

        Args:
            target: 射撃対象の位置

        Returns:
            結果
        """
        if self._phase != GamePhase.SHOOTING:
            return MoveResult(success=False, error="射撃フェーズではありません")

        if not self._pending_shoot:
            return MoveResult(success=False, error="射撃待ちではありません")

        shoot_info = self._pending_shoot
        valid_targets = shoot_info["targets"]

        if target not in valid_targets:
            return MoveResult(success=False, error=f"{target}は射撃対象外です")

        # 射撃実行
        player = self.current_player
        killed = movement.execute_shoot(self.state, [target], player)

        # 棋譜に射撃情報を追加
        for pos, piece_id, is_prom in killed:
            self._kifu_move.path_kills.append((pos, piece_id, is_prom))

        # 残り回数を減らす
        shoot_info["remaining"] -= 1

        # ターゲットリストから撃った駒を除外
        shoot_info["targets"] = [t for t in shoot_info["targets"] if t != target]

        result = MoveResult(
            success=True,
            path_kills=killed,
        )

        # まだ射撃回数が残っていて、ターゲットもある場合は射撃フェーズを継続
        if shoot_info["remaining"] > 0 and shoot_info["targets"]:
            result.can_shoot = True
            return result

        # 射撃終了
        self._pending_shoot = None
        return self._finalize_turn(result)

    def skip_shoot(self) -> MoveResult:
        """射撃をスキップ"""
        if self._phase != GamePhase.SHOOTING:
            return MoveResult(success=False, error="射撃フェーズではありません")

        self._pending_shoot = None
        result = MoveResult(success=True)
        return self._finalize_turn(result)

    # ===================
    # ターン終了処理
    # ===================

    def _finalize_turn(self, result: MoveResult) -> MoveResult:
        """ターン終了処理"""
        # 成り戻りチェック
        demotions = movement.check_revert_all(self.state)
        if self._kifu_move:
            self._kifu_move.demotions = demotions

        # 棋譜に記録
        if self._kifu_move:
            self.state.kifu.append(self._kifu_move)
            self._kifu_move = None

        # 勝敗判定
        winner = victory.check_victory(self.state)
        if winner is not None:
            result.winner = winner
            self.state.kifu.winner = winner
            self.state.kifu.win_reason = "capture"
            self._phase = GamePhase.GAME_OVER
            return result

        # ターン終了
        movement.end_turn(self.state)
        self._phase = GamePhase.PIECE_SELECT
        self._pending_move_result = None

        return result

    # ===================
    # Undo
    # ===================

    def undo(self) -> bool:
        """棋譜ベースのUndo"""
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
        for pos, piece_id, killed_is_promoted in last_move.collateral_kills:
            self.state.board.set(pos[0], pos[1], piece_id, 1 - last_move.player, is_promoted=killed_is_promoted)

        if last_move.move_type == "move":
            from_pos = last_move.from_pos
            to_pos = last_move.to_pos
            piece_id = last_move.piece_id

            # 成りを元に戻す
            was_promoted_before = False
            if last_move.promoted:
                piece = get_piece(piece_id)
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

            # 経路上で取った駒を復元
            for pos, killed_id, killed_is_promoted in last_move.path_kills:
                self.state.board.set(pos[0], pos[1], killed_id, 1 - last_move.player, is_promoted=killed_is_promoted)

        elif last_move.move_type == "shoot":
            if last_move.captured_piece is not None and last_move.captured_pos is not None:
                self.state.board.set(
                    last_move.captured_pos[0], last_move.captured_pos[1],
                    last_move.captured_piece, 1 - last_move.player,
                    is_promoted=last_move.captured_was_promoted
                )
            for pos, killed_id, killed_is_promoted in last_move.path_kills:
                self.state.board.set(pos[0], pos[1], killed_id, 1 - last_move.player, is_promoted=killed_is_promoted)

        # 手番を戻す
        self.state.current_player = last_move.player
        self.state.move_count -= 1
        self.state.winner = None
        self._phase = GamePhase.PIECE_SELECT

        return True

    # ===================
    # ユーティリティ
    # ===================

    def get_legal_moves(self, pos: tuple[int, int]) -> list[tuple[int, int]]:
        """合法手を取得（ユーティリティ）"""
        return movement.get_legal_moves(self.state, pos)
