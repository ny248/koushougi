"""AI同士の対戦と棋譜出力"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from backend.rules.game_engine import GameEngine
from ai.base import BaseAI
from ai.random import RandomPlayer
from config import AI_MAX_TURNS


@dataclass
class MoveRecord:
    """1手の記録"""
    turn: int
    player: int
    from_pos: tuple[int, int]
    to_pos: tuple[int, int]
    promote: bool = False
    captured: Optional[int] = None
    shoot_target: Optional[tuple[int, int]] = None
    shoot_kills: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "player": self.player,
            "from": f"{chr(ord('a') + self.from_pos[0])}{self.from_pos[1] + 1}",
            "to": f"{chr(ord('a') + self.to_pos[0])}{self.to_pos[1] + 1}",
            "promote": self.promote,
            "captured": self.captured,
            "shoot": f"{chr(ord('a') + self.shoot_target[0])}{self.shoot_target[1] + 1}" if self.shoot_target else None,
            "shoot_kills": self.shoot_kills if self.shoot_kills else None,
        }


@dataclass
class GameRecord:
    """対局記録"""
    moves: list[MoveRecord] = field(default_factory=list)
    winner: Optional[int] = None
    total_turns: int = 0
    elapsed_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "total_turns": self.total_turns,
            "elapsed_ms": self.elapsed_ms,
            "moves": [m.to_dict() for m in self.moves],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def run_battle(sente_ai: BaseAI, gote_ai: BaseAI, max_turns: int = AI_MAX_TURNS) -> GameRecord:
    """
    AI同士で対戦して棋譜を返す

    Args:
        sente_ai: 先手AI
        gote_ai: 後手AI
        max_turns: 最大ターン数

    Returns:
        GameRecord: 対局記録
    """
    engine = GameEngine()
    record = GameRecord()
    start_time = time.perf_counter()

    turn = 0
    while turn < max_turns and not engine.is_game_over:
        player = engine.current_player
        ai = sente_ai if player == 0 else gote_ai

        # 移動選択
        move = ai.choose_move(engine)
        if move is None:
            break

        from_pos = move["from"]
        to_pos = move["to"]
        promote = move.get("promote", False)

        # 移動実行
        result = engine.move(from_pos, to_pos, promote=promote)
        if not result.success:
            break

        # 記録作成
        move_record = MoveRecord(
            turn=turn,
            player=player,
            from_pos=from_pos,
            to_pos=to_pos,
            promote=promote,
            captured=result.captured,
        )

        # 射撃処理
        shoot_targets = engine.get_shoot_targets()
        if shoot_targets:
            target = ai.choose_shoot(engine, shoot_targets)
            if target:
                shoot_result = engine.shoot([target])
                move_record.shoot_target = target
                move_record.shoot_kills = shoot_result.path_kills or []
            else:
                engine.skip_shoot()

        record.moves.append(move_record)
        turn += 1

    record.winner = engine.winner
    record.total_turns = turn
    record.elapsed_ms = (time.perf_counter() - start_time) * 1000

    return record


def run_battles(n_games: int, sente_ai: Optional[BaseAI] = None,
                gote_ai: Optional[BaseAI] = None, max_turns: int = AI_MAX_TURNS,
                verbose: bool = True) -> list[GameRecord]:
    """
    複数対局を実行

    Args:
        n_games: 対局数
        sente_ai: 先手AI（省略時はRandomPlayer）
        gote_ai: 後手AI（省略時はRandomPlayer）
        max_turns: 1局あたりの最大ターン数
        verbose: 進捗表示

    Returns:
        list[GameRecord]: 対局記録のリスト
    """
    if sente_ai is None:
        sente_ai = RandomPlayer()
    if gote_ai is None:
        gote_ai = RandomPlayer()

    records = []
    sente_wins = 0
    gote_wins = 0
    draws = 0

    total_start = time.perf_counter()

    for i in range(n_games):
        record = run_battle(sente_ai, gote_ai, max_turns)
        records.append(record)

        if record.winner == 0:
            sente_wins += 1
        elif record.winner == 1:
            gote_wins += 1
        else:
            draws += 1

        if verbose and (i + 1) % 10 == 0:
            print(f"Game {i + 1}/{n_games}: 先手{sente_wins} - 後手{gote_wins} - 引分{draws}")

    total_elapsed = (time.perf_counter() - total_start) * 1000

    if verbose:
        print(f"\n=== 結果 ===")
        print(f"対局数: {n_games}")
        print(f"先手勝利: {sente_wins} ({100*sente_wins/n_games:.1f}%)")
        print(f"後手勝利: {gote_wins} ({100*gote_wins/n_games:.1f}%)")
        print(f"引き分け: {draws} ({100*draws/n_games:.1f}%)")
        print(f"総時間: {total_elapsed:.1f}ms ({total_elapsed/n_games:.2f}ms/局)")

    return records


def main():
    """テスト実行"""
    import argparse

    parser = argparse.ArgumentParser(description="AI同士の対戦")
    parser.add_argument("-n", "--games", type=int, default=10, help="対局数")
    parser.add_argument("-o", "--output", type=str, help="棋譜出力ファイル（JSON）")
    parser.add_argument("--max-turns", type=int, default=AI_MAX_TURNS, help="最大ターン数")
    args = parser.parse_args()

    records = run_battles(args.games, max_turns=args.max_turns)

    if args.output:
        output_data = {
            "games": [r.to_dict() for r in records],
            "summary": {
                "total_games": len(records),
                "sente_wins": sum(1 for r in records if r.winner == 0),
                "gote_wins": sum(1 for r in records if r.winner == 1),
                "draws": sum(1 for r in records if r.winner is None),
            }
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n棋譜を保存: {args.output}")


if __name__ == "__main__":
    main()
