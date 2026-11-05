"""Memory-hard password hashing using Python's standard-library scrypt."""

import base64
import hashlib
import hmac
import secrets


_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LENGTH = 64
_MAX_PASSWORD_LENGTH = 1024
_MAX_MEMORY = 64 * 1024 * 1024


class PasswordHasher:
    """Create and verify versioned, salted scrypt password hashes."""

    def hash_password(self, password: str) -> str:
        if not isinstance(password, str) or not 12 <= len(password) <= _MAX_PASSWORD_LENGTH:
            raise ValueError("Password must contain between 12 and 1024 characters.")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_KEY_LENGTH,
            maxmem=_MAX_MEMORY,
        )
        return "scrypt${}${}${}${}${}".format(
            _SCRYPT_N,
            _SCRYPT_R,
            _SCRYPT_P,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )

    def verify_password(self, password: str, encoded_hash: str) -> bool:
        if not isinstance(password, str) or len(password) > _MAX_PASSWORD_LENGTH:
            return False
        try:
            algorithm, n_text, r_text, p_text, salt_text, digest_text = (
                encoded_hash.split("$")
            )
            if algorithm != "scrypt":
                return False
            n, r, p = int(n_text), int(r_text), int(p_text)
            if not (1 << 14) <= n <= (1 << 17) or r != 8 or p != 1:
                return False
            salt = base64.b64decode(salt_text, altchars=b"-_", validate=True)
            expected = base64.b64decode(
                digest_text,
                altchars=b"-_",
                validate=True,
            )
            if not 16 <= len(salt) <= 64 or len(expected) != _KEY_LENGTH:
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=n,
                r=r,
                p=p,
                dklen=len(expected),
                maxmem=_MAX_MEMORY,
            )
        except (AttributeError, ValueError, TypeError, UnicodeError):
            return False
        return hmac.compare_digest(actual, expected)

