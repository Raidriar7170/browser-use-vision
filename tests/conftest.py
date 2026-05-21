"""
pytest conftest — 统一设置环境变量，避免 browser-use 初始化报错
"""

import os
import tempfile

# browser-use 0.12.7 在导入时会尝试创建 ~/.config/browseruse/
# 使用临时目录避免权限问题
os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(tempfile.gettempdir(), "browseruse_test_config"))
