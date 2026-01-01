"""訓練フェーズ定義

Pythonネイティブな訓練フェーズの定義。
JSONテンプレートではなく、型安全なPydanticモデルとして定義。
"""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Union

from pydantic import BaseModel

from ai import get_ai_player
from ai.base import BaseAI


class PhaseResult(BaseModel):
    """フェーズ実行結果"""

    success: bool
    output_dir: Optional[Path] = None
    model_path: Optional[Path] = None
    games_file: Optional[Path] = None
    win_rate: Optional[float] = None
    passed: bool = True

    class Config:
        arbitrary_types_allowed = True


class PhaseContext:
    """フェーズ実行時のコンテキスト"""

    def __init__(
        self,
        output_dir: Path,
        logger,
        latest_model: Optional[Path] = None,
        best_model: Optional[Path] = None,
        best_win_rate: float = 0.0,
        all_game_files: Optional[List[Path]] = None,
        variables: Optional[dict] = None,
        save_callback: Optional[Callable[[], None]] = None,
    ):
        self.output_dir = output_dir
        self.logger = logger
        self.latest_model = latest_model
        self.best_model = best_model
        self.best_win_rate = best_win_rate
        self.all_game_files = all_game_files or []
        self.variables = variables or {}
        self._save_callback = save_callback

        # フェーズ内進捗
        self.current_phase_name: Optional[str] = None
        self.current_phase_type: Optional[str] = None
        self.current_phase_completed: int = 0
        self.current_phase_total: int = 0

    def start_phase(self, name: str, phase_type: str, total: int):
        """フェーズ開始を記録"""
        self.current_phase_name = name
        self.current_phase_type = phase_type
        self.current_phase_completed = 0
        self.current_phase_total = total

    def update_phase_progress(self, completed: int):
        """フェーズ内進捗を更新して保存"""
        self.current_phase_completed = completed
        if self._save_callback:
            self._save_callback()

    def finish_phase(self):
        """フェーズ完了を記録"""
        self.current_phase_name = None
        self.current_phase_type = None
        self.current_phase_completed = 0
        self.current_phase_total = 0

    def register_games(self, path: Path):
        """棋譜ファイルを登録"""
        if path not in self.all_game_files:
            self.all_game_files.append(path)

    def update_model(self, path: Path):
        """最新モデルを更新"""
        self.latest_model = path

    def update_best(self, path: Path, win_rate: float):
        """ベストモデルを更新"""
        self.best_model = path
        self.best_win_rate = win_rate


# =============================================================================
# プレイヤーファクトリ
# =============================================================================


def minimax(depth: int = 1, epsilon: float = 0.0) -> Callable[[PhaseContext], BaseAI]:
    """Minimaxプレイヤーファクトリを返す"""

    def factory(ctx: PhaseContext) -> BaseAI:
        return get_ai_player("minimax", depth=depth, epsilon=epsilon)

    return factory


def neural(
    model: str = "@latest",
    epsilon: Union[float, Callable[[PhaseContext], float]] = 0.0,
) -> Callable[[PhaseContext], BaseAI]:
    """Neuralプレイヤーファクトリを返す

    Args:
        model: "@latest", "@best", またはパス
        epsilon: 探索率（固定値またはコンテキストから計算する関数）
    """

    def factory(ctx: PhaseContext) -> BaseAI:
        # epsilon解決
        eps = epsilon(ctx) if callable(epsilon) else epsilon

        # モデルパス解決
        if model == "@latest":
            model_path = ctx.latest_model
        elif model == "@best":
            model_path = ctx.best_model
        else:
            model_path = Path(model)

        os.environ.setdefault("KMP_DISABLE_SHM", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")

        player = get_ai_player("neural", epsilon=eps)
        if model_path and model_path.exists():
            player.load_checkpoint(str(model_path))
        return player

    return factory


def random_player() -> Callable[[PhaseContext], BaseAI]:
    """Randomプレイヤーファクトリを返す"""

    def factory(ctx: PhaseContext) -> BaseAI:
        return get_ai_player("random")

    return factory


# =============================================================================
# データソースヘルパー
# =============================================================================


def from_phase(phase_name: str) -> Callable[[PhaseContext], List[Path]]:
    """指定フェーズの棋譜を返すファクトリ"""

    def factory(ctx: PhaseContext) -> List[Path]:
        path = ctx.output_dir / phase_name / "games.jsonl"
        return [path] if path.exists() else []

    return factory


def all_games() -> Callable[[PhaseContext], List[Path]]:
    """全棋譜を返すファクトリ"""

    def factory(ctx: PhaseContext) -> List[Path]:
        return list(ctx.all_game_files)

    return factory


# =============================================================================
# フェーズ基底クラス
# =============================================================================


class Phase(ABC):
    """フェーズ基底クラス"""

    name: Union[str, Callable[[PhaseContext], str]]

    def get_name(self, ctx: PhaseContext) -> str:
        """フェーズ名を取得"""
        if callable(self.name):
            return self.name(ctx)
        return self.name

    @abstractmethod
    def execute(self, ctx: PhaseContext) -> PhaseResult:
        """フェーズを実行"""
        pass


# =============================================================================
# 具体フェーズ
# =============================================================================


@dataclass
class GeneratePhase(Phase):
    """棋譜生成フェーズ"""

    name: Union[str, Callable[[PhaseContext], str]]
    games: int
    sente: Callable[[PhaseContext], BaseAI]
    gote: Callable[[PhaseContext], BaseAI]
    game_timeout: float = 120.0
    turn_timeout: float = 60.0

    def execute(self, ctx: PhaseContext) -> PhaseResult:
        from scripts.lib.logger import GameLogger
        from scripts.battle import run_games

        phase_name = self.get_name(ctx)
        output_dir = ctx.output_dir / phase_name
        output_dir.mkdir(parents=True, exist_ok=True)
        games_file = output_dir / "games.jsonl"

        # フェーズ内進捗の開始位置を決定
        start_from = 0
        if ctx.current_phase_name == phase_name and ctx.current_phase_completed > 0:
            start_from = ctx.current_phase_completed
            ctx.logger.info(f"棋譜生成: {self.games}局（{start_from}局目から再開）")
        else:
            ctx.logger.info(f"棋譜生成: {self.games}局")
            ctx.start_phase(phase_name, "generate", self.games)

        player1 = self.sente(ctx)
        player2 = self.gote(ctx)

        # 1局ごとに進捗を保存するコールバック
        def on_progress(i, record, stats):
            ctx.update_phase_progress(i + 1)

        game_logger = GameLogger(ctx.logger, verbose=False)
        run_games(
            player1,
            player2,
            n_games=self.games,
            logger=game_logger,
            turn_timeout=self.turn_timeout,
            game_timeout=self.game_timeout,
            output_path=games_file,
            output_format="jsonl",
            start_from=start_from,
            progress_callback=on_progress,
        )

        success = games_file.exists()
        if success:
            ctx.register_games(games_file)

        ctx.finish_phase()

        return PhaseResult(
            success=success,
            output_dir=output_dir,
            games_file=games_file if success else None,
        )


@dataclass
class TrainPhase(Phase):
    """訓練フェーズ"""

    name: Union[str, Callable[[PhaseContext], str]]
    method: str  # "supervised" | "reinforce" | "td"
    data: Callable[[PhaseContext], List[Path]]
    epochs: int = 20
    batch_size: int = 64
    lr: float = 0.001
    model: Optional[Callable[[PhaseContext], Optional[Path]]] = None
    lite: bool = True
    gamma: float = 0.99  # TD学習用割引率

    def execute(self, ctx: PhaseContext) -> PhaseResult:
        phase_name = self.get_name(ctx)
        output_dir = ctx.output_dir / phase_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # データパス解決
        data_paths = self.data(ctx)
        if not data_paths:
            ctx.logger.error("データが見つかりません")
            return PhaseResult(success=False)

        # 複数データの場合はディレクトリにシンボリックリンク
        if len(data_paths) == 1:
            data_arg = str(data_paths[0])
        else:
            data_dir = output_dir / "data"
            data_dir.mkdir(exist_ok=True)
            for i, p in enumerate(data_paths):
                link = data_dir / f"{i:03d}_{p.stem}.jsonl"
                if not link.exists():
                    link.symlink_to(p.resolve())
            data_arg = str(data_dir)

        cmd = [
            "python",
            "scripts/train.py",
            self.method,
            "--data",
            data_arg,
            "--output",
            str(output_dir),
            "--epochs",
            str(self.epochs),
            "--batch-size",
            str(self.batch_size),
            "--lr",
            str(self.lr),
        ]

        # 継続学習用モデル
        if self.model:
            model_path = self.model(ctx)
            if model_path and model_path.exists():
                cmd.extend(["--load", str(model_path)])

        if self.lite:
            cmd.append("--lite")

        # TD学習用パラメータ
        if self.method == "td":
            cmd.extend(["--gamma", str(self.gamma)])

        ctx.logger.info(f"訓練: {self.method}, {self.epochs}エポック")

        timeout = self.epochs * 600
        try:
            result = subprocess.run(cmd, timeout=timeout, capture_output=False)
            success = result.returncode == 0
        except subprocess.TimeoutExpired:
            ctx.logger.error(f"タイムアウト: {timeout}秒")
            success = False
        except Exception as e:
            ctx.logger.error(f"エラー: {e}")
            success = False

        model_path = None
        if success:
            best_model = output_dir / "best_model.pth"
            if best_model.exists():
                model_path = best_model
                ctx.update_model(best_model)

        return PhaseResult(
            success=success,
            output_dir=output_dir,
            model_path=model_path,
        )


@dataclass
class EvalPhase(Phase):
    """評価フェーズ"""

    name: Union[str, Callable[[PhaseContext], str]]
    model: Callable[[PhaseContext], Optional[Path]]
    games: int = 30
    opponent: Optional[Callable[[PhaseContext], BaseAI]] = None
    game_timeout: float = 120.0
    target_win_rate: float = 0.0
    save_if_best: bool = False

    def execute(self, ctx: PhaseContext) -> PhaseResult:
        from scripts.lib.logger import GameLogger
        from scripts.battle import run_games

        phase_name = self.get_name(ctx)
        output_dir = ctx.output_dir / phase_name
        output_dir.mkdir(parents=True, exist_ok=True)
        games_file = output_dir / "eval_games.jsonl"

        # モデル解決
        model_path = self.model(ctx)
        if not model_path or not model_path.exists():
            ctx.logger.error("評価モデルが見つかりません")
            return PhaseResult(success=False, passed=False)

        # プレイヤー構築
        os.environ.setdefault("KMP_DISABLE_SHM", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")

        player1 = get_ai_player("neural", epsilon=0.0)
        player1.load_checkpoint(str(model_path))

        if self.opponent:
            player2 = self.opponent(ctx)
        else:
            player2 = get_ai_player("minimax", depth=1, epsilon=0.0)

        ctx.logger.info(f"評価: {self.games}局")

        game_logger = GameLogger(ctx.logger, verbose=False)
        run_games(
            player1,
            player2,
            n_games=self.games,
            logger=game_logger,
            game_timeout=self.game_timeout,
            output_path=games_file,
            output_format="jsonl",
        )

        if not games_file.exists():
            return PhaseResult(success=False, passed=False)

        # 勝率計算
        stats = self._collect_stats(games_file)
        win_rate = stats.get("nn_win_rate", 0)

        ctx.logger.info(f"評価結果: 勝率 {win_rate:.1%} ({stats['nn_wins']}/{stats['total']})")

        # 結果保存
        with open(output_dir / "eval_result.json", "w") as f:
            json.dump(
                {
                    "win_rate": win_rate,
                    "stats": stats,
                    "model": str(model_path),
                },
                f,
                indent=2,
            )

        # ベストモデル更新
        if self.save_if_best and win_rate > ctx.best_win_rate:
            ctx.update_best(model_path, win_rate)
            ctx.logger.info(f"新ベスト: {win_rate:.1%}")

        # 閾値チェック
        passed = win_rate >= self.target_win_rate

        return PhaseResult(
            success=True,
            output_dir=output_dir,
            games_file=games_file,
            win_rate=win_rate,
            passed=passed,
        )

    def _collect_stats(self, games_file: Path) -> dict:
        """棋譜ファイルから統計を収集"""
        stats = {
            "total": 0,
            "sente_wins": 0,
            "gote_wins": 0,
            "draws": 0,
            "nn_wins": 0,
            "minimax_wins": 0,
        }

        with open(games_file) as f:
            for line in f:
                game = json.loads(line)
                stats["total"] += 1

                winner = game.get("kifu", {}).get("winner")
                players = game.get("players", {})

                if winner == 0:
                    stats["sente_wins"] += 1
                    if "neural" in players.get("sente", "").lower():
                        stats["nn_wins"] += 1
                    else:
                        stats["minimax_wins"] += 1
                elif winner == 1:
                    stats["gote_wins"] += 1
                    if "neural" in players.get("gote", "").lower():
                        stats["nn_wins"] += 1
                    else:
                        stats["minimax_wins"] += 1
                else:
                    stats["draws"] += 1

        if stats["total"] > 0:
            stats["nn_win_rate"] = stats["nn_wins"] / stats["total"]
            stats["minimax_win_rate"] = stats["minimax_wins"] / stats["total"]

        return stats


@dataclass
class LoopPhase(Phase):
    """ループフェーズ"""

    name: Union[str, Callable[[PhaseContext], str]]
    max_iterations: int
    phases: List[Phase]
    break_condition: Optional[Callable[[PhaseContext, int], bool]] = None

    def execute(self, ctx: PhaseContext) -> PhaseResult:
        ctx.logger.info(f"ループ開始: 最大 {self.max_iterations} イテレーション")

        for i in range(self.max_iterations):
            ctx.variables["iteration"] = i
            ctx.logger.info(f"=== イテレーション {i + 1}/{self.max_iterations} ===")

            for phase in self.phases:
                phase_name = phase.get_name(ctx)
                ctx.logger.info(f"--- フェーズ: {phase_name} ---")

                result = phase.execute(ctx)

                if not result.success:
                    return result

            if self.break_condition and self.break_condition(ctx, i):
                ctx.logger.info("終了条件を満たしました")
                break

        return PhaseResult(success=True)
