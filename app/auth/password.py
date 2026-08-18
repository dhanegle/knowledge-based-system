"""密码哈希工具（直接使用 bcrypt，不依赖已停止维护的 passlib）。"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """ bcrypt 要求密码不超过 72 字节，截断后哈希。"""
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
