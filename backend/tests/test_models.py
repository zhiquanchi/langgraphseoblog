import logging

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AppSettings, LLMCall, Provider


@pytest.fixture()
def tmp_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def tmp_session(tmp_engine):
    with Session(tmp_engine) as session:
        yield session


def test_tables_created(tmp_engine) -> None:
    inspector = inspect(tmp_engine)
    tables = set(inspector.get_table_names())
    assert {"providers", "app_settings", "llm_calls"} <= tables

    llm_calls_indexes = {ix["name"] for ix in inspector.get_indexes("llm_calls")}
    assert {"idx_llm_calls_created", "idx_llm_calls_provider"} <= llm_calls_indexes


def test_provider_create(tmp_session) -> None:
    provider = Provider(
        name="openai-gpt4o",
        type="openai",
        api_key="sk-test-1234",
        default_model="gpt-4o",
        priority=10,
    )
    tmp_session.add(provider)
    tmp_session.commit()
    tmp_session.refresh(provider)

    assert provider.id is not None
    assert provider.name == "openai-gpt4o"
    assert provider.type == "openai"
    assert provider.base_url is None
    assert provider.enabled is True
    assert provider.priority == 10
    assert provider.created_at is not None
    assert provider.updated_at is not None


def test_provider_name_unique(tmp_session) -> None:
    tmp_session.add(Provider(name="dup", type="openai", api_key="k1", default_model="m"))
    tmp_session.commit()

    tmp_session.add(Provider(name="dup", type="anthropic", api_key="k2", default_model="m"))
    with pytest.raises(IntegrityError):
        tmp_session.commit()


def test_app_settings_singleton(tmp_session) -> None:
    settings = AppSettings(
        id=1, default_provider_id=1, fallback_provider_ids="[2, 3]", node_routing='{"outline": 1}'
    )
    tmp_session.add(settings)
    tmp_session.commit()

    duplicate = AppSettings(id=2)
    tmp_session.add(duplicate)
    with pytest.raises(IntegrityError):
        tmp_session.commit()


def test_llm_call_defaults(tmp_session) -> None:
    call = LLMCall(provider_name="openai", model="gpt-4o", success=True)
    tmp_session.add(call)
    tmp_session.commit()
    tmp_session.refresh(call)

    assert call.prompt_tokens == 0
    assert call.completion_tokens == 0
    assert call.total_tokens == 0
    assert call.latency_ms == 0
    assert call.failover_from == "[]"
    assert call.node is None
    assert call.error is None
    assert call.created_at is not None


def test_api_key_not_in_logs_or_repr(tmp_session, caplog) -> None:
    secret = "sk-secret-key-abcdef0123456789"
    provider = Provider(name="secure-provider", type="openai", api_key=secret, default_model="gpt-4o")

    logger = logging.getLogger("app.models")
    with caplog.at_level(logging.DEBUG):
        tmp_session.add(provider)
        tmp_session.commit()
        logger.info("created %r", provider)
        logger.info("provider row: %s", provider)

    assert secret not in repr(provider)
    assert secret not in caplog.text
