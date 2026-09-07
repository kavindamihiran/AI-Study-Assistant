from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path


_VERSION = "v1"
_NONCE_BYTES = 16
_BLOCK_BYTES = 32


class SecretDecryptionError(RuntimeError):
    """Raised when a stored secret cannot be decrypted with the current key."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class SecretBox:
    """Authenticated symmetric encryption for user-supplied provider API keys.

    Uses a stdlib-only encrypt-then-MAC construction: an HMAC-SHA256 counter-mode
    keystream for confidentiality and a separate HMAC-SHA256 tag for integrity, so
    no extra dependency is required to keep API keys out of the database in plain
    text.
    """

    def __init__(self, passphrase: str) -> None:
        if not passphrase:
            raise ValueError("SecretBox requires a non-empty passphrase")
        material = hashlib.scrypt(
            passphrase.encode("utf-8"),
            salt=b"studyos.user-model-credentials.v1",
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )
        self._encryption_key = material[:32]
        self._mac_key = material[32:]

    @classmethod
    def from_env_or_file(cls, key_file: Path, env_value: str | None = None) -> "SecretBox":
        """Build a box from the configured passphrase, generating one if absent.

        A deployment should set ``SECRET_ENCRYPTION_KEY``; local development falls
        back to a generated key persisted next to the SQLite database so restarts
        can still read previously saved keys.
        """
        passphrase = (env_value or "").strip()
        if passphrase:
            return cls(passphrase)
        if key_file.exists():
            passphrase = key_file.read_text(encoding="utf-8").strip()
        if not passphrase:
            passphrase = secrets.token_urlsafe(48)
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(passphrase, encoding="utf-8")
            try:
                os.chmod(key_file, 0o600)
            except OSError:
                pass
        return cls(passphrase)

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block = hmac.new(
                self._encryption_key,
                nonce + counter.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])

    def _tag(self, nonce: bytes, ciphertext: bytes) -> bytes:
        return hmac.new(
            self._mac_key, nonce + ciphertext, hashlib.sha256
        ).digest()

    def encrypt(self, plaintext: str) -> str:
        raw = plaintext.encode("utf-8")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = bytes(
            byte ^ key_byte
            for byte, key_byte in zip(raw, self._keystream(nonce, len(raw)))
        )
        tag = self._tag(nonce, ciphertext)
        return ".".join(
            (_VERSION, _b64encode(nonce), _b64encode(ciphertext), _b64encode(tag))
        )

    def decrypt(self, token: str) -> str:
        try:
            version, nonce_part, ciphertext_part, tag_part = token.split(".")
            if version != _VERSION:
                raise ValueError(f"Unsupported secret version: {version}")
            nonce = _b64decode(nonce_part)
            ciphertext = _b64decode(ciphertext_part)
            tag = _b64decode(tag_part)
        except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
            raise SecretDecryptionError("Stored secret is malformed") from exc
        if not hmac.compare_digest(tag, self._tag(nonce, ciphertext)):
            raise SecretDecryptionError(
                "Stored secret could not be verified with the current encryption key"
            )
        plaintext = bytes(
            byte ^ key_byte
            for byte, key_byte in zip(
                ciphertext, self._keystream(nonce, len(ciphertext))
            )
        )
        return plaintext.decode("utf-8")


def mask_secret(value: str) -> str:
    """Return a display-safe hint for a stored API key."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 6}{value[-4:]}"
