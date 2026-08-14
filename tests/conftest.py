import os
import socket
import tempfile
import threading
import time

from cryptography.fernet import Fernet

TEST_FAKE_PLATFORM_PORT = 9091

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="social_publisher_tests_")

os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATA_DIR}/test_app.db"
os.environ["JOBSTORE_URL"] = f"sqlite:///{_TEST_DATA_DIR}/test_jobs.db"
os.environ["FAKE_PLATFORM_URL"] = f"http://127.0.0.1:{TEST_FAKE_PLATFORM_PORT}"
os.environ["APP_WEBHOOK_URL"] = "http://testserver/webhooks/social-delivery"

import pytest
import uvicorn

from app.database import Base, engine
from app import models
from fake_platform.server import app as fake_platform_app

Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def live_fake_platform():
    config = uvicorn.Config(fake_platform_app, host="127.0.0.1", port=TEST_FAKE_PLATFORM_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", TEST_FAKE_PLATFORM_PORT))
        sock.close()
        if result == 0:
            break
        time.sleep(0.1)

    yield

    server.should_exit = True
    thread.join(timeout=5)