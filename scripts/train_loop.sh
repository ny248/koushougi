#!/bin/bash
# 10000ゲームまで訓練を継続するループスクリプト

cd /Users/kichiguchinaoki/github/koushougi

TOTAL_GAMES=10000
GAMES_PER_RUN=500

current_game=0

while [ $current_game -lt $TOTAL_GAMES ]; do
    echo "=== Starting training batch (current: $current_game) ==="
    
    python scripts/train.py reinforce \
        --output models/koushougi_rl_v4 \
        --games $GAMES_PER_RUN \
        --lite \
        --device auto \
        --minimax-depth 1 \
        --save-every 50 \
        --epsilon 0.5 \
        --epsilon-decay 0.998 \
        --epsilon-min 0.1 \
        --resume
    
    # チェックポイントから現在のゲーム数を取得
    current_game=$(python -c "
import torch
from pathlib import Path
checkpoints = sorted(Path('models/koushougi_rl_v4').glob('checkpoint_*.pth'))
if checkpoints:
    cp = torch.load(checkpoints[-1], map_location='cpu')
    print(cp.get('game', 0))
else:
    print(0)
" 2>/dev/null || echo "0")
    
    echo "=== Completed batch. Total games: $current_game ==="
    sleep 2
done

echo "=== Training completed: $TOTAL_GAMES games ==="
