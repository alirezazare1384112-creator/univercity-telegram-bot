"""AES-GCM envelope encryption for stored link credentials.

Layout
------

Every stored credential is a JSON document::

    {"username": "sara", "password": "secret"}

Encryption is *envelope*: each row gets its own random 32-byte ``data_key``
used for AES-GCM, and the data key itself is wrapped (encrypted) with the
``CREDENTIALS_MASTER_KEY`` read from the environment. This way:

* Rotating the master key only requires re-wrapping the data keys, not
  re-encrypting every payload.
* A leaked data key cannot decrypt other rows.
* The database stores only ciphertext; plaintext never touches disk.

Stored columns
--------------

For each credential row we persist three columns:

* ``ciphertext``  – base64( nonce || ciphertext || tag )  (the payload)
* ``wrapped_key`` – base64( AES-GCM(master_key, data_key) )
* ``nonce``       – not stored separately, it is the first 12 bytes of
                    ``ciphertext`` (GCM standard layout).

Failure mode
------------

If the master key is missing or invalid, every operation raises
``CredentialKeyError``. The API layer turns this into HTTP 503 so the
Mini App shows "feature disabled" instead of silently storing plaintext.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_LENGTH = 32  # AES-256
_NONCE_LENGTH = 12  # GCM standard


class CredentialKeyError(RuntimeError):
    """Raised when the master key is missing, malformed, or wrong."""


@dataclass(slots=True)
class _MasterKey:
    """Decoded AESGCM instance built from the base64 env var."""

    aesgcm: AESGCM

    @classmethod
    def from_b64(cls, raw: str) -> _MasterKey:
        if not raw:
            raise CredentialKeyError("CREDENTIALS_MASTER_KEY is not set")
        try:
            key = base64.urlsafe_b64decode(raw.encode("ascii"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise CredentialKeyError("CREDENTIALS_MASTER_KEY is not valid base64") from exc
        if len(key) != _KEY_LENGTH:
            raise CredentialKeyError(
                f"CREDENTIALS_MASTER_KEY must decode to {_KEY_LENGTH} bytes, got {len(key)}"
            )
        return cls(aesgcm=AESGCM(key))


def _master_key() -> _MasterKey:
    """Read the master key from settings on every call (cheap, cached)."""
    from app.config import get_settings

    return _MasterKey.from_b64(get_settings().credentials_master_key)


def encrypt_credential(payload: dict[str, str]) -> tuple[bytes, bytes]:
    """Return ``(ciphertext, wrapped_key)`` for storage.

    Both fields are stored as ``nonce || ct || tag`` (the layout that
    ``AESGCM.encrypt`` returns when given a separate nonce). The first
    12 bytes are the nonce; the rest is the ciphertext+tag.
    """
    if not payload:
        raise ValueError("payload must not be empty")
    master = _master_key()

    # Fresh per-row data key.
    data_key = os.urandom(_KEY_LENGTH)
    data_aesgcm = AESGCM(data_key)

    nonce = os.urandom(_NONCE_LENGTH)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = data_aesgcm.encrypt(nonce, plaintext, associated_data=None)
    ciphertext = nonce + ct

    # Wrap the data key with the master key. AESGCM.encrypt returns
    # ``ct || tag`` (no nonce), so we prepend our own nonce.
    wrap_nonce = os.urandom(_NONCE_LENGTH)
    wrapped_ct = master.aesgcm.encrypt(wrap_nonce, data_key, associated_data=None)
    wrapped_key = wrap_nonce + wrapped_ct

    return ciphertext, wrapped_key


def decrypt_credential(ciphertext: bytes, wrapped_key: bytes) -> dict[str, str]:
    """Reverse of :func:`encrypt_credential`.

    Raises ``CredentialKeyError`` when the master key is wrong or missing
    (the wrapped key cannot be unwrapped) or when the ciphertext has been
    tampered with (InvalidTag).
    """
    if len(ciphertext) < _NONCE_LENGTH + 16:
        raise ValueError("ciphertext too short")
    if len(wrapped_key) < _NONCE_LENGTH + 16:
        raise ValueError("wrapped_key too short")
    master = _master_key()

    # Unwrap the data key.
    wrap_nonce = wrapped_key[:_NONCE_LENGTH]
    wrapped_ct = wrapped_key[_NONCE_LENGTH:]
    try:
        data_key = master.aesgcm.decrypt(wrap_nonce, wrapped_ct, associated_data=None)
    except InvalidTag as exc:
        raise CredentialKeyError("wrapped key cannot be decrypted (master key mismatch?)") from exc

    if len(data_key) != _KEY_LENGTH:
        raise CredentialKeyError("unwrapped data key has wrong length")

    # Decrypt the payload with the unwrapped data key.
    data_aesgcm = AESGCM(data_key)
    nonce = ciphertext[:_NONCE_LENGTH]
    ct = ciphertext[_NONCE_LENGTH:]
    try:
        plaintext = data_aesgcm.decrypt(nonce, ct, associated_data=None)
    except InvalidTag as exc:
        raise CredentialKeyError("ciphertext tampered with or wrong key") from exc

    try:
        result = json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CredentialKeyError("decrypted payload is not valid JSON") from exc
    if not isinstance(result, dict):
        raise CredentialKeyError("decrypted payload is not a JSON object")
    return result


def to_storage(ciphertext: bytes, wrapped_key: bytes) -> dict[str, str]:
    """Base64-encode both fields for TEXT column storage."""
    return {
        "ciphertext_b64": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        "wrapped_key_b64": base64.urlsafe_b64encode(wrapped_key).decode("ascii"),
    }


def from_storage(ciphertext_b64: str, wrapped_key_b64: str) -> tuple[bytes, bytes]:
    """Reverse of :func:`to_storage`."""
    return (
        base64.urlsafe_b64decode(ciphertext_b64.encode("ascii")),
        base64.urlsafe_b64decode(wrapped_key_b64.encode("ascii")),
    )


__all__ = [
    "CredentialKeyError",
    "decrypt_credential",
    "encrypt_credential",
    "from_storage",
    "to_storage",
]
