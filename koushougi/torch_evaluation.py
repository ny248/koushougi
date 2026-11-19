"""学習用の実行環境で、同じNNの複数局面をまとめて採点する。"""

from collections import OrderedDict

import torch

from .search import WIN
from .train_value import TrainingNetwork, get_device
from .value_network import encode_board


class TorchEvaluator:
    def __init__(self, model, *, device="auto", batch_size=256, cache_size=16384):
        if batch_size < 1 or cache_size < 0:
            raise ValueError("評価のバッチ数またはキャッシュ件数が不正です")
        self.device = get_device(device)
        self.model, self.batch_size, self.cache_size = model, batch_size, cache_size
        self.network = TrainingNetwork(model)
        # CPUでは倍精度を使い、標準ライブラリの推論との丸めの差を抑える。
        self.network = self.network.to(device=self.device, dtype=(torch.float64
                                      if self.device.type == "cpu" else torch.float32)).eval()
        self.cache = OrderedDict()

    @torch.inference_mode()
    def score_many(self, games, side):
        encoded = [bytes(encode_board(game.board, game.turn)) for game in games]
        missing = list(dict.fromkeys(row for row in encoded if row not in self.cache))
        computed = {}
        for offset in range(0, len(missing), self.batch_size):
            chunk = missing[offset:offset + self.batch_size]
            tensor = torch.tensor([list(row) for row in chunk], dtype=torch.long, device=self.device)
            values = self.network(tensor).cpu().tolist()
            for row, value in zip(chunk, values):
                if not (-float("inf") < value < float("inf")):
                    raise ValueError("NNの評価値が有限ではありません")
                computed[row] = round(value)
        scores = []
        for row, game in zip(encoded, games):
            raw = computed[row] if row in computed else self.cache[row]
            value = raw if game.turn == side else -raw
            scores.append(max(-WIN + 1, min(WIN - 1, value)))
        for row in encoded:
            if row in computed:
                self.cache[row] = computed[row]
            if row in self.cache:
                self.cache.move_to_end(row)
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return scores

    def score(self, game, side):
        return self.score_many([game], side)[0]
