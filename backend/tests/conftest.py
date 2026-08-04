"""pytest 全局配置：在导入 app 前将数据库指向临时目录，避免污染真实 app.db。"""

import os
import shutil
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="langgraphseoblog-tests-")
os.environ["SQLITE_PATH"] = os.path.join(_TEST_DB_DIR, "test.db")

# SessionLocal 共享库：与应用启动行为一致，预建表供 LLM 工厂等直接使用 SessionLocal 的测试
from app import models  # noqa: E402,F401 — 确保模型注册到 Base.metadata
from app.db import Base, engine  # noqa: E402

Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
