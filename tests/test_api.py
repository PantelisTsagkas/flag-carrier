"""API tests for Flag Carrier."""

import pytest
from fastapi.testclient import TestClient

from main import COUNTRIES, OPTIONS_PER_ROUND, ROUNDS_PER_DAY, STATIC_DIR, app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FC_DB_PATH", str(tmp_path / "test.db"))
    return TestClient(app)


def test_daily_is_deterministic(client):
    a = client.get("/api/daily", params={"date": "2026-07-18"}).json()
    b = client.get("/api/daily", params={"date": "2026-07-18"}).json()
    assert a == b


def test_daily_differs_across_dates(client):
    a = client.get("/api/daily", params={"date": "2026-07-18"}).json()
    b = client.get("/api/daily", params={"date": "2026-07-19"}).json()
    assert [r["answer"] for r in a["rounds"]] != [r["answer"] for r in b["rounds"]]


def test_daily_structure(client):
    data = client.get("/api/daily", params={"date": "2026-07-18"}).json()
    rounds = data["rounds"]
    assert len(rounds) == ROUNDS_PER_DAY
    answers = [r["answer"] for r in rounds]
    assert len(set(answers)) == ROUNDS_PER_DAY
    for r in rounds:
        codes = [o["code"] for o in r["options"]]
        assert len(codes) == OPTIONS_PER_ROUND
        assert len(set(codes)) == OPTIONS_PER_ROUND
        assert r["answer"] in codes
        assert r["name"] == COUNTRIES[r["answer"]]


def test_every_country_has_a_flag_asset():
    for code in COUNTRIES:
        assert (STATIC_DIR / "flags" / f"{code}.svg").exists(), code


def test_daily_rejects_bad_date(client):
    assert client.get("/api/daily", params={"date": "nonsense"}).status_code == 400
    assert client.get("/api/daily", params={"date": "2026-02-30"}).status_code == 400


def test_practice_shape(client):
    data = client.get("/api/practice").json()
    assert data["date"] is None
    assert len(data["rounds"]) == ROUNDS_PER_DAY


def test_score_submit_and_leaderboard_order(client):
    d = "2026-07-18"
    r1 = client.post("/api/scores", json={"name": "AVA", "score": 1500, "date": d}).json()
    assert r1["logged"] is True and r1["position"] == 1
    r2 = client.post("/api/scores", json={"name": "BEN", "score": 900, "date": d}).json()
    assert r2["position"] == 2
    board = client.get("/api/leaderboard", params={"date": d}).json()
    assert [e["name"] for e in board["entries"]] == ["AVA", "BEN"]
    assert board["entries"][0]["pos"] == 1


def test_first_attempt_stands(client):
    d = "2026-07-18"
    client.post("/api/scores", json={"name": "Cara", "score": 800, "date": d})
    retry = client.post("/api/scores", json={"name": "CARA", "score": 2000, "date": d}).json()
    assert retry["logged"] is False
    assert retry["standing_score"] == 800
    board = client.get("/api/leaderboard", params={"date": d}).json()
    assert len(board["entries"]) == 1
    assert board["entries"][0]["score"] == 800


def test_score_validation(client):
    assert client.post("/api/scores", json={"name": "X", "score": 2001}).status_code == 422
    assert client.post("/api/scores", json={"name": "X", "score": -1}).status_code == 422
    assert client.post("/api/scores", json={"name": "", "score": 100}).status_code == 422
    assert client.post("/api/scores", json={"name": "   ", "score": 100}).status_code == 422


def test_alltime_sums_across_days(client):
    client.post("/api/scores", json={"name": "DEV", "score": 1000, "date": "2026-07-17"})
    client.post("/api/scores", json={"name": "DEV", "score": 500, "date": "2026-07-18"})
    data = client.get("/api/alltime").json()
    assert data["entries"][0]["name"] == "DEV"
    assert data["entries"][0]["total"] == 1500
    assert data["entries"][0]["days"] == 2
