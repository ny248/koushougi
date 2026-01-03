"""ゲーム状態管理"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto
from .board import Board, BOARD_SIZE
from .kifu import Kifu
from .zobrist import get_zobrist_table


class GamePhase(Enum):
    """ゲームのフェーズ"""
    PIECE_SELECT = auto()    # 駒選択待ち
    DEST_SELECT = auto()     # 移動先選択待ち
    MULTI_STEP_MOVE = auto() # マルチステップ移動中
    PROMOTION = auto()       # 成り判断待ち
    SHOOTING = auto()        # 射撃待ち
    GAME_OVER = auto()       # ゲーム終了


@dataclass
class GameState:
    """ゲームの状態（完全な状態を保持）

    設計原則:
    - GameStateはゲームの完全な状態を表現する
    - GameEngineはサービスとして状態遷移を計算する
    - GameStateを変更せず、新しいGameStateを返す
    """
    board: Board = field(default_factory=Board)
    current_player: int = 0  # 0: 先手, 1: 後手
    move_count: int = 0
    winner: Optional[int] = None  # None: 継続中, 0: 先手勝ち, 1: 後手勝ち
    kifu: Kifu = field(default_factory=Kifu)

    # フェーズ関連
    phase: GamePhase = GamePhase.PIECE_SELECT
    selected_piece: Optional[tuple[int, int]] = None  # 選択中の駒位置
    pending_promotion: Optional[dict] = None  # 成り判断待ち状態
    pending_shoot: Optional[dict] = None  # 射撃待ち状態
    multi_step_state: Optional[dict] = None  # マルチステップ移動状態

    # Zobrist Hash（盤面+手番の識別子、千日手判定・Transposition Table用）
    _zobrist_hash: int = 0

    # 千日手判定用の局面履歴（Zobrist Hash → 出現回数）
    position_history: dict = field(default_factory=dict)

    @property
    def zobrist_hash(self) -> int:
        """現在のZobrist Hash値を取得"""
        return self._zobrist_hash

    def compute_zobrist_hash(self) -> int:
        """盤面全体からZobrist Hashを再計算"""
        table = get_zobrist_table()
        self._zobrist_hash = table.compute_full_hash(self.board, self.current_player)
        return self._zobrist_hash

    def update_zobrist_piece(self, x: int, y: int, piece_id: int, player: int, is_promoted: bool = False) -> None:
        """駒の追加/削除でZobrist Hashを差分更新（XOR）

        駒を置く時と取る時の両方で同じメソッドを呼ぶ。
        XORなので2回呼べば元に戻る。
        """
        table = get_zobrist_table()
        self._zobrist_hash ^= table.piece_hash(x, y, piece_id, player, is_promoted)

    def update_zobrist_turn(self) -> None:
        """手番交代でZobrist Hashを更新"""
        table = get_zobrist_table()
        self._zobrist_hash ^= table.turn_hash()

    def switch_player(self) -> None:
        """手番を交代"""
        self.update_zobrist_turn()
        self.current_player = 1 - self.current_player
        self.move_count += 1

    def record_position(self) -> None:
        """現在の局面を履歴に記録"""
        h = self._zobrist_hash
        self.position_history[h] = self.position_history.get(h, 0) + 1

    def is_sennichite(self) -> bool:
        """千日手（同一局面が3回以上）かどうか判定"""
        h = self._zobrist_hash
        return self.position_history.get(h, 0) >= 3

    def is_game_over(self) -> bool:
        """ゲームが終了しているか"""
        return self.winner is not None

    # ===================
    # 駒操作（Zobrist Hash自動更新）
    # ===================

    def set_piece(self, x: int, y: int, piece_id: int, player: int, is_promoted: bool = False) -> None:
        """駒を配置（Zobrist Hash自動更新）

        既存の駒がある場合は先に除去してから配置する。
        """
        # 既存の駒があれば除去（Zobrist Hash更新）
        existing = self.board.grid[x][y]
        if existing is not None:
            old_id, old_player = existing[0], existing[1]
            old_promoted = existing[2] if len(existing) > 2 else False
            self.update_zobrist_piece(x, y, old_id, old_player, old_promoted)

        # 新しい駒を配置
        self.board.grid[x][y] = (piece_id, player, is_promoted)
        self.update_zobrist_piece(x, y, piece_id, player, is_promoted)

    def remove_piece(self, x: int, y: int) -> None:
        """駒を除去（Zobrist Hash自動更新）"""
        existing = self.board.grid[x][y]
        if existing is not None:
            piece_id, player = existing[0], existing[1]
            is_promoted = existing[2] if len(existing) > 2 else False
            self.update_zobrist_piece(x, y, piece_id, player, is_promoted)
            self.board.grid[x][y] = None

    def get_piece(self, x: int, y: int) -> Optional[tuple[int, int]]:
        """駒を取得（piece_id, player）またはNone"""
        return self.board.get(x, y)

    def get_piece_promoted(self, x: int, y: int) -> bool:
        """駒が成っているかどうか"""
        return self.board.get_promoted(x, y)

    def get_piece_positions(self, piece_id: int, player: Optional[int] = None) -> list[tuple[int, int]]:
        """指定した駒の位置リストを取得"""
        positions = []
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                piece = self.board.get(x, y)
                if piece and piece[0] == piece_id:
                    if player is None or piece[1] == player:
                        positions.append((x, y))
        return positions

    def has_piece_alive(self, piece_id: int, player: int) -> bool:
        """指定した駒が生きているか"""
        return len(self.get_piece_positions(piece_id, player)) > 0

    def copy(self) -> "GameState":
        """状態のディープコピーを作成"""
        import copy
        new_board = Board()
        new_board.grid = [row[:] for row in self.board.grid]

        new_state = GameState(
            board=new_board,
            current_player=self.current_player,
            move_count=self.move_count,
            winner=self.winner,
            kifu=copy.deepcopy(self.kifu),
            phase=self.phase,
            selected_piece=self.selected_piece,
            pending_promotion=copy.deepcopy(self.pending_promotion) if self.pending_promotion else None,
            pending_shoot=copy.deepcopy(self.pending_shoot) if self.pending_shoot else None,
            multi_step_state=copy.deepcopy(self.multi_step_state) if self.multi_step_state else None,
        )
        new_state._zobrist_hash = self._zobrist_hash
        new_state.position_history = dict(self.position_history)
        return new_state


def create_initial_state() -> GameState:
    """初期配置のゲーム状態を作成

    GAMERULE.mdの初期配置図に基づく。
    先手（player=0）は下側（y=18が1段目）、後手（player=1）は上側（y=0が1段目）。

    駒ID対応:
    1:将, 2:記室, 3:参謀, 4:親兵, 5:力士, 6:舎人, 7:舎餘, 8:軍吏, 9:軍匠,
    10:高道, 11:神僧, 12:前衝, 13:後衝, 14:中軍, 15:鼓, 16:旗, 17:把総, 18:百総,
    19:護兵, 20:千総, 21:騎総, 22:仏狼機, 23:象, 24:弓, 25:弩, 26:砲, 27:馬兵,
    28:歩兵, 29:歩総, 30:牌, 31:牌総, 32:車, 33:車総, 34:先鋒
    """
    state = GameState()

    # 初期配置表（GAMERULE.mdより）
    row1 = [12, 10, 9, 8, 7, 6, 5, 4, 3, 1, 2, 4, 5, 6, 7, 8, 9, 11, 12]
    row2 = [13, 18, None, 17, None, 20, None, 19, 16, 14, 15, 19, None, 20, None, 17, None, 18, 13]
    row3 = [23, 26, 25, 24, 23, 26, 25, 24, 23, 22, 23, 24, 25, 26, 23, 24, 25, 26, 23]
    row4 = [21, None, 27, None, 27, None, 27, None, 27, None, 27, None, 27, None, 27, None, 27, None, 21]
    row5 = [None, 29, None, 28, None, 28, None, 28, None, 29, None, 28, None, 28, None, 28, None, 29, None]
    row6 = [33, 31, 32, 30, 32, 30, 32, 30, 32, 31, 32, 30, 32, 30, 32, 30, 32, 31, 33]
    row7 = [None, None, None, None, None, None, None, None, None, 34, None, None, None, None, None, None, None, None, None]

    def place_row(row_data: list, y_sente: int, y_gote: int):
        for x, piece_id in enumerate(row_data):
            if piece_id is not None:
                state.board.set(x, y_sente, piece_id, 0)  # 先手
                state.board.set(x, y_gote, piece_id, 1)   # 後手

    place_row(row1, 18, 0)
    place_row(row2, 17, 1)
    place_row(row3, 16, 2)
    place_row(row4, 15, 3)
    place_row(row5, 14, 4)
    place_row(row6, 13, 5)
    place_row(row7, 12, 6)

    # 初期盤面のZobrist Hashを計算
    state.compute_zobrist_hash()

    # 初期局面を履歴に記録
    state.record_position()

    return state
