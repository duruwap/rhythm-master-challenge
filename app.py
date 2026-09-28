"""리듬 마스터 챌린지 — Flask 서버.

게임 자체는 static/index.html 단일 파일(바닐라 HTML/CSS/JS)이며,
서버는 다음을 담당한다.

* 게임 페이지와 정적 파일(자체 호스팅 Pretendard 폰트) 제공
* 같은 리듬(seed·BPM·난이도) 도전 기록 집계 API (SQLite)
  - POST /api/scores  : 한 판의 결과를 기록하고 순위(같은 리듬 / 같은 난이도·BPM)를 돌려준다
  - GET  /api/scores  : 해당 리듬의 도전 횟수 / 최고 점수
* GET /api/health    : 헬스 체크

점수는 클라이언트가 계산하므로 치팅 방지 용도가 아니라 "친구끼리 비교" 용도의
가벼운 통계다. 입력값은 범위 검증만 한다.
"""

from __future__ import annotations

import math
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque

from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

LEVELS = ("easy", "normal", "hard")
BPM_MIN, BPM_MAX, BPM_STEP = 60, 140, 5
SEED_MAX = 0xFFFFFFFF
# 이론상 최대 점수(어려움·BPM 140에서 약 150만)보다 넉넉한 상한
SCORE_MAX = 3_000_000
COMBO_MAX = 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    seed       INTEGER NOT NULL,
    bpm        INTEGER NOT NULL,
    level      TEXT    NOT NULL,
    score      INTEGER NOT NULL,
    accuracy   REAL    NOT NULL,
    max_combo  INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plays_rhythm ON plays (seed, bpm, level, score);
CREATE INDEX IF NOT EXISTS idx_plays_level ON plays (level, bpm, score);
"""


class ValidationError(ValueError):
    pass


def _int(value, name, lo, hi):
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be an integer")
    try:
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be an integer") from None
    if not lo <= n <= hi:
        raise ValidationError(f"{name} out of range")
    return n


def parse_rhythm(src) -> tuple[int, int, str]:
    """seed/bpm/level 을 검증해 튜플로 돌려준다."""
    seed = _int(src.get("seed"), "seed", 0, SEED_MAX)
    bpm = _int(src.get("bpm"), "bpm", BPM_MIN, BPM_MAX)
    if bpm % BPM_STEP:
        raise ValidationError("bpm must be a multiple of 5")
    level = src.get("level")
    if level not in LEVELS:
        raise ValidationError("level must be one of easy/normal/hard")
    return seed, bpm, level


class RateLimiter:
    """IP별 슬라이딩 윈도우 요청 제한 (프로세스 메모리 기반의 가벼운 방어)."""

    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window = window_s
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self.hits) > 10_000:  # 메모리 보호
                for k in [k for k, v in self.hits.items() if not v]:
                    del self.hits[k]
            return True


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static",
                instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get("RMC_DATABASE",
                                os.path.join(app.instance_path, "rhythm_master.sqlite3")),
        MAX_CONTENT_LENGTH=4 * 1024,
        JSON_AS_ASCII=False,
        RATE_LIMIT=30,          # 분당 기록 요청 수
        RATE_WINDOW=60.0,
    )
    if test_config:
        app.config.update(test_config)

    db_dir = os.path.dirname(app.config["DATABASE"])
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    limiter = RateLimiter(app.config["RATE_LIMIT"], app.config["RATE_WINDOW"])

    # ---------------------------------------------------------------- DB
    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            conn = sqlite3.connect(app.config["DATABASE"], timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            g.db = conn
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    with app.app_context():
        get_db().executescript(SCHEMA)

    def rhythm_stats(db, seed, bpm, level):
        row = db.execute(
            "SELECT COUNT(*) AS plays, COALESCE(MAX(score), 0) AS best "
            "FROM plays WHERE seed=? AND bpm=? AND level=?",
            (seed, bpm, level),
        ).fetchone()
        return int(row["plays"]), int(row["best"])

    # ---------------------------------------------------------------- 헤더
    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if resp.mimetype == "text/html":
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
            )
            resp.headers["Cache-Control"] = "no-cache"
        elif request.path.startswith("/static/fonts/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    # ---------------------------------------------------------------- 라우트
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(STATIC_DIR, "favicon.svg", mimetype="image/svg+xml")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/scores")
    def get_scores():
        try:
            seed, bpm, level = parse_rhythm(request.args)
        except ValidationError as e:
            return jsonify(error=str(e)), 400
        plays, best = rhythm_stats(get_db(), seed, bpm, level)
        return jsonify(seed=seed, bpm=bpm, level=level, plays=plays, best=best)

    @app.post("/api/scores")
    def post_score():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="JSON object body required"), 400
        try:
            seed, bpm, level = parse_rhythm(data)
            score = _int(data.get("score"), "score", 0, SCORE_MAX)
            max_combo = _int(data.get("maxCombo", 0), "maxCombo", 0, COMBO_MAX)
            try:
                accuracy = float(data.get("accuracy", 0))
            except (TypeError, ValueError):
                raise ValidationError("accuracy must be a number") from None
            if not (math.isfinite(accuracy) and 0 <= accuracy <= 100):
                raise ValidationError("accuracy out of range")
        except ValidationError as e:
            return jsonify(error=str(e)), 400

        ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
        if not limiter.allow(ip):
            return jsonify(error="too many requests"), 429

        db = get_db()
        db.execute(
            "INSERT INTO plays (seed, bpm, level, score, accuracy, max_combo, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (seed, bpm, level, score, round(accuracy, 2), max_combo, int(time.time())),
        )
        db.commit()
        plays, best = rhythm_stats(db, seed, bpm, level)
        higher = db.execute(
            "SELECT COUNT(*) FROM plays WHERE seed=? AND bpm=? AND level=? AND score>?",
            (seed, bpm, level, score),
        ).fetchone()[0]
        rank = int(higher) + 1
        top_percent = max(1, math.ceil(rank / plays * 100))
        # 같은 난이도·BPM 전체(모든 리듬) 기준 순위 — 매 판 새 리듬이라 이쪽이 주로 쓰인다
        lv = db.execute(
            "SELECT COUNT(*) AS n, SUM(score > ?) AS higher FROM plays WHERE level=? AND bpm=?",
            (score, level, bpm),
        ).fetchone()
        level_plays = int(lv["n"])
        level_rank = int(lv["higher"] or 0) + 1
        level_top = max(1, math.ceil(level_rank / level_plays * 100))
        return jsonify(plays=plays, best=best, rank=rank, topPercent=top_percent,
                       levelPlays=level_plays, levelRank=level_rank, levelTopPercent=level_top), 201

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="payload too large"), 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "15002")),
            debug=os.environ.get("FLASK_DEBUG") == "1")
