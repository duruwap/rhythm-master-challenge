"""통계 배치: play_detail → score_summary / level_summary / site_summary 재생성.

주기적으로 실행한다 (예: cron 10분마다, batch/run_summary.sh).
한 트랜잭션으로 지우고 다시 채우므로, 실행 중에도 서버는 항상 완전한 이전/새 통계를 읽는다.

    python -m batch.build_summary [--db PATH]
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from game_rules import BPM, LEVELS, MIN_RANK_SAMPLES, TIER_BANDS  # noqa: E402

SAMPLES = 1000   # 난이도별 분포 표본 지점 수 (기록이 이보다 적으면 모든 기록 저장)


def rank_samples(n: int, samples: int = SAMPLES) -> list[int]:
    """1..n 중 저장할 순위 위치. n <= samples 이면 전부."""
    if n <= 0:
        return []
    if n <= samples:
        return list(range(1, n + 1))
    return sorted({max(1, math.ceil(n * j / samples)) for j in range(1, samples + 1)})


def tier_ranges(samples: list[tuple[int, int]], n: int) -> list[tuple[str, int, int | None]] | None:
    """저장된 분포(순위 위치 k, 점수 s — 점수 내림차순)로 등급별 점수 범위를 구한다.

    클라이언트(Stats.topPercent + tierOf)와 같은 계산: 상위 % = (내 점수보다 높은 기록 수 + 1) / (기록 수 + 1).
    반환: [(등급, 최저 점수, 최고 점수 또는 None=상한 없음)], 해당 점수가 없는 등급은 빠진다.
    기록이 MIN_RANK_SAMPLES 미만이면 None (클라이언트가 비율 기준을 쓰는 구간).
    """
    if n < MIN_RANK_SAMPLES or not samples:
        return None
    # 서로 다른 점수마다 "그보다 높은 기록 수" → 상위 %
    pct_by_score, higher, i = [], 0, 0
    while i < len(samples):
        score, j = samples[i][1], i
        while j < len(samples) and samples[j][1] == score:
            j += 1
        pct_by_score.append((score, min(100.0, max(0.1, (higher + 1) / (n + 1) * 100))))
        higher = samples[j - 1][0]
        i = j
    ranges, upper = [], None       # upper: 바로 위 등급의 최저 점수
    for idx, (max_pct, tier) in enumerate(TIER_BANDS):
        last = idx == len(TIER_BANDS) - 1
        ok = [sc for sc, p in pct_by_score if p <= max_pct]
        lo = 0 if last else (min(ok) if ok else None)
        if lo is None or (upper is not None and lo >= upper):
            continue
        ranges.append((tier, lo, None if upper is None else upper - 1))
        upper = lo
    return ranges


def format_tier_ranges(level: str, n: int, ranges) -> str:
    head = f"  {level:<6} {n:>6}판"
    if ranges is None:
        return f"{head}  기록 {MIN_RANK_SAMPLES}판 미만 → 등급은 최대 점수 대비 비율로 판정"
    parts = [f"{tier} {lo:,}~" + ("" if hi is None else f"{hi:,}") for tier, lo, hi in ranges]
    return f"{head}  " + " | ".join(parts)


def build_summary(conn) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report, tiers = {}, {}
    with conn:   # 하나의 트랜잭션
        conn.execute("DELETE FROM score_summary")
        conn.execute("DELETE FROM level_summary")
        for level in LEVELS:
            scores = [r[0] for r in conn.execute(
                "SELECT score FROM play_detail WHERE level = ? AND bpm = ? ORDER BY score DESC", (level, BPM))]
            n = len(scores)
            samples = [(k, scores[k - 1]) for k in rank_samples(n)]
            conn.executemany(
                "INSERT INTO score_summary (level, rank_pos, score) VALUES (?, ?, ?)",
                [(level, k, sc) for k, sc in samples])
            tiers[level] = (n, tier_ranges(samples, n))
            players = conn.execute(
                "SELECT COUNT(DISTINCT player_id) FROM play_detail WHERE level = ? AND bpm = ?", (level, BPM)).fetchone()[0]
            conn.execute(
                "INSERT INTO level_summary (level, plays, players, best_score, avg_score, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (level, n, players, scores[0] if n else 0, (sum(scores) / n) if n else 0.0, now))
            report[level] = n
        site = conn.execute(
            "SELECT COUNT(*) AS plays, COUNT(DISTINCT player_id) AS players, "
            "SUM(date(played_at, 'localtime') = date('now', 'localtime')) AS plays_today, "
            "COUNT(DISTINCT CASE WHEN date(played_at, 'localtime') = date('now', 'localtime') THEN player_id END) AS players_today "
            "FROM play_detail").fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO site_summary (id, total_plays, total_players, plays_today, players_today, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (site["plays"], site["players"], site["plays_today"] or 0, site["players_today"] or 0, now))
        report.update(total_plays=site["plays"], total_players=site["players"])
    report["tiers"] = tiers
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="rhythm-master-challenge 통계 배치")
    ap.add_argument("--db", default=None, help="SQLite 경로 (기본: RMC_DATABASE 환경 변수)")
    args = ap.parse_args(argv)
    t0 = time.time()
    conn = db.connect(args.db)
    try:
        db.apply_ddl(conn)
        report = build_summary(conn)
    finally:
        conn.close()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tiers = report.pop("tiers")
    lines = [f"[{stamp}] summary rebuilt in {time.time() - t0:.2f}s: {report}", "  등급별 점수 범위 (상위 %: "
             + " · ".join(f"{t} ≤{p}%" for p, t in TIER_BANDS[:-1]) + " · BRONZE 나머지)"]
    lines += [format_tier_ranges(level, n, ranges) for level, (n, ranges) in tiers.items()]
    print("\n".join(lines), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
