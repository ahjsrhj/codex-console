import asyncio
from contextlib import contextmanager
from pathlib import Path

from src.config.constants import EmailServiceType
from src.database.models import Base, EmailService
from src.database.session import DatabaseSessionManager
from src.services.base import EmailServiceFactory
from src.web.routes import email as email_routes


def _build_manager(name: str) -> DatabaseSessionManager:
    runtime_dir = Path("tests_runtime")
    runtime_dir.mkdir(exist_ok=True)
    db_path = runtime_dir / name
    if db_path.exists():
        db_path.unlink()
    manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=manager.engine)
    return manager


def test_luckmail_service_registered():
    service_type = EmailServiceType("luckmail")
    service_class = EmailServiceFactory.get_service_class(service_type)
    assert service_class is not None
    assert service_class.__name__ == "LuckMailService"


def test_email_service_types_include_luckmail_account_list():
    result = asyncio.run(email_routes.get_service_types())
    luckmail_type = next(item for item in result["types"] if item["value"] == "luckmail")

    assert luckmail_type["label"] == "LuckMail"
    field_names = [field["name"] for field in luckmail_type["config_fields"]]
    assert "prefer_existing_account_list" in field_names
    assert "account_list_text" in field_names


def test_filter_sensitive_config_summarizes_luckmail_account_list():
    filtered = email_routes.filter_sensitive_config({
        "base_url": "https://mails.luckyous.com/",
        "api_key": "lm_test_key",
        "_service_record_id": 9,
        "account_list": [
            {"email": "first@example.com", "token": "tok_1", "used": False},
            {"email": "second@example.com", "token": "tok_2", "used": True},
        ],
    })

    assert filtered["base_url"] == "https://mails.luckyous.com/"
    assert filtered["has_api_key"] is True
    assert filtered["has_account_list"] is True
    assert filtered["account_list_total"] == 2
    assert filtered["account_list_unused"] == 1
    assert "account_list" not in filtered
    assert "_service_record_id" not in filtered


def test_create_luckmail_service_parses_account_list_and_list_hides_tokens(monkeypatch):
    manager = _build_manager("luckmail_routes_create.db")

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(email_routes, "get_db", fake_get_db)

    created = asyncio.run(email_routes.create_email_service(
        email_routes.EmailServiceCreate(
            service_type="luckmail",
            name="LuckMail Pool",
            config={
                "base_url": "https://mails.luckyous.com/",
                "api_key": "lm_test_key",
                "project_code": "openai",
                "email_type": "ms_graph",
                "prefer_existing_account_list": False,
                "account_list_text": "pool1@example.com----tok_pool1\npool2@example.com----tok_pool2",
            },
            enabled=True,
            priority=1,
        )
    ))

    with manager.session_scope() as session:
        service = session.query(EmailService).filter(EmailService.id == created.id).first()
        assert service is not None
        assert service.config["prefer_existing_account_list"] is False
        assert service.config["account_list"] == [
            {
                "email": "pool1@example.com",
                "token": "tok_pool1",
                "used": False,
                "used_at": None,
                "last_result": None,
                "last_task_uuid": None,
            },
            {
                "email": "pool2@example.com",
                "token": "tok_pool2",
                "used": False,
                "used_at": None,
                "last_result": None,
                "last_task_uuid": None,
            },
        ]
        assert "account_list_text" not in service.config

    listed = asyncio.run(email_routes.list_email_services(service_type="luckmail", enabled_only=False))
    assert listed.total == 1
    assert listed.services[0].config["prefer_existing_account_list"] is False
    assert listed.services[0].config["has_account_list"] is True
    assert listed.services[0].config["account_list_total"] == 2
    assert listed.services[0].config["account_list_unused"] == 2
    assert "account_list" not in listed.services[0].config

    full = asyncio.run(email_routes.get_email_service_full(created.id))
    assert full["config"]["prefer_existing_account_list"] is False
    assert full["config"]["account_list_text"] == "pool1@example.com----tok_pool1\npool2@example.com----tok_pool2"
    assert full["config"]["account_list"][0]["token"] == "tok_pool1"


def test_create_luckmail_service_rejects_invalid_account_list(monkeypatch):
    manager = _build_manager("luckmail_routes_invalid.db")

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(email_routes, "get_db", fake_get_db)

    request = email_routes.EmailServiceCreate(
        service_type="luckmail",
        name="LuckMail Invalid",
        config={
            "base_url": "https://mails.luckyous.com/",
            "api_key": "lm_test_key",
            "account_list_text": "bad-line-without-token",
        },
    )

    try:
        asyncio.run(email_routes.create_email_service(request))
    except email_routes.HTTPException as exc:
        assert exc.status_code == 400
        assert "第 1 行格式错误" in exc.detail
    else:
        raise AssertionError("expected invalid luckmail account list to be rejected")


def test_update_luckmail_service_preserves_used_state_and_supports_clear(monkeypatch):
    manager = _build_manager("luckmail_routes_update.db")

    with manager.session_scope() as session:
        service = EmailService(
            service_type="luckmail",
            name="LuckMail Existing",
            config={
                "base_url": "https://mails.luckyous.com/",
                "api_key": "lm_test_key",
                "account_list": [
                    {
                        "email": "used@example.com",
                        "token": "tok_used",
                        "used": True,
                        "used_at": "2026-04-01T00:00:00Z",
                        "last_result": "success",
                        "last_task_uuid": "task-old",
                    }
                ],
            },
            enabled=True,
            priority=0,
        )
        session.add(service)
        session.flush()
        service_id = service.id

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(email_routes, "get_db", fake_get_db)

    updated = asyncio.run(email_routes.update_email_service(
        service_id,
        email_routes.EmailServiceUpdate(
            config={
                "account_list_text": "used@example.com----tok_used\nfresh@example.com----tok_fresh",
            }
        )
    ))

    assert updated.config["account_list_total"] == 2
    assert updated.config["account_list_unused"] == 1

    with manager.session_scope() as session:
        service = session.query(EmailService).filter(EmailService.id == service_id).first()
        assert service.config["account_list"][0]["used"] is True
        assert service.config["account_list"][0]["used_at"] == "2026-04-01T00:00:00Z"
        assert service.config["account_list"][0]["last_result"] == "success"
        assert service.config["account_list"][1]["used"] is False

    asyncio.run(email_routes.update_email_service(
        service_id,
        email_routes.EmailServiceUpdate(config={"account_list_text": ""})
    ))

    with manager.session_scope() as session:
        service = session.query(EmailService).filter(EmailService.id == service_id).first()
        assert service.config["account_list"] == []
