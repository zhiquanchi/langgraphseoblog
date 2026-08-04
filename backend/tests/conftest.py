"""pytest 全局配置：在导入 app 前将数据库指向临时目录，避免污染真实 app.db。"""

import os
import shutil
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="langgraphseoblog-tests-")
os.environ["SQLITE_PATH"] = os.path.join(_TEST_DB_DIR, "test.db")


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
