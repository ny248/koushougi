"""広将棋 GUI アプリケーション（フェーズ分離型API対応）"""

import pygame
import sys
from typing import Optional
from enum import Enum
from backend.rules.game_engine import GameEngine, GamePhase
from frontend.pygame.renderer import BoardRenderer, InfoPanel
from frontend.pygame.menu import MenuScreen, GameConfig, PlayerType
from ai.minimax.player import MinimaxPlayer
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

        # AI (Minimax depth=3)
        self.ai = MinimaxPlayer(depth=3, max_moves=15)

        # UI状態
        self.selected_pos: Optional[tuple[int, int]] = None
        self.legal_moves: list[tuple[int, int]] = []
        self.status_text = ""

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

        # AIが1ステップ処理（相手の手番になるまで繰り返す）
        current_player = self.engine.current_player
        while not self.engine.is_game_over and self.engine.current_player == current_player:
            if not self.ai.play_step(self.engine):
                break
        self.clear_selection()

        # 結果表示
        if self.engine.is_game_over:
            winner_name = "先手" if self.engine.winner == 0 else "後手"
            self.status_text = f"{winner_name}の勝ち！"
        else:
            self.status_text = ""

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
            elif event.key == pygame.K_u:  # Undo
                self.engine.undo()
                self.clear_selection()
                self.status_text = "Undo"
            elif event.key == pygame.K_y and self.engine.phase == GamePhase.PROMOTION:
                # 成る
                self.decide_promotion(promote=True)
            elif event.key == pygame.K_n and self.engine.phase == GamePhase.PROMOTION:
                # 成らない
                self.decide_promotion(promote=False)
            elif event.key == pygame.K_s and self.engine.phase == GamePhase.SHOOTING and self.is_human_turn():
                # 射撃スキップ
                self.skip_shoot()
            elif event.key == pygame.K_SPACE and self.engine.phase == GamePhase.MULTI_STEP_MOVE and self.is_human_turn():
                # マルチステップ移動を停止
                self.stop_multi_step()
            elif event.key == pygame.K_ESCAPE and self.engine.phase == GamePhase.MULTI_STEP_MOVE and self.is_human_turn():
                # マルチステップ移動をキャンセル
                self.cancel_multi_step()

    def handle_click(self, pixel_pos: tuple[int, int]):
        """クリック処理"""
        # 人間の番でなければ無視
        if not self.is_human_turn():
            return

        # ゲーム終了時は無視
        if self.engine.is_game_over:
            return

        phase = self.engine.phase

        # 成り選択中はボタンクリックのみ許可
        if phase == GamePhase.PROMOTION:
            # パネル領域のクリック判定
            panel_x = pixel_pos[0] - self.board_renderer.surface_size
            if panel_x >= 0:
                result = self.info_panel.get_promotion_click(panel_x, pixel_pos[1])
                if result is not None:
                    self.decide_promotion(promote=result)
            return

        # 盤面クリック判定
        board_pos = self.board_renderer.pixel_to_board(pixel_pos[0], pixel_pos[1])

        if board_pos is None:
            return

        # 射撃待ち状態
        if phase == GamePhase.SHOOTING:
            self.handle_shoot_click(board_pos)
            return

        # マルチステップ移動中
        if phase == GamePhase.MULTI_STEP_MOVE:
            self.handle_multi_step_click(board_pos)
            return

        # 駒選択 or 移動先選択
        self.handle_board_click(board_pos)

    def handle_board_click(self, pos: tuple[int, int]):
        """盤面クリック処理（駒選択 or 移動先選択）"""
        phase = self.engine.phase
        piece = self.engine.state.board.get(pos[0], pos[1])

        if phase == GamePhase.PIECE_SELECT:
            # 駒選択フェーズ
            if piece and piece[1] == self.engine.current_player:
                if self.engine.select_piece(pos):
                    self.selected_pos = pos
                    self.legal_moves = self.engine.get_legal_destinations()
                    self.status_text = f"選択: ({pos[0]}, {pos[1]})"
                else:
                    self.status_text = "その駒は動かせません"

        elif phase == GamePhase.DEST_SELECT:
            # 移動先選択フェーズ
            if pos in self.legal_moves:
                # 移動実行
                result = self.engine.select_destination(pos)
                if result.success:
                    self.handle_move_result(result)
                else:
                    self.status_text = result.error or "移動できません"
            elif piece and piece[1] == self.engine.current_player:
                # 別の駒を選択し直す
                self.engine.cancel_piece_selection()
                if self.engine.select_piece(pos):
                    self.selected_pos = pos
                    self.legal_moves = self.engine.get_legal_destinations()
                    self.status_text = f"選択: ({pos[0]}, {pos[1]})"
            else:
                # 選択解除
                self.engine.cancel_piece_selection()
                self.clear_selection()

    def handle_move_result(self, result):
        """移動結果を処理"""
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

        # マルチステップ移動中
        if self.engine.phase == GamePhase.MULTI_STEP_MOVE:
            remaining = self.engine.get_remaining_steps()
            can_stop = self.engine.can_stop_now()
            stop_msg = "Space:停止, " if can_stop else ""
            self.status_text = f"次のステップを選択（残り{remaining}歩, {stop_msg}ESC:キャンセル）"
            # 次ステップ候補をlegal_movesにセット
            self.legal_moves = self.engine.get_next_step_options()
            state = self.engine.get_multi_step_state()
            if state:
                self.selected_pos = state["current_pos"]
            return

        # 成り判断待ち
        if self.engine.phase == GamePhase.PROMOTION:
            self.status_text = "成りますか？ Y: 成る / N: 成らない"
            return

        # 射撃待ち
        if self.engine.phase == GamePhase.SHOOTING:
            remaining = self.engine.get_remaining_shoot_count()
            self.status_text = f"射撃先をクリック（残り{remaining}回, Sでスキップ）"
            return

        # 勝敗
        if result.winner is not None:
            winner_name = "先手" if result.winner == 0 else "後手"
            status_parts.append(f"{winner_name}の勝ち！")

        self.status_text = " / ".join(status_parts) if status_parts else ""

    def decide_promotion(self, promote: bool):
        """成り判断"""
        result = self.engine.decide_promotion(promote)
        if result.success:
            status_parts = []
            if promote and result.promoted:
                status_parts.append("成った！")
            if result.triggered_promotions:
                status_parts.append(f"連鎖成り×{len(result.triggered_promotions)}")

            # 射撃待ち
            if self.engine.phase == GamePhase.SHOOTING:
                remaining = self.engine.get_remaining_shoot_count()
                self.status_text = f"射撃先をクリック（残り{remaining}回, Sでスキップ）"
                return

            # 勝敗
            if result.winner is not None:
                winner_name = "先手" if result.winner == 0 else "後手"
                status_parts.append(f"{winner_name}の勝ち！")

            self.status_text = " / ".join(status_parts) if status_parts else ""
        else:
            self.status_text = result.error or "エラー"

    def handle_shoot_click(self, pos: tuple[int, int]):
        """射撃クリック処理"""
        targets = self.engine.get_shoot_targets()
        if pos in targets:
            self.execute_shoot(pos)
        else:
            self.status_text = "射撃できない位置です"

    def execute_shoot(self, target: tuple[int, int]):
        """射撃実行"""
        result = self.engine.shoot(target)

        if result.success:
            status_parts = []
            if result.path_kills:
                status_parts.append(f"{len(result.path_kills)}体撃破")

            # まだ射撃可能な場合
            if result.can_shoot and self.engine.phase == GamePhase.SHOOTING:
                remaining = self.engine.get_remaining_shoot_count()
                status_parts.append(f"残り{remaining}回")
                self.status_text = " / ".join(status_parts) + "（Sでスキップ）"
                return

            if result.winner is not None:
                winner_name = "先手" if result.winner == 0 else "後手"
                status_parts.append(f"{winner_name}の勝ち！")
            self.status_text = " / ".join(status_parts) if status_parts else ""
        else:
            self.status_text = result.error or "射撃失敗"

    def skip_shoot(self):
        """射撃スキップ"""
        self.engine.skip_shoot()
        self.status_text = "射撃をスキップ"

    def handle_multi_step_click(self, pos: tuple[int, int]):
        """マルチステップ移動中のクリック処理"""
        options = self.engine.get_next_step_options()
        if pos in options:
            result = self.engine.select_next_step(pos)
            if result.success:
                self.handle_move_result(result)
            else:
                self.status_text = result.error or "移動できません"
        else:
            self.status_text = "その位置には移動できません"

    def stop_multi_step(self):
        """マルチステップ移動を停止"""
        if not self.engine.can_stop_now():
            self.status_text = "ここでは停止できません"
            return

        result = self.engine.stop_move()
        if result.success:
            self.clear_selection()
            self.handle_move_result(result)
        else:
            self.status_text = result.error or "停止できません"

    def cancel_multi_step(self):
        """マルチステップ移動をキャンセル"""
        result = self.engine.cancel_multi_step()
        if result.success:
            self.clear_selection()
            self.status_text = "移動をキャンセル"
        else:
            self.status_text = result.error or "キャンセルできません"

    def clear_selection(self):
        """選択解除"""
        self.selected_pos = None
        self.legal_moves = []

    def draw(self):
        """描画"""
        if self.app_state == AppState.MENU:
            self.menu.draw(self.screen)
        else:
            phase = self.engine.phase
            shoot_targets = self.engine.get_shoot_targets() if phase == GamePhase.SHOOTING else []

            # マルチステップ移動中の経路表示用
            step_history = None
            if phase == GamePhase.MULTI_STEP_MOVE:
                state = self.engine.get_multi_step_state()
                if state:
                    step_history = state.get("step_history", [])

            # 盤面描画
            self.board_renderer.draw_state(
                self.board_surface,
                self.engine.state,
                selected=self.selected_pos,
                move_targets=self.legal_moves if phase in (GamePhase.DEST_SELECT, GamePhase.MULTI_STEP_MOVE) else None,
                shoot_targets=shoot_targets,
                step_history=step_history,
            )
            self.screen.blit(self.board_surface, (0, 0))

            # 情報パネル
            self.info_panel.draw(
                self.panel_surface,
                self.engine.state,
                self.status_text,
                show_promotion_buttons=(phase == GamePhase.PROMOTION),
            )
            self.screen.blit(self.panel_surface, (self.board_renderer.surface_size, 0))


def main():
    """エントリーポイント"""
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
