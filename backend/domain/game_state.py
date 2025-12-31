"""ゲーム状態管理"""

import copy
from dataclasses import dataclass, field
from typing import Optional
from .board import Board, BOARD_SIZE
from .piece_registry import get_piece


@dataclass
class StateSnapshot:
    """状態のスナップショット（undo用）"""
    board_grid: list[list]  # 盤面のコピー
    current_player: int
    captured_pieces: dict[int, list[int]]
    move_count: int
    winner: Optional[int]


@dataclass
class CapturedPieces:
    """取った駒の管理"""
    # player -> list of piece_ids
    pieces: dict[int, list[int]] = field(default_factory=lambda: {0: [], 1: []})

    def add(self, player: int, piece_id: int) -> None:
        """駒を追加"""
        self.pieces[player].append(piece_id)

    def get(self, player: int) -> list[int]:
        """プレイヤーの取った駒リストを取得"""
        return self.pieces[player].copy()


@dataclass
class GameState:
    """ゲームの状態"""
    board: Board = field(default_factory=Board)
    current_player: int = 0  # 0: 先手, 1: 後手
    captured: CapturedPieces = field(default_factory=CapturedPieces)
    move_count: int = 0
    winner: Optional[int] = None  # None: 継続中, 0: 先手勝ち, 1: 後手勝ち

    def switch_player(self) -> None:
        """手番を交代"""
        self.current_player = 1 - self.current_player
        self.move_count += 1

    def is_game_over(self) -> bool:
        """ゲームが終了しているか"""
        return self.winner is not None

    def create_snapshot(self) -> StateSnapshot:
        """現在の状態のスナップショットを作成"""
        return StateSnapshot(
            board_grid=copy.deepcopy(self.board.grid),
            current_player=self.current_player,
            captured_pieces={
                0: self.captured.pieces[0].copy(),
                1: self.captured.pieces[1].copy(),
            },
            move_count=self.move_count,
            winner=self.winner,
        )

    def restore_snapshot(self, snapshot: StateSnapshot) -> None:
        """スナップショットから状態を復元"""
        self.board.grid = snapshot.board_grid
        self.current_player = snapshot.current_player
        self.captured.pieces = snapshot.captured_pieces
        self.move_count = snapshot.move_count
        self.winner = snapshot.winner

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
    # 一段目（先手: y=18, 後手: y=0）
    # 前衝 | 高道 | 軍匠 | 軍吏 | 舎餘 | 舎人 | 力士 | 親兵 | 参謀 | 将 | 記室 | 親兵 | 力士 | 舎人 | 舎餘 | 軍吏 | 軍匠 | 神僧 | 前衝
    row1 = [12, 10, 9, 8, 7, 6, 5, 4, 3, 1, 2, 4, 5, 6, 7, 8, 9, 11, 12]

    # 二段目（先手: y=17, 後手: y=1）
    # 後衝 | 百総 | ┼ | 把総 | ┼ | 千総 | ┼ | 護兵 | 旗 | 中軍 | 鼓 | 護兵 | ┼ | 千総 | ┼ | 把総 | ┼ | 百総 | 後衝
    row2 = [13, 18, None, 17, None, 20, None, 19, 16, 14, 15, 19, None, 20, None, 17, None, 18, 13]

    # 三段目（先手: y=16, 後手: y=2）
    # 象 | 砲 | 弩 | 弓 | 象 | 砲 | 弩 | 弓 | 象 | 仏狼機 | 象 | 弓 | 弩 | 砲 | 象 | 弓 | 弩 | 砲 | 象
    row3 = [23, 26, 25, 24, 23, 26, 25, 24, 23, 22, 23, 24, 25, 26, 23, 24, 25, 26, 23]

    # 四段目（先手: y=15, 後手: y=3）
    # 騎総 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 馬兵 | ┼ | 騎総
    row4 = [21, None, 27, None, 27, None, 27, None, 27, None, 27, None, 27, None, 27, None, 27, None, 21]

    # 五段目（先手: y=14, 後手: y=4）
    # ├ | 歩総 | ┼ | 歩兵 | ┼ | 歩兵 | ┼ | 歩兵 | ┼ | 歩総 | ┼ | 歩兵 | ┼ | 歩兵 | ┼ | 歩兵 | ┼ | 歩総 | ┤
    row5 = [None, 29, None, 28, None, 28, None, 28, None, 29, None, 28, None, 28, None, 28, None, 29, None]

    # 六段目（先手: y=13, 後手: y=5）
    # 車総 | 牌総 | 車 | 牌 | 車 | 牌 | 車 | 牌 | 車 | 牌総 | 車 | 牌 | 車 | 牌 | 車 | 牌 | 車 | 牌総 | 車総
    row6 = [33, 31, 32, 30, 32, 30, 32, 30, 32, 31, 32, 30, 32, 30, 32, 30, 32, 31, 33]

    # 七段目（先手: y=12, 後手: y=6）
    # ├ | ┼ | ┼ | ┼ | ┼ | ┼ | ┼ | ┼ | ┼ | 先鋒 | ┼ | ┼ | ┼ | ┼ | ┼ | ┼ | ┼ | ┼ | ┤
    row7 = [None, None, None, None, None, None, None, None, None, 34, None, None, None, None, None, None, None, None, None]

    # 八〜十二段目は空（中央地帯）

    # 十三段目（先手: y=6, 後手: y=12）は row7 の対称
    # 十四段目（先手: y=5, 後手: y=13）は row6 の対称
    # ... 以下同様

    # 配置関数
    def place_row(row_data: list, y_sente: int, y_gote: int):
        for x, piece_id in enumerate(row_data):
            if piece_id is not None:
                state.board.set(x, y_sente, piece_id, 0)  # 先手
                state.board.set(x, y_gote, piece_id, 1)   # 後手

    place_row(row1, 18, 0)   # 一段目
    place_row(row2, 17, 1)   # 二段目
    place_row(row3, 16, 2)   # 三段目
    place_row(row4, 15, 3)   # 四段目
    place_row(row5, 14, 4)   # 五段目
    place_row(row6, 13, 5)   # 六段目
    place_row(row7, 12, 6)   # 七段目

    return state
