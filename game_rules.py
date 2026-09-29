"""서버 측 게임 규칙 — 점수 검증용.

static/index.html 의 CONFIG(SHAPE_POOLS · LAYOUTS 패드 수 · SCORING)와 같은 값을 유지해야 한다.
클라이언트가 보낸 점수가 이론상 가능한 최대치를 넘으면 거부하기 위해,
난이도별로 "가장 꼭짓점이 많은 도형 조합 + 전부 PERFECT" 점수를 계산한다.
"""

from __future__ import annotations

import math

LEVELS = ("easy", "normal", "hard")
BPM = 90                      # BPM 고정
TOTAL_ROUNDS = 8
BARS_PER_ROUND = 2

PAD_COUNT = {"easy": 2, "normal": 3, "hard": 4}
SHAPE_POOLS = {
    "easy": [[1, 2], [1, 2, 4], [1, 2, 3], [2, 3, 4], [2, 3, 4], [3, 4, 6], [3, 4, 5, 6], [3, 4, 5, 6]],
    "normal": [[1, 2, 4], [1, 2, 3, 4], [1, 2, 3, 4], [2, 3, 4, 6], [2, 3, 4, 5, 6], [3, 4, 5, 6], [3, 4, 5, 6, 7], [3, 4, 5, 6, 7, 8]],
    "hard": [[1, 2, 4, 8], [1, 2, 3, 4, 6], [2, 3, 4, 6, 8], [2, 3, 4, 5, 6, 8], [3, 4, 5, 6, 8], [3, 4, 5, 6, 7, 8], [3, 4, 5, 6, 7, 8], [4, 5, 6, 7, 8]],
}
HIT_PERFECT = 1000
ROUND_BONUS_PERFECT = 2000
ROUND_WEIGHT = [1, 1, 1.5, 1.5, 2, 2, 2.5, 2.5]
MILESTONE = {10: 2000, 20: 5000, 50: 10000}
FULL_PERFECT = 20000
LEVEL_MUL = {"easy": 0.8, "normal": 1.0, "hard": 1.3}

# 등급: 같은 난이도 상위 % 누적 기준 (index.html 의 TIER_BANDS · CONFIG.MIN_RANK_SAMPLES 와 동일)
TIER_BANDS = ((1, "CHALLENGER"), (4, "MASTER"), (11, "DIAMOND"), (25, "PLATINUM"), (45, "GOLD"), (70, "SILVER"), (100, "BRONZE"))
MIN_RANK_SAMPLES = 20   # 기록이 이보다 적으면 클라이언트는 최대 점수 대비 비율로 등급을 매김


def combo_bonus(n: int) -> int:
    if 2 <= n <= 4:
        return 100 * (n - 1)
    if 5 <= n <= 9:
        return 500
    if 10 <= n <= 19:
        return 800
    if n >= 20:
        return 1000
    return 0


def max_notes_per_round(level: str) -> list[int]:
    pads = PAD_COUNT[level]
    out = []
    for pool in SHAPE_POOLS[level]:
        top = sorted(pool, reverse=True)[:pads]
        out.append(BARS_PER_ROUND * sum(top) + pads)   # 2마디 + 패드별 마무리 박
    return out


def level_score_max(level: str) -> int:
    """해당 난이도에서 나올 수 있는 이론상 최대 점수 (모든 시드의 상한)."""
    raw = 0
    combo = 0
    notes_total = 0
    for r, n in enumerate(max_notes_per_round(level)):
        for _ in range(n):
            combo += 1
            raw += HIT_PERFECT + combo_bonus(combo) + MILESTONE.get(combo, 0)
        notes_total += n
        raw += round(ROUND_BONUS_PERFECT * ROUND_WEIGHT[r])
    raw += FULL_PERFECT
    mul = round(LEVEL_MUL[level] * 10000) / 10000
    return math.floor(raw * mul + 1e-6)


def max_notes_total(level: str) -> int:
    return sum(max_notes_per_round(level))


LEVEL_SCORE_MAX = {lv: level_score_max(lv) for lv in LEVELS}
LEVEL_NOTES_MAX = {lv: max_notes_total(lv) for lv in LEVELS}
