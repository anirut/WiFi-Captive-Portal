import pytest
import uuid


@pytest.mark.asyncio
async def test_list_sessions_returns_empty(client):
    response = await client.get("/admin/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_kick_nonexistent_session_returns_404(client):
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/admin/sessions/{fake_id}")
    assert response.status_code == 404
