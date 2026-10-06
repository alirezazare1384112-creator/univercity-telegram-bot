"""A fake PTB bot for API tests that move files through Telegram."""

from __future__ import annotations

from types import SimpleNamespace


class FakeTgFile:
    def __init__(self, file_path: str = "photos/pic_1.jpg", payload: bytes = b"\xff\xd8fake") -> None:
        self.file_path = file_path
        self._payload = payload

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self._payload)


class FakeBot:
    def __init__(self, *, file_path: str = "photos/pic_1.jpg", payload: bytes = b"\xff\xd8fake") -> None:
        self.file_path = file_path
        self.payload = payload
        self.sent: list[tuple[str, int]] = []
        self.deleted: list[int] = []
        self.get_file_calls: list[str] = []

    async def send_photo(self, *, chat_id: int, photo: object) -> SimpleNamespace:
        self.sent.append(("photo", chat_id))
        size = SimpleNamespace(file_id="PHOTO-FILE-1", file_unique_id="photo-unique-1")
        return SimpleNamespace(message_id=101, photo=[size], document=None)

    async def send_document(self, *, chat_id: int, document: object) -> SimpleNamespace:
        self.sent.append(("document", chat_id))
        doc = SimpleNamespace(file_id="DOC-FILE-1", file_unique_id="doc-unique-1")
        return SimpleNamespace(message_id=102, photo=None, document=doc)

    async def delete_message(self, *, chat_id: int, message_id: int) -> bool:
        self.deleted.append(message_id)
        return True

    async def get_file(self, file_id: str) -> FakeTgFile:
        self.get_file_calls.append(file_id)
        return FakeTgFile(self.file_path, self.payload)
