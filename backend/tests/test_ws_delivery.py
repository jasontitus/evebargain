"""The WebSocket must register under the same id the server pushes to.

It registered under the client-supplied user_id -- which the frontend fills
with character_id -- while every push addresses the database user id. Alerts,
region changes, market updates and fetch progress were all broadcast to a key
with no connection on it.
"""

import pytest

from app.services.notification import ws_manager

DB_USER_ID = 1
CHARACTER_ID = 96347599


class FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload):
        self.sent.append(payload)


@pytest.fixture(autouse=True)
def _clear_connections():
    ws_manager._connections.clear()
    yield
    ws_manager._connections.clear()


@pytest.mark.asyncio
async def test_progress_reaches_a_connection_registered_by_db_user_id():
    ws = FakeWS()
    ws_manager._connections[DB_USER_ID] = [ws]

    await ws_manager.send_progress(DB_USER_ID, "region", "Kador", 3, 10)

    assert len(ws.sent) == 1
    assert ws.sent[0]["type"] == "fetch_progress"
    assert ws.sent[0]["data"]["completed"] == 3
    assert ws.sent[0]["data"]["total"] == 10
    assert ws.sent[0]["data"]["region_name"] == "Kador"


@pytest.mark.asyncio
async def test_registering_under_character_id_receives_nothing():
    """This is the shape of the original bug -- it must stay broken-by-design."""
    ws = FakeWS()
    ws_manager._connections[CHARACTER_ID] = [ws]

    await ws_manager.send_progress(DB_USER_ID, "region", "Kador", 3, 10)
    await ws_manager.send_alert(DB_USER_ID, {"type_name": "Thrasher"})

    assert ws.sent == []


@pytest.mark.asyncio
async def test_done_progress_is_flagged_so_the_bar_clears():
    ws = FakeWS()
    ws_manager._connections[DB_USER_ID] = [ws]

    await ws_manager.send_progress(DB_USER_ID, "compare", "Kador", 1, 1, done=True)

    assert ws.sent[0]["data"]["done"] is True
