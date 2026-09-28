import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "test.sqlite3"), "TESTING": True, "RATE_LIMIT": 5})
    return app.test_client()


def play(client, **over):
    body = {"seed": 12345, "bpm": 90, "level": "normal", "score": 1000, "accuracy": 80.5, "maxCombo": 4}
    body.update(over)
    return client.post("/api/scores", json=body)


def test_index_served_with_headers(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<!doctype html>" in r.data[:50].lower()
    assert "Content-Security-Policy" in r.headers
    assert r.headers["Cache-Control"] == "no-cache"


def test_static_font_css(client):
    r = client.get("/static/fonts/pretendard/pretendardvariable-dynamic-subset.css")
    assert r.status_code == 200
    assert "immutable" in r.headers["Cache-Control"]


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_record_and_rank(client):
    assert play(client, score=1000).get_json()["rank"] == 1
    r = play(client, score=5000)
    assert r.status_code == 201
    data = r.get_json()
    assert data == {"plays": 2, "best": 5000, "rank": 1, "topPercent": 50,
                    "levelPlays": 2, "levelRank": 1, "levelTopPercent": 50}
    data = play(client, score=10).get_json()
    assert data["rank"] == 3 and data["topPercent"] == 100

    stats = client.get("/api/scores?seed=12345&bpm=90&level=normal").get_json()
    assert stats["plays"] == 3 and stats["best"] == 5000
    # 다른 리듬은 따로 집계
    other = client.get("/api/scores?seed=12345&bpm=95&level=normal").get_json()
    assert other["plays"] == 0 and other["best"] == 0


@pytest.mark.parametrize("over", [
    {"seed": -1}, {"seed": "abc"}, {"bpm": 92}, {"bpm": 200}, {"level": "insane"},
    {"score": -5}, {"score": 10**9}, {"accuracy": 101}, {"accuracy": "nan"}, {"seed": True},
])
def test_validation(client, over):
    assert play(client, **over).status_code == 400


def test_level_rank_spans_rhythms(client):
    play(client, seed=1, score=100)
    play(client, seed=2, score=300)
    play(client, seed=3, score=200, level="hard")   # 다른 난이도는 제외
    data = play(client, seed=4, score=200).get_json()
    assert data["plays"] == 1 and data["topPercent"] == 100
    assert data["levelPlays"] == 3 and data["levelRank"] == 2 and data["levelTopPercent"] == 67


def test_non_json_body(client):
    assert client.post("/api/scores", data="x", content_type="text/plain").status_code == 400


def test_rate_limit(client):
    codes = [play(client).status_code for _ in range(7)]
    assert codes[:5] == [201] * 5
    assert codes[5] == 429
