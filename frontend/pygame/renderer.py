"""Pygame描画モジュール"""

import pygame
from typing import Optional
from backend.domain.game_state import GameState
from backend.domain.piece_registry import get_piece


# 色定義
COLOR_BOARD_BG = (222, 184, 135)  # 木材っぽい色
COLOR_LINE = (0, 0, 0)            # 黒線
COLOR_SENTE_STONE = (240, 240, 240)  # 先手: 白石
COLOR_GOTE_STONE = (40, 40, 40)      # 後手: 黒石
COLOR_SENTE_TEXT = (0, 0, 0)         # 先手: 黒字
COLOR_GOTE_TEXT = (255, 255, 255)    # 後手: 白字
COLOR_PROMOTED_TEXT = (200, 50, 50)  # 成り駒: 朱字
COLOR_SELECTED = (100, 200, 100, 150)  # 選択中: 緑
COLOR_MOVE_TARGET = (100, 100, 255, 150)  # 移動先: 青
COLOR_SHOOT_TARGET = (255, 100, 100, 150)  # 射撃対象: 赤


class BoardRenderer:
    """盤面描画クラス"""

    def __init__(self, cell_size: int = 36, margin: int = 30):
        self.cell_size = cell_size
        self.margin = margin
        self.board_size = 19

        # 盤面の実サイズ
        self.board_pixel_size = (self.board_size - 1) * cell_size
        self.surface_size = self.board_pixel_size + margin * 2

        # フォント（後で初期化）
        self.font: Optional[pygame.font.Font] = None
        self.small_font: Optional[pygame.font.Font] = None

    def init_fonts(self):
        """フォント初期化（pygame.init()後に呼ぶ）"""
        pygame.font.init()
        # macOSの日本語フォントパスを直接指定
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]

        import os
        font_path = None
        for path in font_paths:
            if os.path.exists(path):
                font_path = path
                break

        font_size = int(self.cell_size * 0.55)
        if font_path:
            self.font = pygame.font.Font(font_path, font_size)
            self.small_font = pygame.font.Font(font_path, font_size // 2)
        else:
            # フォールバック: デフォルトフォント
            self.font = pygame.font.Font(None, font_size)
            self.small_font = pygame.font.Font(None, font_size // 2)

    def board_to_pixel(self, x: int, y: int) -> tuple[int, int]:
        """盤面座標からピクセル座標へ"""
        px = self.margin + x * self.cell_size
        py = self.margin + y * self.cell_size
        return (px, py)

    def pixel_to_board(self, px: int, py: int) -> Optional[tuple[int, int]]:
        """ピクセル座標から盤面座標へ"""
        x = round((px - self.margin) / self.cell_size)
        y = round((py - self.margin) / self.cell_size)
        if 0 <= x < self.board_size and 0 <= y < self.board_size:
            return (x, y)
        return None

    def draw_board(self, surface: pygame.Surface):
        """盤面の線を描画"""
        # 背景
        surface.fill(COLOR_BOARD_BG)

        # 縦線
        for x in range(self.board_size):
            start = self.board_to_pixel(x, 0)
            end = self.board_to_pixel(x, self.board_size - 1)
            pygame.draw.line(surface, COLOR_LINE, start, end, 1)

        # 横線
        for y in range(self.board_size):
            start = self.board_to_pixel(0, y)
            end = self.board_to_pixel(self.board_size - 1, y)
            pygame.draw.line(surface, COLOR_LINE, start, end, 1)

        # 星（天元と四隅）
        star_points = [(3, 3), (9, 3), (15, 3),
                       (3, 9), (9, 9), (15, 9),
                       (3, 15), (9, 15), (15, 15)]
        for x, y in star_points:
            pos = self.board_to_pixel(x, y)
            pygame.draw.circle(surface, COLOR_LINE, pos, 3)

    def draw_piece(self, surface: pygame.Surface, x: int, y: int,
                   piece_id: int, player: int, is_promoted: bool = False):
        """駒を描画"""
        pos = self.board_to_pixel(x, y)
        radius = int(self.cell_size * 0.42)

        # 石（円）
        stone_color = COLOR_SENTE_STONE if player == 0 else COLOR_GOTE_STONE
        pygame.draw.circle(surface, stone_color, pos, radius)
        pygame.draw.circle(surface, COLOR_LINE, pos, radius, 1)  # 縁取り

        # 駒名
        try:
            piece = get_piece(piece_id)
            name = piece.name
        except:
            name = "?"

        # 2文字以上なら縦書き風に
        if len(name) >= 2:
            text_color = COLOR_PROMOTED_TEXT if is_promoted else (
                COLOR_SENTE_TEXT if player == 0 else COLOR_GOTE_TEXT
            )
            # 1文字目
            text1 = self.small_font.render(name[0], True, text_color)
            rect1 = text1.get_rect(center=(pos[0], pos[1] - radius // 3))
            surface.blit(text1, rect1)
            # 2文字目
            text2 = self.small_font.render(name[1], True, text_color)
            rect2 = text2.get_rect(center=(pos[0], pos[1] + radius // 3))
            surface.blit(text2, rect2)
        else:
            text_color = COLOR_PROMOTED_TEXT if is_promoted else (
                COLOR_SENTE_TEXT if player == 0 else COLOR_GOTE_TEXT
            )
            text = self.font.render(name, True, text_color)
            text_rect = text.get_rect(center=pos)
            surface.blit(text, text_rect)

    def draw_marker(self, surface: pygame.Surface, x: int, y: int,
                    color: tuple, radius_ratio: float = 0.3):
        """マーカーを描画（選択、移動先など）"""
        pos = self.board_to_pixel(x, y)
        radius = int(self.cell_size * radius_ratio)

        # 半透明の円
        marker_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(marker_surface, color, (radius, radius), radius)
        surface.blit(marker_surface, (pos[0] - radius, pos[1] - radius))

    def draw_state(self, surface: pygame.Surface, state: GameState,
                   selected: Optional[tuple[int, int]] = None,
                   move_targets: Optional[list[tuple[int, int]]] = None,
                   shoot_targets: Optional[list[tuple[int, int]]] = None):
        """ゲーム状態を描画"""
        # 盤面
        self.draw_board(surface)

        # 移動先マーカー（駒の下に描画）
        if move_targets:
            for x, y in move_targets:
                self.draw_marker(surface, x, y, COLOR_MOVE_TARGET)

        # 選択マーカー（駒の下に描画）
        if selected:
            self.draw_marker(surface, selected[0], selected[1], COLOR_SELECTED, 0.45)

        # 駒
        for x in range(19):
            for y in range(19):
                piece_data = state.board.get(x, y)
                if piece_data:
                    piece_id, player = piece_data
                    # 成り駒判定（盤面のis_promotedフラグを使用）
                    is_promoted = state.board.get_promoted(x, y)
                    self.draw_piece(surface, x, y, piece_id, player, is_promoted)

        # 射撃対象マーカー（駒の上に描画して見えるように）
        if shoot_targets:
            for x, y in shoot_targets:
                self.draw_marker(surface, x, y, COLOR_SHOOT_TARGET, 0.4)


class InfoPanel:
    """情報パネル描画クラス"""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.font: Optional[pygame.font.Font] = None

    def init_fonts(self):
        """フォント初期化"""
        import os
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        font_path = None
        for path in font_paths:
            if os.path.exists(path):
                font_path = path
                break
        self.font = pygame.font.Font(font_path, 18) if font_path else pygame.font.Font(None, 18)

    def draw(self, surface: pygame.Surface, state: GameState,
             status_text: str = "", show_promotion_buttons: bool = False):
        """情報パネルを描画"""
        surface.fill((50, 50, 50))

        if not self.font:
            return

        y_offset = 10

        # 手番表示
        turn_text = "先手番" if state.current_player == 0 else "後手番"
        turn_color = (255, 255, 255)
        text = self.font.render(turn_text, True, turn_color)
        surface.blit(text, (10, y_offset))
        y_offset += 30

        # 手数表示
        move_text = f"手数: {state.move_count}"
        text = self.font.render(move_text, True, (200, 200, 200))
        surface.blit(text, (10, y_offset))
        y_offset += 40

        # ステータス
        if status_text:
            text = self.font.render(status_text, True, (255, 255, 100))
            surface.blit(text, (10, y_offset))
            y_offset += 30

        # 成り選択ボタン
        if show_promotion_buttons:
            y_offset += 20
            self._draw_button(surface, 10, y_offset, 80, 30, "成る (Y)", (100, 200, 100))
            self._draw_button(surface, 100, y_offset, 90, 30, "成らない (N)", (200, 100, 100))
            self.promotion_button_rects = {
                "promote": pygame.Rect(10, y_offset, 80, 30),
                "no_promote": pygame.Rect(100, y_offset, 90, 30),
            }
        else:
            self.promotion_button_rects = {}

        # キーバインドヘルプ（下部に表示）
        help_lines = [
            "--- キー操作 ---",
            "U: 待った（1手戻す）",
            "R: リスタート",
            "S: 射撃スキップ",
            "ESC: メニューに戻る",
        ]
        help_y = self.height - len(help_lines) * 22 - 10
        for line in help_lines:
            text = self.font.render(line, True, (150, 150, 150))
            surface.blit(text, (10, help_y))
            help_y += 22

    def _draw_button(self, surface: pygame.Surface, x: int, y: int,
                     width: int, height: int, text: str, color: tuple):
        """ボタンを描画"""
        pygame.draw.rect(surface, color, (x, y, width, height))
        pygame.draw.rect(surface, (255, 255, 255), (x, y, width, height), 2)
        if self.font:
            text_surface = self.font.render(text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(x + width // 2, y + height // 2))
            surface.blit(text_surface, text_rect)

    def get_promotion_click(self, panel_x: int, panel_y: int) -> Optional[bool]:
        """成りボタンのクリック判定（Trueなら成る、Falseなら成らない、Noneなら無関係）"""
        if not hasattr(self, 'promotion_button_rects') or not self.promotion_button_rects:
            return None
        if self.promotion_button_rects["promote"].collidepoint(panel_x, panel_y):
            return True
        if self.promotion_button_rects["no_promote"].collidepoint(panel_x, panel_y):
            return False
        return None
