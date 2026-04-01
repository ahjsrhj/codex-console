from contextlib import contextmanager
from pathlib import Path

from src.database.models import Base, EmailService
from src.database.session import DatabaseSessionManager
from src.services import luckmail_mail as luckmail_module
from src.services.luckmail_mail import LuckMailService


class FakeLuckMailUser:
    def __init__(self, code="654321"):
        self.code = code
        self.token_code_calls = []

    def get_token_code(self, token):
        self.token_code_calls.append(token)
        return {
            "has_new_mail": True,
            "verification_code": self.code,
        }

    def get_balance(self):
        return "100.0000"


def _build_manager(name: str) -> DatabaseSessionManager:
    runtime_dir = Path("tests_runtime")
    runtime_dir.mkdir(exist_ok=True)
    db_path = runtime_dir / name
    if db_path.exists():
        db_path.unlink()
    manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=manager.engine)
    return manager


def _build_service(config=None):
    luckmail_module._CUSTOM_ACCOUNT_RESERVATIONS.clear()
    base_config = {
        "base_url": "https://mails.luckyous.com/",
        "api_key": "lm_test_key",
        "project_code": "openai",
        "email_type": "ms_graph",
    }
    service = LuckMailService({**base_config, **(config or {})})
    return service


def test_create_email_prefers_custom_account_pool_and_uses_token_code_endpoint():
    service = _build_service({
        "account_list": [
            {"email": "pool1@example.com", "token": "tok_pool1", "used": False},
            {"email": "pool2@example.com", "token": "tok_pool2", "used": False},
        ],
        "_service_record_id": "101",
    })
    fake_user = FakeLuckMailUser(code="112233")
    service.client = type("FakeLuckMailClient", (), {"user": fake_user})()

    email_info = service.create_email()
    code = service.get_verification_code(
        email=email_info["email"],
        email_id=email_info["service_id"],
        timeout=1,
    )

    assert email_info["email"] == "pool1@example.com"
    assert email_info["service_id"] == "tok_pool1"
    assert email_info["token"] == "tok_pool1"
    assert email_info["source"] == "custom_account_pool"
    assert code == "112233"
    assert fake_user.token_code_calls == ["tok_pool1"]


def test_create_email_falls_back_to_purchase_when_custom_pool_is_exhausted():
    service = _build_service({
        "account_list": [
            {"email": "used@example.com", "token": "tok_used", "used": True},
        ],
    })

    def fake_purchase(project_code, email_type, preferred_domain):
        return {
            "id": "tok_fallback",
            "service_id": "tok_fallback",
            "order_no": "",
            "email": "fallback@example.com",
            "token": "tok_fallback",
            "purchase_id": "purchase-1",
            "inbox_mode": "purchase",
            "project_code": project_code,
            "email_type": email_type,
            "preferred_domain": preferred_domain,
            "expired_at": "",
            "created_at": 0,
            "source": "new_purchase",
        }

    service._create_purchase_inbox = fake_purchase

    email_info = service.create_email()

    assert email_info["email"] == "fallback@example.com"
    assert email_info["source"] == "new_purchase"


def test_create_email_skips_custom_account_pool_when_prefer_existing_account_list_disabled():
    service = _build_service({
        "prefer_existing_account_list": False,
        "account_list": [
            {"email": "pool1@example.com", "token": "tok_pool1", "used": False},
        ],
    })

    def fake_purchase(project_code, email_type, preferred_domain):
        return {
            "id": "tok_fallback",
            "service_id": "tok_fallback",
            "order_no": "",
            "email": "fallback@example.com",
            "token": "tok_fallback",
            "purchase_id": "purchase-1",
            "inbox_mode": "purchase",
            "project_code": project_code,
            "email_type": email_type,
            "preferred_domain": preferred_domain,
            "expired_at": "",
            "created_at": 0,
            "source": "new_purchase",
        }

    service._create_purchase_inbox = fake_purchase

    email_info = service.create_email()

    assert email_info["email"] == "fallback@example.com"
    assert email_info["source"] == "new_purchase"
    assert service.config["account_list"][0]["used"] is False


def test_mark_registration_outcome_marks_custom_account_used_in_database(monkeypatch, tmp_path):
    manager = _build_manager("luckmail_service_mark_used.db")

    with manager.session_scope() as session:
        db_service = EmailService(
            service_type="luckmail",
            name="LuckMail Pool",
            config={
                "base_url": "https://mails.luckyous.com/",
                "api_key": "lm_test_key",
                "account_list": [
                    {
                        "email": "pool1@example.com",
                        "token": "tok_pool1",
                        "used": False,
                        "used_at": None,
                        "last_result": None,
                        "last_task_uuid": None,
                    }
                ],
            },
            enabled=True,
            priority=0,
        )
        session.add(db_service)
        session.flush()
        service_record_id = db_service.id

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    import src.database.session as session_module

    monkeypatch.setattr(session_module, "get_db", fake_get_db)

    service = _build_service({
        "_service_record_id": str(service_record_id),
        "account_list": [
            {
                "email": "pool1@example.com",
                "token": "tok_pool1",
                "used": False,
                "used_at": None,
                "last_result": None,
                "last_task_uuid": None,
            }
        ],
    })
    service._data_dir = tmp_path
    service._registered_file = tmp_path / "luckmail_registered.json"
    service._failed_file = tmp_path / "luckmail_failed.json"

    service.mark_registration_outcome(
        email="pool1@example.com",
        success=False,
        reason="未收到验证码",
        context={
            "source": "custom_account_pool",
            "service_id": "tok_pool1",
            "token": "tok_pool1",
            "task_uuid": "task-1",
        },
    )

    with manager.session_scope() as session:
        stored = session.query(EmailService).filter(EmailService.id == service_record_id).first()
        entry = stored.config["account_list"][0]
        assert entry["used"] is True
        assert entry["used_at"]
        assert entry["last_result"] == "未收到验证码"
        assert entry["last_task_uuid"] == "task-1"


def test_multiple_instances_do_not_allocate_same_custom_account():
    shared_config = {
        "_service_record_id": "shared-1",
        "account_list": [
            {"email": "pool1@example.com", "token": "tok_pool1", "used": False},
            {"email": "pool2@example.com", "token": "tok_pool2", "used": False},
        ],
    }
    service_one = _build_service(shared_config)
    service_two = _build_service(shared_config)

    first = service_one.create_email()
    second = service_two.create_email()

    assert first["email"] == "pool1@example.com"
    assert second["email"] == "pool2@example.com"
