import asyncio
from types import SimpleNamespace

from fastapi import FastAPI

from src.web.routes import accounts


class DummyDb:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_accounts_router_registers_codex2api_paths():
    app = FastAPI()
    app.include_router(accounts.router, prefix="/accounts")

    paths = {route.path for route in app.routes}

    assert "/accounts/batch-upload-codex2api" in paths
    assert "/accounts/{account_id}/upload-codex2api" in paths


def test_upload_account_to_codex2api_calls_uploader(monkeypatch):
    captured = {}

    monkeypatch.setattr(accounts, "get_db", lambda: DummyDb())
    monkeypatch.setattr(
        accounts.crud,
        "get_codex2api_service_by_id",
        lambda db, service_id: SimpleNamespace(
            id=service_id,
            api_url="https://codex2api.example.com",
            admin_key="admin-secret",
            proxy_url="http://proxy.local:8080",
        ),
    )
    monkeypatch.setattr(
        accounts.crud,
        "get_account_by_id",
        lambda db, account_id: SimpleNamespace(
            id=account_id,
            email="tester@example.com",
            refresh_token="rt-123",
            access_token="at-123",
        ),
    )

    def fake_upload(account, api_url, admin_key, proxy_url=None):
        captured["account"] = account
        captured["api_url"] = api_url
        captured["admin_key"] = admin_key
        captured["proxy_url"] = proxy_url
        return True, "上传成功"

    monkeypatch.setattr(accounts, "upload_to_codex2api", fake_upload)

    result = asyncio.run(
        accounts.upload_account_to_codex2api(
            11,
            accounts.Codex2ApiUploadRequest(service_id=7),
        )
    )

    assert result == {"success": True, "message": "上传成功", "error": None}
    assert captured["api_url"] == "https://codex2api.example.com"
    assert captured["admin_key"] == "admin-secret"
    assert captured["proxy_url"] == "http://proxy.local:8080"
    assert captured["account"].id == 11


def test_batch_upload_accounts_to_codex2api_uses_resolved_ids(monkeypatch):
    captured = {}

    monkeypatch.setattr(accounts, "get_db", lambda: DummyDb())
    monkeypatch.setattr(
        accounts.crud,
        "get_codex2api_services",
        lambda db, enabled=True: [
            SimpleNamespace(
                id=1,
                api_url="https://codex2api.example.com",
                admin_key="admin-secret",
                proxy_url="http://proxy.local:8080",
            )
        ],
    )
    monkeypatch.setattr(accounts, "resolve_account_ids", lambda *args, **kwargs: [3, 4])

    def fake_batch_upload(ids, api_url, admin_key, proxy_url=None):
        captured["ids"] = ids
        captured["api_url"] = api_url
        captured["admin_key"] = admin_key
        captured["proxy_url"] = proxy_url
        return {"success_count": 2, "failed_count": 0, "skipped_count": 0, "details": []}

    monkeypatch.setattr(accounts, "batch_upload_to_codex2api", fake_batch_upload)

    result = asyncio.run(
        accounts.batch_upload_accounts_to_codex2api(
            accounts.BatchCodex2ApiUploadRequest(
                ids=[1],
                select_all=False,
                service_id=None,
            )
        )
    )

    assert result["success_count"] == 2
    assert captured["ids"] == [3, 4]
    assert captured["api_url"] == "https://codex2api.example.com"
    assert captured["admin_key"] == "admin-secret"
    assert captured["proxy_url"] == "http://proxy.local:8080"
