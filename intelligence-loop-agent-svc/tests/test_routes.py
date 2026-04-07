"""Smoke tests for ILA HTTP routes."""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "intelligence-loop-agent"


def test_execute_requires_token(client):
    resp = client.post("/v1/execute", json={"job_id": "j1"})
    assert resp.status_code == 401


def test_execute_returns_intelligence_report(client, service_token_header):
    resp = client.post(
        "/v1/execute",
        json={
            "job_id": "job-abc",
            "tenant_id": "tenant-1",
            "state": {"campaign_id": "camp-9"},
            "config": {"default_mode": "store_only"},
        },
        headers=service_token_header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == "job-abc"
    assert body["intelligence_report"]["mode"] == "store_only"
    assert body["intelligence_report"]["campaign_id"] == "camp-9"
    assert len(body["intelligence_report"]["learnings"]) == 1
    learning = body["intelligence_report"]["learnings"][0]
    assert learning["category"] == "creative"
    assert 0 <= learning["confidence"] <= 100
