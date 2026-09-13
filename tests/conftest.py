"""测试全局配置：让测试自包含，不依赖开发机上的 .env。

背景：CI 通过 git clone 获取代码，仓库里没有 .env（已 gitignore）。
而 app.main 启动时会做安全校验——debug 关闭且 JWT 密钥仍为默认值时
直接拒绝启动（见 app/main.py 的 _validate_jwt_secret）。开发机上 .env
设了 ZHIYUAN_DEBUG=true，本地因此能过；CI 上 debug 取默认值 False，
校验抛 RuntimeError，所有依赖 create_app() 的测试随之失败。

在导入任何 app 模块之前注入测试用环境变量即可消除这个环境差异。

注意：app.config.settings 是模块级单例，导入即固化，所以必须写在
conftest 顶层——pytest 会在收集测试模块之前先导入它。
"""

import os

# 用 setdefault：若开发者已在 shell 里显式指定，则以显式值为准。
os.environ.setdefault("ZHIYUAN_DEBUG", "true")
os.environ.setdefault("ZHIYUAN_JWT_SECRET", "test-only-jwt-secret-not-for-production")
