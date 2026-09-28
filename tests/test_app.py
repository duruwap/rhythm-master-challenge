import json
import re

import pytest

import db
from app import create_app
from batch.build_summary import build_summary, rank_samples
from game_rules import LEVEL_SCORE_MAX


@pytest.fixture()
def dbpath(tmp_path):
    return str(tmp_path / "test.sqlite3")


@pytest.fixture()
def client(dbpath):
    app = create_app({"DATABASE": dbpath, "TESTING": True, "RATE_LIMIT": 50, "STATS_TTL": 0})
    return app.test_client()


def play(client, **over):
    body = {"seed": 12345, "bpm": 90, "level": "normal", "score": 1000, "maxPossible": 400000,
            "accuracy": 80.5, "maxCombo": 4, "playerId": "player-0001", "tier": "GOLD"}
    body.update(over)
    return client.post("/api/plays", json=body)


def rebuild(dbpath):
    conn = db.connect(dbpath)
    try:
        return build_summary(conn)
    finally:
        conn.close()


def test_index_injects_stats(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<!--RMC_STATS-->" not in html
    m = re.search(r"window\.__RMC_STATS__=(\{.*?\});</script>", html)
    assert m, "stats must be embedded in the page"
    stats = json.loads(m.group(1))
    assert stats["players"] == 0 and stats["levels"]["normal"]["plays"] == 0
    assert "Content-Security-Policy" in r.headers and r.headers["Cache-Control"] == "no-cache"


def test_static_font_css(client):
    r = client.get("/static/fonts/pretendard/pretendardvariable-dynamic-subset.css")
    assert r.status_code == 200
    assert "immutable" in r.headers["Cache-Control"]


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_record_then_batch_summary(client, dbpath):
    for i, s in enumerate([100, 400, 300, 200]):
        assert play(client, score=s, playerId=f"player-000{i}").status_code == 201
    play(client, score=999, level="hard", playerId="player-0001")
    report = rebuild(dbpath)
    assert report["normal"] == 4 and report["hard"] == 1 and report["total_players"] == 4
    stats = client.get("/api/stats").get_json()
    lv = stats["levels"]["normal"]
    assert lv["plays"] == 4 and lv["k"] == [1, 2, 3, 4] and lv["s"] == [400, 300, 200, 100]
    assert stats["players"] == 4 and stats["plays"] == 5 and stats["playsToday"] == 5


def test_rank_samples_caps_points():
    assert rank_samples(0) == []
    assert rank_samples(5) == [1, 2, 3, 4, 5]
    big = rank_samples(123456)
    assert len(big) == 1000 and big[0] >= 1 and big[-1] == 123456 and big == sorted(big)


@pytest.mark.parametrize("over", [
    {"score": -1}, {"score": -5000}, {"score": "abc"}, {"score": 1.5},
    {"score": LEVEL_SCORE_MAX["normal"] + 1, "maxPossible": LEVEL_SCORE_MAX["normal"]},   # 불가능한 점수
    {"score": 5000, "maxPossible": 4000},                                               # 리듬 최대치 초과
    {"maxPossible": LEVEL_SCORE_MAX["normal"] + 1},
    {"bpm": 120}, {"level": "insane"}, {"seed": -1}, {"seed": True},
    {"accuracy": 101}, {"accuracy": "nan"}, {"maxCombo": 100000},
    {"playerId": "x"}, {"playerId": "bad id with spaces"}, {"tier": "LEGEND"},
])
def test_validation(client, over):
    assert play(client, **over).status_code == 400


def test_max_score_accepted(client):
    cap = LEVEL_SCORE_MAX["hard"]
    assert play(client, level="hard", score=cap, maxPossible=cap).status_code == 201


def test_non_json_body(client):
    assert client.post("/api/plays", data="x", content_type="text/plain").status_code == 400


def test_rate_limit(dbpath):
    c = create_app({"DATABASE": dbpath, "TESTING": True, "RATE_LIMIT": 5}).test_client()
    codes = [play(c).status_code for _ in range(7)]
    assert codes[:5] == [201] * 5 and codes[5] == 429
