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
