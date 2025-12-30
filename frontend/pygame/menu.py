"""対局設定メニュー"""

import pygame
import random
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class PlayerType(Enum):
    HUMAN = "human"
    AI = "ai"


@dataclass
class GameConfig:
    """対局設定"""
    sente_type: PlayerType  # 先手
    gote_type: PlayerType   # 後手

    @property
    def is_human_turn(self) -> callable:
        """指定プレイヤーが人間かどうかを返す関数"""
        def check(player: int) -> bool:
            if player == 0:
                return self.sente_type == PlayerType.HUMAN
            else:
                return self.gote_type == PlayerType.HUMAN
        return check


class MenuScreen:
    """対局設定メニュー画面"""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.font: Optional[pygame.font.Font] = None
        self.title_font: Optional[pygame.font.Font] = None

        # 選択状態
        self.sente_type = PlayerType.HUMAN
        self.gote_type = PlayerType.AI
        self.selected_row = 0  # 0: 先手, 1: 後手, 2: 開始

        # ボタン領域
        self.buttons: dict[str, pygame.Rect] = {}

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

        if font_path:
            self.font = pygame.font.Font(font_path, 24)
            self.title_font = pygame.font.Font(font_path, 36)
        else:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)

    def handle_event(self, event: pygame.event.Event) -> Optional[GameConfig]:
        """
        イベント処理

        Returns:
            GameConfig: ゲーム開始時に設定を返す、それ以外はNone
        """
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selected_row = (self.selected_row - 1) % 3
            elif event.key == pygame.K_DOWN:
                self.selected_row = (self.selected_row + 1) % 3
            elif event.key == pygame.K_LEFT or event.key == pygame.K_RIGHT:
                if self.selected_row == 0:
                    self.sente_type = PlayerType.AI if self.sente_type == PlayerType.HUMAN else PlayerType.HUMAN
                elif self.selected_row == 1:
                    self.gote_type = PlayerType.AI if self.gote_type == PlayerType.HUMAN else PlayerType.HUMAN
            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                if self.selected_row == 2:
                    return GameConfig(self.sente_type, self.gote_type)
            elif event.key == pygame.K_r:
                # ランダム先手後手
                if random.random() < 0.5:
                    self.sente_type, self.gote_type = self.gote_type, self.sente_type

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                return self.handle_click(event.pos)

        return None

    def handle_click(self, pos: tuple[int, int]) -> Optional[GameConfig]:
        """クリック処理"""
        for name, rect in self.buttons.items():
            if rect.collidepoint(pos):
                if name == "sente_human":
                    self.sente_type = PlayerType.HUMAN
                elif name == "sente_ai":
                    self.sente_type = PlayerType.AI
                elif name == "gote_human":
                    self.gote_type = PlayerType.HUMAN
                elif name == "gote_ai":
                    self.gote_type = PlayerType.AI
                elif name == "random":
                    if random.random() < 0.5:
                        self.sente_type, self.gote_type = self.gote_type, self.sente_type
                elif name == "start":
                    return GameConfig(self.sente_type, self.gote_type)
        return None

    def draw(self, surface: pygame.Surface):
        """描画"""
        surface.fill((40, 40, 50))

        if not self.font:
            return

        center_x = self.width // 2
        y = 60

        # タイトル
        title = self.title_font.render("広将棋", True, (255, 255, 255))
        title_rect = title.get_rect(center=(center_x, y))
        surface.blit(title, title_rect)
        y += 80

        # 説明
        desc = self.font.render("対局設定", True, (200, 200, 200))
        desc_rect = desc.get_rect(center=(center_x, y))
        surface.blit(desc, desc_rect)
        y += 60

        self.buttons.clear()

        # 先手設定
        row_color = (100, 150, 100) if self.selected_row == 0 else (80, 80, 90)
        self._draw_player_row(surface, y, "▲先手:", self.sente_type, "sente", row_color)
        y += 60

        # 後手設定
        row_color = (100, 150, 100) if self.selected_row == 1 else (80, 80, 90)
        self._draw_player_row(surface, y, "△後手:", self.gote_type, "gote", row_color)
        y += 80

        # ランダムボタン
        random_btn = self._draw_button(surface, center_x, y, "先後ランダム入替 (R)", (100, 100, 120))
        self.buttons["random"] = random_btn
        y += 60

        # 開始ボタン
        start_color = (80, 150, 80) if self.selected_row == 2 else (60, 120, 60)
        start_btn = self._draw_button(surface, center_x, y, "ゲーム開始", start_color, width=200, height=50)
        self.buttons["start"] = start_btn
        y += 80

        # 操作説明
        help_texts = [
            "操作: ↑↓で選択 / ←→で切替 / Enter/クリックで決定",
        ]
        for text in help_texts:
            help_surf = self.font.render(text, True, (150, 150, 150))
            help_rect = help_surf.get_rect(center=(center_x, y))
            surface.blit(help_surf, help_rect)
            y += 30

    def _draw_player_row(self, surface: pygame.Surface, y: int, label: str,
                         current_type: PlayerType, prefix: str, bg_color: tuple):
        """プレイヤー設定行を描画"""
        center_x = self.width // 2
        row_width = 350
        row_height = 45

        # 背景
        row_rect = pygame.Rect(center_x - row_width // 2, y - row_height // 2, row_width, row_height)
        pygame.draw.rect(surface, bg_color, row_rect, border_radius=5)

        # ラベル
        label_surf = self.font.render(label, True, (255, 255, 255))
        label_rect = label_surf.get_rect(midleft=(center_x - 150, y))
        surface.blit(label_surf, label_rect)

        # 人間ボタン
        human_color = (100, 180, 100) if current_type == PlayerType.HUMAN else (70, 70, 80)
        human_btn = self._draw_button(surface, center_x + 20, y, "人間", human_color, width=80, height=35)
        self.buttons[f"{prefix}_human"] = human_btn

        # AIボタン
        ai_color = (100, 180, 100) if current_type == PlayerType.AI else (70, 70, 80)
        ai_btn = self._draw_button(surface, center_x + 120, y, "AI", ai_color, width=80, height=35)
        self.buttons[f"{prefix}_ai"] = ai_btn

    def _draw_button(self, surface: pygame.Surface, x: int, y: int, text: str,
                     color: tuple, width: int = 150, height: int = 40) -> pygame.Rect:
        """ボタン描画"""
        rect = pygame.Rect(x - width // 2, y - height // 2, width, height)
        pygame.draw.rect(surface, color, rect, border_radius=5)
        pygame.draw.rect(surface, (200, 200, 200), rect, 1, border_radius=5)

        text_surf = self.font.render(text, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=(x, y))
        surface.blit(text_surf, text_rect)

        return rect
