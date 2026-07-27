import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from customer360.infrastructure.session import Base
from customer360.outbox.models import OutboxEvent
from customer360.outbox.repository import OutboxRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with testing_session() as db_session:
        yield db_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def outbox_repository(session: Session) -> OutboxRepository:
    return OutboxRepository(session)


def test_get_by_event_id_returns_the_matching_row(
    outbox_repository: OutboxRepository,
) -> None:
    outbox_repository.add(event_id="evt-1", event_type="UPSERTED", payload="{}")

    found = outbox_repository.get_by_event_id("evt-1")

    assert found is not None
    assert found.event_id == "evt-1"


def test_get_by_event_id_returns_none_when_missing(
    outbox_repository: OutboxRepository,
) -> None:
    assert outbox_repository.get_by_event_id("does-not-exist") is None


def test_delete_by_event_ids_removes_only_the_named_rows(
    outbox_repository: OutboxRepository,
) -> None:
    outbox_repository.add(event_id="evt-keep", event_type="UPSERTED", payload="{}")
    outbox_repository.add(event_id="evt-remove", event_type="UPSERTED", payload="{}")

    deleted = outbox_repository.delete_by_event_ids(["evt-remove"])

    assert deleted == 1
    assert outbox_repository.get_by_event_id("evt-remove") is None
    assert outbox_repository.get_by_event_id("evt-keep") is not None


def test_delete_by_event_ids_with_empty_list_is_a_no_op(
    outbox_repository: OutboxRepository,
) -> None:
    outbox_repository.add(event_id="evt-1", event_type="UPSERTED", payload="{}")

    assert outbox_repository.delete_by_event_ids([]) == 0
    assert outbox_repository.get_by_event_id("evt-1") is not None


def test_outbox_model_defaults():
    event = OutboxEvent(
        event_id="123",
        event_type="UPSERTED",
        payload='{"id":"123"}',
        status="PENDING",
    )

    assert event.event_id == "123"
    assert event.event_type == "UPSERTED"
    assert event.payload == '{"id":"123"}'
    assert event.status == "PENDING"


def test_mark_published_fields():
    event = OutboxEvent(
        event_id="456",
        event_type="UPSERTED",
        payload='{"id":"456"}',
        status="PUBLISHED",
    )

    assert event.status == "PUBLISHED"