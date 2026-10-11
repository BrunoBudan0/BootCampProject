import hashlib
import hmac
import os
import secrets

HASH_SCHEME = "scrypt"
SCRYPT_COST = 2**14
SCRYPT_BLOCK_SIZE = 8
SCRYPT_PARALLELISM = 1
SALT_BYTES = 16
DERIVED_KEY_BYTES = 32
FIELD_SEPARATOR = "$"


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    derived_key = derive_key(password, salt, SCRYPT_COST, SCRYPT_BLOCK_SIZE, SCRYPT_PARALLELISM)

    return FIELD_SEPARATOR.join(
        [
            HASH_SCHEME,
            str(SCRYPT_COST),
            str(SCRYPT_BLOCK_SIZE),
            str(SCRYPT_PARALLELISM),
            salt.hex(),
            derived_key.hex(),
        ]
    )


def password_matches(password: str, stored_hash: str) -> bool:
    _, cost, block_size, parallelism, salt_hex, derived_key_hex = stored_hash.split(FIELD_SEPARATOR)
    derived_key = derive_key(password, bytes.fromhex(salt_hex), int(cost), int(block_size), int(parallelism))

    return hmac.compare_digest(derived_key, bytes.fromhex(derived_key_hex))


def derive_key(password: str, salt: bytes, cost: int, block_size: int, parallelism: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=cost,
        r=block_size,
        p=parallelism,
        dklen=DERIVED_KEY_BYTES,
    )


PASSWORD_HASH_OF_NOBODY = hash_password(secrets.token_urlsafe(32))
