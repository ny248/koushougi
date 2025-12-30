"""広将棋 GUI アプリケーション"""

import pygame
import sys
from typing import Optional
from enum import Enum
from backend.rules.game_engine import GameEngine
from frontend.pygame.renderer import BoardRenderer, InfoPanel
from frontend.pygame.menu import MenuScreen, GameConfig, PlayerType
from ai import RandomPlayer
from config import GUI_AI_DELAY_MS, GUI_CELL_SIZE, GUI_MARGIN, GUI_PANEL_WIDTH


class AppState(Enum):
    MENU = "menu"
    PLAYING = "playing"


class GameApp:
    """GUIアプリケーション"""

    def __init__(self):
        pygame.init()

        # レンダラー
        self.board_renderer = BoardRenderer(cell_size=GUI_CELL_SIZE, margin=GUI_MARGIN)
        self.board_renderer.init_fonts()

        # 情報パネル
        panel_width = GUI_PANEL_WIDTH
        panel_height = self.board_renderer.surface_size
        self.info_panel = InfoPanel(panel_width, panel_height)
        self.info_panel.init_fonts()

        # ウィンドウ
        window_width = self.board_renderer.surface_size + panel_width
        window_height = self.board_renderer.surface_size
        self.screen = pygame.display.set_mode((window_width, window_height))
        pygame.display.set_caption("広将棋")

        # サーフェス
        self.board_surface = pygame.Surface(
            (self.board_renderer.surface_size, self.board_renderer.surface_size)
        )
        self.panel_surface = pygame.Surface((panel_width, panel_height))

        # メニュー画面
        self.menu = MenuScreen(window_width, window_height)
        self.menu.init_fonts()

        # アプリ状態
        self.app_state = AppState.MENU
        self.config: Optional[GameConfig] = None

        # ゲームエンジン
        self.engine = GameEngine()

        # AI
        self.ai = RandomPlayer()

        # UI状態
        self.selected_pos: Optional[tuple[int, int]] = None
        self.legal_moves: list[tuple[int, int]] = []
        self.shoot_targets: list[tuple[int, int]] = []
        self.status_text = ""
        self.can_promote = False
        self.pending_move: Optional[tuple[tuple[int, int], tuple[int, int]]] = None

        # AI思考中フラグ
        self.ai_thinking = False
        self.ai_delay_timer = 0
        self.ai_delay_ms = GUI_AI_DELAY_MS

        # クロック
        self.clock = pygame.time.Clock()

    def run(self):
        """メインループ"""
        running = True
        while running:
            dt = self.clock.tick(60)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif self.app_state == AppState.MENU:
                    config = self.menu.handle_event(event)
                    if config:
                        self.start_game(config)
                elif self.app_state == AppState.PLAYING:
                    self.handle_game_event(event)

            # AI処理
            if self.app_state == AppState.PLAYING:
                self.update_ai(dt)

            self.draw()
            pygame.display.flip()

        pygame.quit()
        sys.exit()

    def start_game(self, config: GameConfig):
        """ゲーム開始"""
        self.config = config
        self.engine = GameEngine()
        self.clear_selection()
        self.shoot_targets = []
        self.can_promote = False
        self.pending_move = None
        self.app_state = AppState.PLAYING
        self.ai_thinking = False
        self.ai_delay_timer = 0

        # 開始時のステータス
        sente_str = "人間" if config.sente_type == PlayerType.HUMAN else "AI"
        gote_str = "人間" if config.gote_type == PlayerType.HUMAN else "AI"
        self.status_text = f"先手:{sente_str} vs 後手:{gote_str}"

    def is_human_turn(self) -> bool:
        """現在の手番が人間かどうか"""
        if self.config is None:
            return True
        player = self.engine.current_player
        if player == 0:
            return self.config.sente_type == PlayerType.HUMAN
        else:
            return self.config.gote_type == PlayerType.HUMAN

    def update_ai(self, dt: int):
        """AI処理の更新"""
        if self.engine.is_game_over:
            return

        if self.is_human_turn():
            self.ai_thinking = False
            return

        # 成り選択待ち中はAI処理しない（人間の操作待ち）
        if self.can_promote:
            return

        # AI思考開始
        if not self.ai_thinking:
            self.ai_thinking = True
            self.ai_delay_timer = 0
            turn_name = "先手" if self.engine.current_player == 0 else "後手"
            self.status_text = f"{turn_name}(AI)思考中..."

        # 遅延タイマー
        self.ai_delay_timer += dt
        if self.ai_delay_timer < self.ai_delay_ms:
            return

        # 射撃待ち状態
        if self.shoot_targets:
            target = self.ai.choose_shoot(self.engine, self.shoot_targets)
            if target:
                self.execute_shoot(target)
            else:
                self.skip_shoot()
            self.ai_thinking = False
            self.ai_delay_timer = 0
            return

        # 通常移動
        move = self.ai.choose_move(self.engine)
        if move:
            from_pos = move["from"]
            to_pos = move["to"]
            promote = move.get("promote", False)
            self.execute_move(from_pos, to_pos, promote)

        self.ai_thinking = False
        self.ai_delay_timer = 0

    def handle_game_event(self, event: pygame.event.Event):
        """ゲーム中のイベント処理"""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # 左クリック
                self.handle_click(event.pos)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # メニューに戻る
                self.app_state = AppState.MENU
            elif event.key == pygame.K_r:  # リセット
                if self.config:
                    self.start_game(self.config)
            elif event.key == pygame.K_y and self.can_promote:
                # 成る
                self.confirm_move(promote=True)
            elif event.key == pygame.K_n and self.can_promote:
                # 成らない
                self.confirm_move(promote=False)
            elif event.key == pygame.K_s and self.shoot_targets and self.is_human_turn():
                # 射撃スキップ
                self.skip_shoot()

    def handle_click(self, pixel_pos: tuple[int, int]):
        """クリック処理"""
        # 人間の番でなければ無視
        if not self.is_human_turn():
            return

        # ゲーム終了時は無視
        if self.engine.is_game_over:
            return

        # 成り選択中は無視
        if self.can_promote:
            return

        # 盤面クリック判定
        board_pos = self.board_renderer.pixel_to_board(pixel_pos[0], pixel_pos[1])

        if board_pos is None:
            return

        # 射撃待ち状態
        if self.shoot_targets:
            self.handle_shoot_click(board_pos)
            return

        # 通常の選択・移動
        self.handle_board_click(board_pos)

    def handle_board_click(self, pos: tuple[int, int]):
        """盤面クリック処理"""
        piece = self.engine.state.board.get(pos[0], pos[1])

        if self.selected_pos is None:
            # 選択
            if piece and piece[1] == self.engine.current_player:
                self.selected_pos = pos
                self.legal_moves = self.engine.get_legal_moves(pos)
                self.status_text = f"選択: ({pos[0]}, {pos[1]})"
        else:
            # 移動先クリック
            if pos in self.legal_moves:
                # 移動実行（成り判定付き）
                self.try_move(self.selected_pos, pos)
            elif piece and piece[1] == self.engine.current_player:
                # 自分の別の駒を選択
                self.selected_pos = pos
                self.legal_moves = self.engine.get_legal_moves(pos)
                self.status_text = f"選択: ({pos[0]}, {pos[1]})"
            else:
                # 選択解除
                self.clear_selection()

    def try_move(self, from_pos: tuple[int, int], to_pos: tuple[int, int]):
        """移動を試みる（成り選択が必要な場合は待機）"""
        # 移動先に駒があるか確認
        target = self.engine.state.board.get(to_pos[0], to_pos[1])
        captured_piece = target[0] if target else None

        # 移動元の駒情報を取得
        piece_data = self.engine.state.board.get(from_pos[0], from_pos[1])
        if piece_data is None:
            return

        piece_id, player = piece_data
        from backend.domain.piece_registry import get_piece
        piece = get_piece(piece_id)

        # 成りが可能か判定
        if piece.promotes_to is not None:
            from backend.rules import promotion
            can_promote = promotion.can_promote(
                self.engine.state, from_pos, to_pos, captured_piece, player
            )
            if can_promote:
                # 成り選択待ち
                self.pending_move = (from_pos, to_pos)
                self.can_promote = True
                self.status_text = "成りますか？ Y: 成る / N: 成らない"
                return

        # 成りなしで移動
        self.execute_move(from_pos, to_pos, promote=False)

    def confirm_move(self, promote: bool):
        """成り選択確定"""
        if self.pending_move is None:
            return

        from_pos, to_pos = self.pending_move
        self.pending_move = None
        self.can_promote = False
        self.execute_move(from_pos, to_pos, promote=promote)

    def execute_move(self, from_pos: tuple[int, int], to_pos: tuple[int, int],
                     promote: bool):
        """移動実行"""
        result = self.engine.move(from_pos, to_pos, promote=promote)

        if result.success:
            self.clear_selection()

            # 結果表示
            status_parts = []
            if result.captured:
                from backend.domain.piece_registry import get_piece
                try:
                    name = get_piece(result.captured).name
                    status_parts.append(f"{name}を取った")
                except:
                    pass
            if result.promoted:
                status_parts.append("成った！")
            if result.triggered_promotions:
                status_parts.append(f"連鎖成り×{len(result.triggered_promotions)}")

            # 射撃待ち
            if result.after_effect and "shoot" in result.after_effect:
                self.shoot_targets = self.engine.get_shoot_targets() or []
                if self.is_human_turn():
                    status_parts.append("射撃先を選択（Sでスキップ）")
                else:
                    status_parts.append("AI射撃中...")

            # 勝敗
            if result.winner is not None:
                winner_name = "先手" if result.winner == 0 else "後手"
                status_parts.append(f"{winner_name}の勝ち！")

            self.status_text = " / ".join(status_parts) if status_parts else ""
        else:
            self.status_text = result.error or "移動できません"

    def handle_shoot_click(self, pos: tuple[int, int]):
        """射撃クリック処理"""
        if pos in self.shoot_targets:
            self.execute_shoot(pos)
        else:
            self.status_text = "射撃できない位置です"

    def execute_shoot(self, pos: tuple[int, int]):
        """射撃実行"""
        result = self.engine.shoot([pos])
        self.shoot_targets = []

        if result.success:
            status_parts = []
            if result.path_kills:
                status_parts.append(f"{len(result.path_kills)}体撃破")
            if result.winner is not None:
                winner_name = "先手" if result.winner == 0 else "後手"
                status_parts.append(f"{winner_name}の勝ち！")
            self.status_text = " / ".join(status_parts) if status_parts else ""
        else:
            self.status_text = result.error or "射撃失敗"

    def skip_shoot(self):
        """射撃スキップ"""
        result = self.engine.skip_shoot()
        self.shoot_targets = []
        self.status_text = "射撃をスキップ"

    def clear_selection(self):
        """選択解除"""
        self.selected_pos = None
        self.legal_moves = []

    def draw(self):
        """描画"""
        if self.app_state == AppState.MENU:
            self.menu.draw(self.screen)
        else:
            # 盤面描画
            self.board_renderer.draw_state(
                self.board_surface,
                self.engine.state,
                selected=self.selected_pos,
                move_targets=self.legal_moves if not self.shoot_targets else None,
                shoot_targets=self.shoot_targets,
            )
            self.screen.blit(self.board_surface, (0, 0))

            # 情報パネル
            self.info_panel.draw(
                self.panel_surface,
                self.engine.state,
                self.status_text,
            )
            self.screen.blit(self.panel_surface, (self.board_renderer.surface_size, 0))


def main():
    """エントリーポイント"""
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
