"""鉴权模块：JWT 令牌 + 用户注册/登录。"""

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.jwt import create_access_token, decode_access_token
from app.auth.models import User

__all__ = [
    "CurrentUser",
    "User",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
]
