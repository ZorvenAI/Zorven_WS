"""Tests for the /v1/execute endpoint."""


async def test_execute_stub_mode(client, valid_execute_payload, tenant_headers):
    """POST /v1/execute should return stub response when executor not initialized."""
    response = await client.post(
        "/v1/execute",
        json=valid_execute_payload,
        headers=tenant_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("stub", "success")
    assert isinstance(data["findings"], list)
    assert isinstance(data["recommendations"], list)
    assert isinstance(data["tools_called"], list)


async def test_execute_missing_prompt(client, tenant_headers):
    """POST /v1/execute with empty payload should still work."""
    response = await client.post(
        "/v1/execute",
        json={},
        headers=tenant_headers,
    )
    assert response.status_code == 200


async def test_execute_default_tenant(client, valid_execute_payload):
    """POST /v1/execute without X-Tenant-ID should use default."""
    response = await client.post(
        "/v1/execute",
        json=valid_execute_payload,
    )
    assert response.status_code == 200


async def test_execute_response_schema(client, valid_execute_payload, tenant_headers):
    """Response should contain all ExecuteResponse fields."""
    response = await client.post(
        "/v1/execute",
        json=valid_execute_payload,
        headers=tenant_headers,
    )
    data = response.json()
    assert "status" in data
    assert "findings" in data
    assert "recommendations" in data
    assert "data" in data
    assert "result_data" in data
    assert "tools_called" in data
    assert "reasoning_steps" in data
