"""DatabasePersistence (serverless) round-trip tests."""

from __future__ import annotations

import pytest

from app.persistence import DatabasePersistence


@pytest.mark.asyncio
async def test_user_and_bot_data_roundtrip(db):
    persistence = DatabasePersistence()

    await persistence.update_user_data(42, {"lang": "fa", "step": 3})
    await persistence.update_chat_data(7, {"notes": [1, 2]})
    await persistence.update_bot_data({"flag": True})

    assert (await persistence.get_user_data())[42] == {"lang": "fa", "step": 3}
    assert (await persistence.get_chat_data())[7] == {"notes": [1, 2]}
    assert await persistence.get_bot_data() == {"flag": True}

    user_data: dict[int, dict] = {}
    await persistence.refresh_user_data(42, user_data)
    assert user_data == {"lang": "fa", "step": 3}

    await persistence.drop_user_data(42)
    assert 42 not in await persistence.get_user_data()


@pytest.mark.asyncio
async def test_conversations_tuple_keys_roundtrip(db):
    persistence = DatabasePersistence()

    await persistence.update_conversation("menu_flow", (42, 7), "AWAITING_PICK")
    conversations = await persistence.get_conversations("menu_flow")
    assert conversations == {(42, 7): "AWAITING_PICK"}

    # a finished conversation stores None -> the entry disappears
    await persistence.update_conversation("menu_flow", (42, 7), None)
    assert await persistence.get_conversations("menu_flow") == {}
    # unknown conversation names are simply empty
    assert await persistence.get_conversations("never_used") == {}


@pytest.mark.asyncio
async def test_callback_data_roundtrip(db):
    persistence = DatabasePersistence()

    assert await persistence.get_callback_data() is None

    payload = (
        [("uuid-1", 1712345678.5, {"a": "b"})],
        {"42:99": "uuid-1"},
    )
    await persistence.update_callback_data(payload)
    cached, index = await persistence.get_callback_data()
    assert cached == [["uuid-1", 1712345678.5, {"a": "b"}]] or cached == [
        ("uuid-1", 1712345678.5, {"a": "b"})
    ]
    assert index == {"42:99": "uuid-1"}
