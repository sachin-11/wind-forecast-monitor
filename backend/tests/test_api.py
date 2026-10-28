from datetime import UTC

import httpx
import pytest
from fastapi.testclient import TestClient

from app.data_sources import DataSourceError, ElexonSource
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok", "data_source": "sample"}


def test_series_shape_and_metrics():
    r = client.get("/api/series", params={"start": "2026-01-05T00:00:00Z", "end": "2026-01-06T00:00:00Z", "horizon_h": 6})
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 48  # half-hourly actuals for one day
    with_fc = [p for p in body["points"] if p["forecast"] is not None]
    assert len(with_fc) == 24
    assert all(p["lead_h"] >= 6 for p in with_fc)
    assert body["metrics"]["n"] == 24


def test_longer_horizon_is_less_accurate_on_sample_data():
    curve = client.get("/api/analysis").json()["horizon_curve"]
    assert curve[0]["horizon_h"] == 0 and curve[-1]["horizon_h"] == 48
    assert curve[-1]["mae"] > curve[0]["mae"]


def test_decision_mode_respects_cutoff():
    pts = client.get(
        "/api/series", params={"mode": "decision", "start": "2026-01-20T00:00:00Z", "end": "2026-01-21T00:00:00Z"}
    ).json()["points"]
    pubs = {p["publish_time"] for p in pts if p["publish_time"]}
    assert pubs and all(p <= "2026-01-19T09:00:00Z" for p in pubs)


def test_day_ahead_band():
    body = client.get("/api/day-ahead", params={"delivery_date": "2026-01-15"}).json()
    assert body["cutoff_utc"] == "2026-01-14T09:00:00Z"
    p = next(x for x in body["points"] if x["forecast"] is not None)
    assert p["p10"] < p["p90"]
    assert body["publish_time"] <= body["cutoff_utc"]
    assert body["summary"]["p10_mwh"] < body["summary"]["corrected_mwh"]
    assert 0.5 < body["scale"] < 1.5


def test_corrected_metrics_present():
    body = client.get("/api/analysis", params={"mode": "decision"}).json()
    assert body["decision_metrics_corrected"]["n"] == body["decision_metrics"]["n"] > 0
    assert "mae_corrected" in body["horizon_curve"][0]


@pytest.mark.parametrize(
    "params",
    [{"start": "2025-06-01T00:00:00Z", "end": "2025-06-02T00:00:00Z"}, {"horizon_h": 99}, {"mode": "bogus"}],
)
def test_validation_errors(params):
    assert client.get("/api/series", params=params).status_code == 422


def test_day_ahead_bad_date():
    assert client.get("/api/day-ahead", params={"delivery_date": "2025-05-01"}).status_code == 422


def test_elexon_source_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503)

    monkeypatch.setattr("time.sleep", lambda *_: None)
    src = ElexonSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(DataSourceError):
        src._get("/datasets/WINDFOR/stream", {})
    assert calls["n"] == 3


def test_elexon_source_parses_and_caches():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert request.url.params["fuelType"] == "WIND"
        return httpx.Response(
            200,
            json=[
                {
                    "startTime": "2026-01-02T00:00:00Z",
                    "publishTime": "2026-01-02T00:30:00Z",
                    "fuelType": "WIND",
                    "generation": 1234,
                },
            ],
        )

    from datetime import datetime

    src = ElexonSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    s, e = datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC)
    df = src.actuals(s, e)
    src.actuals(s, e)
    assert df.generation.tolist() == [1234.0]
    assert calls["n"] == 1
