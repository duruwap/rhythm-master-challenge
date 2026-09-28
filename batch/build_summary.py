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
from game_rules import BPM, LEVELS  # noqa: E402

SAMPLES = 1000   # 난이도별 분포 표본 지점 수 (기록이 이보다 적으면 모든 기록 저장)


def rank_samples(n: int, samples: int = SAMPLES) -> list[int]:
    """1..n 중 저장할 순위 위치. n <= samples 이면 전부."""
    if n <= 0:
        return []
    if n <= samples:
        return list(range(1, n + 1))
    return sorted({max(1, math.ceil(n * j / samples)) for j in range(1, samples + 1)})


def build_summary(conn) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {}
    with conn:   # 하나의 트랜잭션
        conn.execute("DELETE FROM score_summary")
        conn.execute("DELETE FROM level_summary")
        for level in LEVELS:
            scores = [r[0] for r in conn.execute(
                "SELECT score FROM play_detail WHERE level = ? AND bpm = ? ORDER BY score DESC", (level, BPM))]
            n = len(scores)
            conn.executemany(
                "INSERT INTO score_summary (level, rank_pos, score) VALUES (?, ?, ?)",
                [(level, k, scores[k - 1]) for k in rank_samples(n)])
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
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="rhythm-master-challenge 통계 배치")
    ap.add_argument("--db", default=None, help="SQLite 경로 (기본: RMC_DATABASE 또는 instance/rhythm_master.sqlite3)")
    args = ap.parse_args(argv)
    t0 = time.time()
    conn = db.connect(args.db)
    try:
        db.apply_ddl(conn)
        report = build_summary(conn)
    finally:
        conn.close()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] summary rebuilt in {time.time() - t0:.2f}s: {report}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
