# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

広将棋 (Koushougi) GUI Battle Project - A Python GUI application for playing Koushougi (a historical Japanese board game invented by Ogyū Sorai) locally between two human players.

**Current Status**: Early prototype with basic board rendering and piece selection. Core game logic not yet implemented.

## Development Commands

No build system configured yet. Run the main application with:
```bash
python src/main.py  # (when implemented)
```

The project uses Python with tkinter (standard library) for GUI. No external dependencies currently.

## Architecture

### Planned Directory Structure
- `src/app/` - Application startup, window management, screen transitions
- `src/domain/` - Core game logic: Board, Pieces, Turn management
- `src/rules/` - Rule validation and legal move generation
- `src/ui/` - GUI rendering and user input handling
- `src/utils/` - Shared utilities
- `assets/` - Board images, piece images, sound effects
- `tests/` - Unit and integration tests

### Key Concepts
- **19x19 intersection grid** - Pieces placed on intersections (like Go/Xiangqi), not squares
- **34 unique piece types** - Each with distinct movement rules (see GAMERULE.md)
- **No captured piece reuse** - Unlike Shogi, captured pieces cannot be dropped back
- **Promotion system** - Pieces promote when entering enemy territory or capturing specific pieces
- **Win condition** - Capture opponent's 将 (General) + either 中軍/旗 (Central Army/Flag), unless 中軍 promotes to 帥

### Board Rendering
- Pieces rendered as circular stones (black/white based on owner)
- Japanese piece names displayed as text overlay
- Promoted pieces shown in red text
- Opponent's pieces rotated 180 degrees for readability

## Key Files

- [GAMERULE.md](GAMERULE.md) - Complete game rules with all 34 piece movements, promotion conditions, and special abilities
- [.codex/AGENTS.md](.codex/AGENTS.md) - AI assistant working guidelines for this project

## Working Guidelines (from .codex/AGENTS.md)

- **Priority**: Local human-vs-human play first
- **Language**: Python
- **Efficiency**: Minimize web access, store data locally, avoid redundant requests
- **Communication**: Keep concise, confirm before major changes

## Development Notes

- 判断に迷う点や後で見直すべき点は `docs/notes/dev_notes.md` にメモして先に進む
- ユーティリティやヘルパーは実際の使用場面が明確になってから作成する
- 必要だと分かっていながら実装をサボらない。あまりに大変そうならユーザに確認を取る

## アンチパターン

### 二重管理の禁止

駒の定義（ID、名前、成り先、移動パターンなど）は `backend/domain/` に一元管理されている。
他の場所で同じ情報を再定義してはならない。

**悪い例:**
```python
# ai/greedy/piece_values.py で成り関係を再定義
PROMOTION_MAP = {
    1: 35,   # 将 → 帥
    2: 36,   # 記室 → 軍師
    ...
}
```

**良い例:**
```python
# backend/domain/piece_registry から取得
from backend.domain.piece_registry import get_piece

piece = get_piece(piece_id)
promoted_id = piece.promotes_to  # 成り先ID
```

### データの権威ある出典

| データ | 出典 |
|--------|------|
| ゲームルール | `GAMERULE.md` |
| 駒の定義 | `backend/domain/piece_registry.py` |
| 駒の詳細 | `src/domain/pieces/*.py` |
| 設定定数 | `config.py` |
