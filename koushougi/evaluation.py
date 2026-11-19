"""駒の価値と前進点による広将棋の盤面評価。"""


# 歩兵を100とした暫定値。長距離移動、射撃、特殊能力を加味する。
VALUES = {
    "歩兵": 100, "牌": 115, "先鋒": 130, "軍匠": 145, "軍吏": 180,
    "親兵": 200, "護兵": 200, "舎人": 200, "舎餘": 180,
    "前衝": 220, "後衝": 180, "馬兵": 250, "歩総": 270, "車": 300,
    "牌総": 340, "象": 330, "弓": 320, "弩": 380, "砲": 475,
    "仏狼機": 650, "記室": 240, "参謀": 240, "神僧": 240, "高道": 330,
    "力士": 450, "車総": 430, "百総": 465, "把総": 500, "騎総": 475,
    "都司": 520, "天塁": 600, "天馬": 680, "彍騎": 460, "弩騎": 520,
    "砲車": 650, "神機車": 850, "鷹揚": 670, "虎翼": 700,
    "千総": 730, "龍驤": 970, "軍師": 540, "旗鼓": 480,
    "千戸": 390, "百戸": 380, "副司": 450, "毒火": 560,
    "五里霧": 550, "聖燈": 450, "天網": 470, "地網": 460,
    "鼓": 340, "霹靂": 800, "旗": 700, "招揺": 850,
    "中軍": 850, "帥": 1500, "将": 1400,
}


def material_contribution(cell, piece):
    """一駒の価値と前進点を、黒側を正とする整数で返す。"""
    points = VALUES[piece.name] * 20 + (18 - cell[1] if piece.side == "black" else cell[1])
    return points if piece.side == "black" else -points


def material_points(board, side):
    balance = getattr(board, "material_balance", None)
    if balance is not None and side in {"black", "white"}:
        return balance if side == "black" else -balance
    score = 0
    for (_, y), piece in board.items():
        points = VALUES[piece.name] * 20 + (18 - y if piece.side == "black" else y)
        score += points if piece.side == side else -points
    return score


def material_score(game, side):
    """駒の価値と前進点の差を、指定された側から見た整数で返す。"""
    return material_points(game.board, side)
