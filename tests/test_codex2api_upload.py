from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from src.core.upload import codex2api_upload
from src.database.models import Account, Base
from src.database.session import DatabaseSessionManager


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


def make_account(**kwargs):
    base = {
        "id": 1,
        "email": "tester@example.com",
        "refresh_token": "rt-123",
        "access_token": "at-123",
        "proxy_used": "http://account-proxy.local:8080",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_upload_to_codex2api_uses_refresh_token_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return FakeResponse(status_code=200, payload={"success": True})

    monkeypatch.setattr(codex2api_upload.cffi_requests, "post", fake_post)

    success, message = codex2api_upload.upload_to_codex2api(
        make_account(access_token="at-ignored"),
        "https://codex2api.example.com/",
        "admin-secret",
        proxy_url="http://service-proxy.local:9000",
    )

    assert success is True
    assert message == "上传成功"
    assert captured["url"] == "https://codex2api.example.com/api/admin/accounts"
    assert captured["json"]["refresh_token"] == "rt-123"
    assert captured["json"]["proxy_url"] == "http://service-proxy.local:9000"
    assert captured["headers"]["X-Admin-Key"] == "admin-secret"


def test_upload_to_codex2api_falls_back_to_access_token_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return FakeResponse(status_code=201, payload={"success": True})

    monkeypatch.setattr(codex2api_upload.cffi_requests, "post", fake_post)

    success, message = codex2api_upload.upload_to_codex2api(
        make_account(refresh_token="", access_token="at-only"),
        "https://codex2api.example.com",
        "admin-secret",
    )

    assert success is True
    assert message == "上传成功"
    assert captured["url"] == "https://codex2api.example.com/api/admin/accounts/at"
    assert captured["json"]["access_token"] == "at-only"
    assert captured["json"]["proxy_url"] == "http://account-proxy.local:8080"


def test_test_codex2api_connection_uses_admin_header(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return FakeResponse(status_code=200, payload={"success": True})

    monkeypatch.setattr(codex2api_upload.cffi_requests, "get", fake_get)

    success, message = codex2api_upload.test_codex2api_connection(
        "https://codex2api.example.com/",
        "admin-secret",
    )

    assert success is True
    assert message == "Codex2Api 连接测试成功"
    assert captured["url"] == "https://codex2api.example.com/api/admin/accounts?page=1&limit=1"
    assert captured["headers"]["X-Admin-Key"] == "admin-secret"


def test_batch_upload_to_codex2api_counts_success_failure_and_skip(monkeypatch):
    runtime_dir = Path("tests_runtime")
    runtime_dir.mkdir(exist_ok=True)
    db_path = runtime_dir / "codex2api_upload.db"
    if db_path.exists():
        db_path.unlink()

    manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=manager.engine)

    with manager.session_scope() as session:
        session.add_all([
            Account(email="rt@example.com", email_service="tempmail", refresh_token="rt-1"),
            Account(email="skip@example.com", email_service="tempmail"),
            Account(email="at@example.com", email_service="tempmail", access_token="at-3"),
        ])

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def fake_upload(account, api_url, admin_key, proxy_url=None):
        if account.email == "at@example.com":
            return False, "远端拒绝"
        return True, "上传成功"

    monkeypatch.setattr(codex2api_upload, "get_db", fake_get_db)
    monkeypatch.setattr(codex2api_upload, "upload_to_codex2api", fake_upload)

    results = codex2api_upload.batch_upload_to_codex2api(
        [1, 2, 3, 999],
        "https://codex2api.example.com",
        "admin-secret",
    )

    assert results["success_count"] == 1
    assert results["skipped_count"] == 1
    assert results["failed_count"] == 2
    assert any(item["email"] == "rt@example.com" and item["success"] for item in results["details"])
    assert any(item["email"] == "skip@example.com" and item["error"] == "缺少 refresh_token 和 access_token" for item in results["details"])
    assert any(item["email"] == "at@example.com" and item["error"] == "远端拒绝" for item in results["details"])
