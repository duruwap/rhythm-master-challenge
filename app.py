"""리듬 마스터 챌린지 — Flask 서버.

게임 자체는 static/index.html 단일 파일(바닐라 HTML/CSS/JS)이며, 서버는 다음을 담당한다.

* GET  /            게임 페이지. 최신 통계(점수 분포·플레이어 수)를 HTML 에 바로 넣어 보내
                    결과 화면의 "상위 N%"·등급을 네트워크 대기 없이 즉시 계산할 수 있게 한다.
* GET  /api/stats   같은 통계 JSON (파일로 직접 열었을 때 등 대체 경로)
* POST /api/plays   한 판의 결과 기록 (클라이언트가 비동기로 보내고 응답을 기다리지 않음)
* GET  /api/health  헬스 체크

통계는 batch/build_summary.py 가 play_detail 을 집계해 summary 테이블에 주기적으로 저장하고,
서버는 summary 테이블만 읽는다 (짧게 메모리 캐시).
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, request, send_from_directory

import db
from batch.build_summary import build_summary
from game_rules import BPM, LEVEL_NOTES_MAX, LEVEL_SCORE_MAX, LEVELS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SEED_MAX = 0xFFFFFFFF
PLAYER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
TIERS = ("BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "MASTER", "CHALLENGER")
STATS_PLACEHOLDER = "<!--RMC_STATS-->"


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


def parse_play(data: dict) -> dict:
    """한 판 결과를 검증한다. 음수·불가능한 점수는 ValidationError."""
    level = data.get("level")
    if level not in LEVELS:
        raise ValidationError("level must be one of easy/normal/hard")
    bpm = _int(data.get("bpm", BPM), "bpm", 0, 1000)
    if bpm != BPM:
        raise ValidationError(f"bpm must be {BPM}")
    seed = _int(data.get("seed"), "seed", 0, SEED_MAX)
    cap = LEVEL_SCORE_MAX[level]
    max_possible = _int(data.get("maxPossible"), "maxPossible", 1, cap)
    raw_score = data.get("score")
    try:
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool) and raw_score < 0:
            raise ValidationError("score must not be negative")
    except TypeError:
        pass
    score = _int(raw_score, "score", 0, cap)
    if score > max_possible:
        raise ValidationError("score exceeds the maximum possible for this rhythm")
    max_combo = _int(data.get("maxCombo", 0), "maxCombo", 0, LEVEL_NOTES_MAX[level])
    try:
        accuracy = float(data.get("accuracy", 0))
    except (TypeError, ValueError):
        raise ValidationError("accuracy must be a number") from None
    if not (math.isfinite(accuracy) and 0 <= accuracy <= 100):
        raise ValidationError("accuracy out of range")
    player_id = data.get("playerId")
    if not isinstance(player_id, str) or not PLAYER_ID_RE.match(player_id):
        raise ValidationError("playerId invalid")
    tier = data.get("tier")
    if tier is not None and tier not in TIERS:
        raise ValidationError("tier invalid")
    return dict(level=level, bpm=bpm, seed=seed, score=score, max_possible=max_possible,
                accuracy=round(accuracy, 2), max_combo=max_combo, player_id=player_id, tier=tier)


def load_stats(conn) -> dict:
    """summary 테이블 → 클라이언트용 통계 (분포는 순위 위치 k 와 점수 s 의 병렬 배열)."""
    site = conn.execute("SELECT * FROM site_summary WHERE id = 1").fetchone()
    levels = {}
    for row in conn.execute("SELECT level, plays, players FROM level_summary"):
        pts = conn.execute(
            "SELECT rank_pos, score FROM score_summary WHERE level = ? ORDER BY rank_pos", (row["level"],)).fetchall()
        levels[row["level"]] = {"plays": row["plays"], "players": row["players"],
                                "k": [p[0] for p in pts], "s": [p[1] for p in pts]}
    return {
        "updatedAt": site["updated_at"] if site else None,
        "players": site["total_players"] if site else 0,
        "plays": site["total_plays"] if site else 0,
        "playsToday": site["plays_today"] if site else 0,
        "playersToday": site["players_today"] if site else 0,
        "levels": levels,
    }


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
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
    app.config.from_mapping(
        DATABASE=db.default_db_path(),
        MAX_CONTENT_LENGTH=4 * 1024,
        JSON_AS_ASCII=False,
        RATE_LIMIT=30,          # IP당 분당 기록 요청 수
        RATE_WINDOW=60.0,
        STATS_TTL=30.0,         # 통계 메모리 캐시(초). 원본은 배치가 갱신하는 summary 테이블
    )
    if test_config:
        app.config.update(test_config)

    limiter = RateLimiter(app.config["RATE_LIMIT"], app.config["RATE_WINDOW"])
    cache = {"stats": None, "at": 0.0, "html": None, "mtime": None}
    cache_lock = threading.Lock()

    # ---------------------------------------------------------------- DB
    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    # 기동 시 DDL 적용, 통계가 한 번도 만들어지지 않았다면 즉시 1회 생성
    boot = db.connect(app.config["DATABASE"])
    try:
        db.apply_ddl(boot)
        if boot.execute("SELECT COUNT(*) FROM site_summary").fetchone()[0] == 0:
            build_summary(boot)
    finally:
        boot.close()

    def current_stats() -> dict:
        with cache_lock:
            if cache["stats"] is not None and time.monotonic() - cache["at"] < app.config["STATS_TTL"]:
                return cache["stats"]
        stats = load_stats(get_db())
        with cache_lock:
            cache["stats"], cache["at"] = stats, time.monotonic()
        return stats

    def index_html() -> str:
        path = os.path.join(STATIC_DIR, "index.html")
        mtime = os.path.getmtime(path)
        with cache_lock:
            if cache["html"] is not None and cache["mtime"] == mtime:
                return cache["html"]
        with open(path, encoding="utf-8") as f:
            html = f.read()
        with cache_lock:
            cache["html"], cache["mtime"] = html, mtime
        return html

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
        # 통계를 페이지에 바로 넣어 보낸다 → 결과 화면에서 추가 요청·대기 없음
        payload = json.dumps(current_stats(), separators=(",", ":")).replace("</", "<\\/")
        html = index_html().replace(STATS_PLACEHOLDER, f"<script>window.__RMC_STATS__={payload};</script>", 1)
        return Response(html, mimetype="text/html")

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(STATIC_DIR, "favicon.svg", mimetype="image/svg+xml")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/stats")
    def stats():
        return jsonify(current_stats())

    @app.post("/api/plays")
    def post_play():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="JSON object body required"), 400
        try:
            play = parse_play(data)
        except ValidationError as e:
            return jsonify(error=str(e)), 400
        ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
        if not limiter.allow(ip):
            return jsonify(error="too many requests"), 429
        conn = get_db()
        conn.execute(
            "INSERT INTO play_detail (played_at, player_id, level, bpm, seed, score, max_possible, accuracy, max_combo, tier) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), play["player_id"], play["level"], play["bpm"],
             play["seed"], play["score"], play["max_possible"], play["accuracy"], play["max_combo"], play["tier"]),
        )
        conn.commit()
        return jsonify(ok=True), 201

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="payload too large"), 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "15002")),
            debug=os.environ.get("FLASK_DEBUG") == "1")
