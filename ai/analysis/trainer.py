"""継続的訓練ループ"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from multiprocessing import Pool, cpu_count

from ai.battle import run_battle
from ai.greedy.player import GreedyPlayer
from ai.greedy.piece_values import PIECE_VALUES
from ai.analysis.kifu_analyzer import KifuAnalyzer
from ai.analysis.value_learner import ValueLearner, PIECE_NAMES
from config import AI_MAX_TURNS


@dataclass
class TrainingConfig:
    """訓練設定"""
    games_per_round: int = 200        # 1ラウンドあたりの対局数
    max_rounds: int = 10              # 最大ラウンド数
    min_samples: int = 10             # 価値調整に必要な最小サンプル数
    scale_factor: float = 100.0       # 敗北率偏差 → 価値変換係数
    max_adjustment: float = 50.0      # 1ラウンドでの最大調整幅
    epsilon: float = 0.05             # 探索率
    n_jobs: int = 0                   # 並列数（0=CPU数）
    max_turns: int = AI_MAX_TURNS     # 対局の最大ターン数
    output_dir: str = "data/training" # 出力ディレクトリ


@dataclass
class RoundResult:
    """1ラウンドの結果"""
    round_num: int
    games: int
    sente_wins: int
    gote_wins: int
    draws: int
    elapsed_sec: float
    values: dict[int, int] = field(default_factory=dict)


def _run_single_game(args: tuple) -> dict:
    """1対局を実行（並列処理用）"""
    values, max_turns, epsilon = args

    # カスタム価値を使うGreedyPlayer
    class CustomGreedyPlayer(GreedyPlayer):
        def __init__(self):
            super().__init__(epsilon=epsilon)
            self._custom_values = values

    # get_piece_valueをオーバーライドするため、一時的にモジュールを書き換え
    import ai.greedy.piece_values as pv
    original_values = pv.PIECE_VALUES.copy()
    pv.PIECE_VALUES.update(values)

    try:
        sente_ai = GreedyPlayer(epsilon=epsilon)
        gote_ai = GreedyPlayer(epsilon=epsilon)
        record = run_battle(sente_ai, gote_ai, max_turns)
        return record.to_dict()
    finally:
        pv.PIECE_VALUES.clear()
        pv.PIECE_VALUES.update(original_values)


class Trainer:
    """継続的訓練"""

    def __init__(self, config: TrainingConfig | None = None):
        self.config = config or TrainingConfig()
        self.current_values = PIECE_VALUES.copy()
        self.history: list[RoundResult] = []

    def run(self, verbose: bool = True) -> dict[int, int]:
        """訓練を実行"""
        n_jobs = self.config.n_jobs if self.config.n_jobs > 0 else cpu_count()
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if verbose:
            print(f"=== 訓練開始 ===")
            print(f"ラウンド数: {self.config.max_rounds}")
            print(f"対局数/ラウンド: {self.config.games_per_round}")
            print(f"並列数: {n_jobs}")
            print(f"探索率: {self.config.epsilon:.1%}")
            print()

        for round_num in range(1, self.config.max_rounds + 1):
            result = self._run_round(round_num, n_jobs, verbose)
            self.history.append(result)

            # チェックポイント保存
            self._save_checkpoint(output_dir, round_num)

        # 最終結果を保存
        self._save_final(output_dir)

        return self.current_values

    def _run_round(self, round_num: int, n_jobs: int, verbose: bool) -> RoundResult:
        """1ラウンドを実行"""
        if verbose:
            print(f"--- ラウンド {round_num}/{self.config.max_rounds} ---")

        start_time = time.perf_counter()

        # 対戦
        game_args = [
            (self.current_values, self.config.max_turns, self.config.epsilon)
            for _ in range(self.config.games_per_round)
        ]

        with Pool(n_jobs) as pool:
            results = list(pool.imap_unordered(_run_single_game, game_args))

        elapsed = time.perf_counter() - start_time

        # 集計
        sente_wins = sum(1 for r in results if r["winner"] == 0)
        gote_wins = sum(1 for r in results if r["winner"] == 1)
        draws = sum(1 for r in results if r["winner"] is None)

        if verbose:
            print(f"対戦結果: 先手{sente_wins} - 後手{gote_wins} - 引分{draws} ({elapsed:.1f}s)")

        # 分析
        analyzer = KifuAnalyzer()
        for game in results:
            analyzer._analyze_game(game)

        # 学習
        learner = ValueLearner(base_values=self.current_values)
        new_values = learner.learn(
            analyzer.get_result(),
            min_samples=self.config.min_samples,
            scale_factor=self.config.scale_factor,
            max_adjustment=self.config.max_adjustment,
        )

        # 変化を表示
        if verbose:
            self._print_changes(new_values)

        self.current_values = new_values

        return RoundResult(
            round_num=round_num,
            games=self.config.games_per_round,
            sente_wins=sente_wins,
            gote_wins=gote_wins,
            draws=draws,
            elapsed_sec=elapsed,
            values=new_values.copy(),
        )

    def _print_changes(self, new_values: dict[int, int]) -> None:
        """主要な変化を表示"""
        changes = []
        for piece_id in self.current_values:
            old = self.current_values[piece_id]
            new = new_values.get(piece_id, old)
            diff = new - old
            if diff != 0:
                changes.append((abs(diff), piece_id, old, new, diff))

        if not changes:
            print("変化なし")
            return

        changes.sort(reverse=True)
        print("主要な変化:")
        for _, piece_id, old, new, diff in changes[:5]:
            name = PIECE_NAMES.get(piece_id, "???")
            sign = "+" if diff > 0 else ""
            print(f"  {name}({piece_id}): {old} → {new} ({sign}{diff})")
        print()

    def _save_checkpoint(self, output_dir: Path, round_num: int) -> None:
        """チェックポイントを保存"""
        checkpoint = {
            "round": round_num,
            "values": self.current_values,
            "history": [
                {
                    "round": r.round_num,
                    "games": r.games,
                    "sente_wins": r.sente_wins,
                    "gote_wins": r.gote_wins,
                    "draws": r.draws,
                    "elapsed_sec": r.elapsed_sec,
                }
                for r in self.history
            ],
        }

        with open(output_dir / f"checkpoint_r{round_num:03d}.json", "w") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)

    def _save_final(self, output_dir: Path) -> None:
        """最終結果を保存"""
        # JSON形式
        with open(output_dir / "final_values.json", "w") as f:
            json.dump(self.current_values, f, ensure_ascii=False, indent=2)

        # Python形式
        learner = ValueLearner(base_values=PIECE_VALUES)
        code = learner.generate_python_code(self.current_values)
        with open(output_dir / "trained_values.py", "w") as f:
            f.write(code)

        print(f"結果を保存: {output_dir}")
