"""ニューラルネットワークを使うAIプレイヤー（フェーズ分離型）"""

import random
from typing import Optional
import torch
import torch.nn.functional as F

from backend.rules.game_engine import GameEngine, GamePhase
from backend.domain.game_state import GameState
from backend.domain.action import (
    Action, SelectPieceAction, SelectDestinationAction,
    StopMoveAction, SelectNextStepAction,
    DecidePromotionAction, ShootAction, SkipShootAction
)
from ai.base import BaseAI
from ai.neural.model import (
    create_model, encode_board, pos_to_index, index_to_pos, NUM_SQUARES
)


class NeuralPlayer(BaseAI):
    """ニューラルネットワークを使うAIプレイヤー"""

    def __init__(self, model=None, device="cpu", epsilon=0.1, temperature=1.0):
        """
        Args:
            model: 学習済みモデル（Noneなら新規作成）
            device: デバイス
            epsilon: ランダムに手を選ぶ確率
            temperature: softmaxの温度（高いほど探索的）
        """
        self.model = model or create_model(lite=True, device=device)
        self.device = device
        self.epsilon = epsilon
        self.temperature = temperature

    def choose_action(self, state: GameState) -> Action:
        """現在の状態から次のアクションを選択"""
        from backend.rules.game_engine import GameEngine

        engine = GameEngine(state)
        phase = engine.phase

        if phase == GamePhase.PIECE_SELECT:
            pos = self.choose_piece(engine)
            return SelectPieceAction(pos=pos)

        elif phase == GamePhase.DEST_SELECT:
            pos = self.choose_destination(engine)
            return SelectDestinationAction(pos=pos)

        elif phase == GamePhase.MULTI_STEP_MOVE:
            if engine.can_stop_now() and self.choose_stop(engine):
                return StopMoveAction()
            pos = self.choose_next_step(engine)
            return SelectNextStepAction(pos=pos)

        elif phase == GamePhase.PROMOTION:
            promote = self.choose_promotion(engine)
            return DecidePromotionAction(promote=promote)

        elif phase == GamePhase.SHOOTING:
            target = self.choose_shoot_target(engine)
            if target is None:
                return SkipShootAction()
            return ShootAction(target=target)

        else:
            raise ValueError(f"Unexpected phase: {phase}")

    def choose_piece(self, engine: GameEngine) -> tuple[int, int]:
        """動かす駒を選択"""
        movable = engine.get_movable_pieces()
        if not movable:
            return (0, 0)

        # ε確率でランダム
        if random.random() < self.epsilon:
            return random.choice(movable)

        # 盤面をエンコード
        board_tensor = encode_board(engine).unsqueeze(0).to(self.device)

        # 推論
        self.model.eval()
        with torch.no_grad():
            policy_logits, _ = self.model(board_tensor, phase="piece")

        # 合法手のみをマスク
        legal_indices = [pos_to_index(x, y) for x, y in movable]
        logits = policy_logits[0, legal_indices]

        # 温度付きsoftmax
        probs = F.softmax(logits / self.temperature, dim=0)

        # サンプリング
        chosen_idx = torch.multinomial(probs, 1).item()
        return movable[chosen_idx]

    def choose_destination(self, engine: GameEngine) -> tuple[int, int]:
        """移動先を選択"""
        dests = engine.get_legal_destinations()
        if not dests:
            return (0, 0)

        # ε確率でランダム
        if random.random() < self.epsilon:
            return random.choice(dests)

        # 盤面をエンコード（選択中の駒をコンテキストとして含める）
        board_tensor = encode_board(engine, selected_piece=engine.selected_piece).unsqueeze(0).to(self.device)

        # 推論
        self.model.eval()
        with torch.no_grad():
            policy_logits, _ = self.model(board_tensor, phase="dest")

        # 合法手のみをマスク
        legal_indices = [pos_to_index(x, y) for x, y in dests]
        logits = policy_logits[0, legal_indices]

        # 温度付きsoftmax
        probs = F.softmax(logits / self.temperature, dim=0)

        # サンプリング
        chosen_idx = torch.multinomial(probs, 1).item()
        return dests[chosen_idx]

    def choose_promotion(self, engine: GameEngine) -> bool:
        """成るかどうかを選択"""
        # ε確率でランダム
        if random.random() < self.epsilon:
            return random.choice([True, False])

        # 盤面をエンコード
        board_tensor = encode_board(engine).unsqueeze(0).to(self.device)

        # 推論
        self.model.eval()
        with torch.no_grad():
            policy_logits, _ = self.model(board_tensor, phase="promo")

        # softmax → argmax or サンプリング
        probs = F.softmax(policy_logits[0] / self.temperature, dim=0)

        # probs[0] = 成らない, probs[1] = 成る
        if self.temperature < 0.5:
            # 低温: 確率最大を選択
            return probs[1].item() > probs[0].item()
        else:
            # 高温: サンプリング
            return torch.multinomial(probs, 1).item() == 1

    def choose_shoot_target(self, engine: GameEngine) -> Optional[tuple[int, int]]:
        """射撃先を選択"""
        targets = engine.get_shoot_targets()
        if not targets:
            return None

        # ε確率でランダム
        if random.random() < self.epsilon:
            if random.random() < 0.3:  # 30%でスキップ
                return None
            return random.choice(targets)

        # 盤面をエンコード
        board_tensor = encode_board(engine).unsqueeze(0).to(self.device)

        # 推論
        self.model.eval()
        with torch.no_grad():
            policy_logits, _ = self.model(board_tensor, phase="shoot")

        # 合法手のインデックス（最後の362番目はスキップ）
        legal_indices = [pos_to_index(x, y) for x, y in targets]
        legal_indices.append(NUM_SQUARES)  # スキップ

        logits = policy_logits[0, legal_indices]

        # 温度付きsoftmax
        probs = F.softmax(logits / self.temperature, dim=0)

        # サンプリング
        chosen_idx = torch.multinomial(probs, 1).item()

        # スキップかどうか
        if chosen_idx == len(targets):
            return None
        return targets[chosen_idx]

    def choose_next_step(self, engine: GameEngine) -> tuple[int, int]:
        """マルチステップ移動の次のステップを選択"""
        options = engine.get_next_step_options()
        if not options:
            return (0, 0)

        # ε確率でランダム
        if random.random() < self.epsilon:
            return random.choice(options)

        # マルチステップ状態を取得
        multi_step_state = engine._multi_step_state

        # 盤面をエンコード（マルチステップ状態を含める）
        board_tensor = encode_board(engine, multi_step_state=multi_step_state).unsqueeze(0).to(self.device)

        # 推論
        self.model.eval()
        with torch.no_grad():
            policy_logits, _ = self.model(board_tensor, phase="step")

        # 合法手のインデックス（361番目は停止だが、ここでは移動先のみ）
        legal_indices = [pos_to_index(x, y) for x, y in options]
        logits = policy_logits[0, legal_indices]

        # 温度付きsoftmax
        probs = F.softmax(logits / self.temperature, dim=0)

        # サンプリング
        chosen_idx = torch.multinomial(probs, 1).item()
        return options[chosen_idx]

    def choose_stop(self, engine: GameEngine) -> bool:
        """マルチステップ移動を途中で止めるかどうかを選択"""
        if not engine.can_stop_now():
            return False

        # ε確率でランダム
        if random.random() < self.epsilon:
            return random.choice([True, False])

        # マルチステップ状態を取得
        multi_step_state = engine._multi_step_state
        options = engine.get_next_step_options()

        # 盤面をエンコード
        board_tensor = encode_board(engine, multi_step_state=multi_step_state).unsqueeze(0).to(self.device)

        # 推論
        self.model.eval()
        with torch.no_grad():
            policy_logits, _ = self.model(board_tensor, phase="step")

        # 停止のlogit（インデックス361）と移動先のlogitsを比較
        stop_logit = policy_logits[0, NUM_SQUARES]  # 停止

        if options:
            move_indices = [pos_to_index(x, y) for x, y in options]
            move_logits = policy_logits[0, move_indices]
            max_move_logit = move_logits.max()

            # 停止確率が最大移動確率より高ければ停止
            return stop_logit.item() > max_move_logit.item()
        else:
            # 移動先がなければ停止
            return True

    def load_checkpoint(self, path: str):
        """チェックポイントを読み込む"""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
