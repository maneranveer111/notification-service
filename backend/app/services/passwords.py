import base64
import hashlib
import hmac
import os


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding < 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("ascii"))


def hash_password(password: str, n: int = 2**14, r: int = 8, p: int = 1) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=0)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = _unb64(parts[4])
        expected_dk = _unb64(parts[5])
        actual_dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=0)
        return hmac.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False

