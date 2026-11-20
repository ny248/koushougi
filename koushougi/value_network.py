"""現行の駒価値で初期化する、線形経路と非線形経路を持つ局面評価NN。"""

import json
from functools import lru_cache
from math import isfinite, tanh
from random import Random

from . import initial_state
from .evaluation import VALUES
from .game import PROMOTIONS
from .search import WIN

SIZE = 19
SCALE = 20_000
PIECES = tuple(sorted({piece.name for piece in initial_state().values()} | set(PROMOTIONS.values())))
PIECE_IDS = {name: index for index, name in enumerate(PIECES)}
STATES = 1 + len(PIECES) * 4


def encode_board(pieces, side):
    """指定した側から見た盤面を361マスの駒状態へ変換する。"""
    encoded = [0] * (SIZE * SIZE)
    for (x, y), piece in pieces.items():
        if side == "white":
            x, y = SIZE - 1 - x, SIZE - 1 - y
        encoded[y * SIZE + x] = 1 + 4 * PIECE_IDS[piece.name] + 2 * (piece.side != side) + int(piece.promoted)
    return encoded


def initial_parameters(width=16, seed=0):
    rng = Random(seed)
    base = [0.0] * STATES
    advance = [0.0] * STATES
    for name, index in PIECE_IDS.items():
        for enemy in (0, 1):
            for promoted in (0, 1):
                state = 1 + 4 * index + 2 * enemy + promoted
                base[state] = -20 * VALUES[name] if enemy else 20 * VALUES[name] + 18
                advance[state] = -1.0
    return {
        "base": base,
        "advance": advance,
        "piece": [[rng.uniform(-0.1, 0.1) for _ in range(width)] for _ in range(STATES)],
        "square": [[rng.uniform(-0.1, 0.1) for _ in range(width)] for _ in range(SIZE * SIZE)],
        "hidden_bias": [0.0] * width,
        "output": [0.0] * width,
        "output_bias": [0.0],
    }


class ValueNetwork:
    """保存したNNの重みをCPUとブラウザで評価する。"""

    def __init__(self, parameters=None, *, width=16, seed=0, cache_size=16384):
        if type(width) is not int or not 1 <= width <= 256:
            raise ValueError("NNの幅は1〜256にしてください")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("評価値の保存件数は0以上の整数にしてください")
        self.width = width
        expected = initial_parameters(width, seed)
        source = expected if parameters is None else parameters
        if not isinstance(source, dict) or source.keys() != expected.keys():
            raise ValueError("NNのパラメータが不足しているか、未対応の項目があります")
        self.parameters = {}
        for name, template in expected.items():
            values = source[name]
            if not isinstance(values, (list, tuple)) or len(values) != len(template):
                raise ValueError("NNのパラメータの形が不正です")
            if isinstance(template[0], list):
                if any(not isinstance(row, (list, tuple)) or len(row) != width for row in values):
                    raise ValueError("NNのパラメータの形が不正です")
                self.parameters[name] = tuple(tuple(self._number(value) for value in row) for row in values)
            else:
                self.parameters[name] = tuple(self._number(value) for value in values)

        # 重みを固定したこのモデルで、同じNN入力の評価値を思考間でも再利用する。
        @lru_cache(maxsize=cache_size)
        def cached_forward(encoded):
            return self.forward(encoded)
        self._cached_forward = cached_forward

    @staticmethod
    def _number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError("NNの重みは有限の数値にしてください")
        return float(value)

    def forward(self, encoded):
        weights = self.parameters
        occupied = [(cell, state) for cell, state in enumerate(encoded) if state]
        linear = sum(weights["base"][state] + weights["advance"][state] * (cell // SIZE)
                     for cell, state in occupied)
        hidden = list(weights["hidden_bias"])
        for cell, state in occupied:
            for index, (piece, square) in enumerate(zip(weights["piece"][state], weights["square"][cell])):
                hidden[index] += piece * square / SIZE
        nonlinear = weights["output_bias"][0] + sum(
            weight * tanh(value) for weight, value in zip(weights["output"], hidden))
        return linear + SCALE * nonlinear

    def score(self, game, side):
        value = self._cached_forward(bytes(encode_board(game.board, game.turn)))
        score = round(value if side == game.turn else -value)
        return max(-WIN + 1, min(WIN - 1, score))

    def save(self, path):
        with path.open("x", encoding="utf-8") as output:
            json.dump({"format": 2, "pieces": PIECES, "width": self.width,
                       "parameters": self.parameters}, output, ensure_ascii=False, allow_nan=False)


def load_network(path=None):
    if path is None:
        return ValueNetwork()
    with path.open(encoding="utf-8") as source:
        state = json.load(source)
    if not isinstance(state, dict) or state.get("format") != 2 or state.get("pieces") != list(PIECES):
        raise ValueError("採点NNの形式が未対応です。format 2のモデルを指定してください")
    return ValueNetwork(state.get("parameters", {}), width=state.get("width"))


DEFAULT_NETWORK = ValueNetwork()
