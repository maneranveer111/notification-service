import json
from typing import Any
from cryptography.fernet import Fernet, MultiFernet, InvalidToken

from app.config import get_settings


class CryptoNotConfigured(Exception):
    pass


def _get_multi_fernet() -> MultiFernet:
    settings = get_settings()
    key_str = settings.encryption_key
    if not key_str or not key_str.strip():
        raise CryptoNotConfigured("Encryption is not configured on this server")

    keys = [k.strip() for k in key_str.split(",") if k.strip()]
    if not keys:
        raise CryptoNotConfigured("Encryption is not configured on this server")

    fernets = []
    for k in keys:
        try:
            fernets.append(Fernet(k.encode("utf-8")))
        except Exception:
            raise CryptoNotConfigured("Encryption is not configured on this server")

    return MultiFernet(fernets)


def encrypt_json(data: dict[str, Any]) -> str:
    """
    Encrypt a dictionary to a Fernet token string.
    First key in MultiFernet is used for encryption.
    """
    mf = _get_multi_fernet()
    raw = json.dumps(data).encode("utf-8")
    return mf.encrypt(raw).decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    """
    Decrypt a Fernet token string back into a dictionary.
    All keys in MultiFernet are tried for decryption (supporting rotation).
    """
    mf = _get_multi_fernet()
    try:
        raw = mf.decrypt(token.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except InvalidToken:
        raise ValueError("Invalid or corrupted ciphertext")
    except Exception as e:
        raise ValueError(f"Failed to decrypt data: {e}")

