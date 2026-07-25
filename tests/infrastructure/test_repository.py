import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import Base


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

    with testing_session() as database_session:
        yield database_session

    Base.metadata.drop_all(engine)


@pytest.fixture
def repository(session: Session) -> Customer360Repository:
    return Customer360Repository(session)


@pytest.fixture
def profile() -> Customer360Profile:
    return Customer360Profile(
        customer_id="1001",
        first_name="John",
        last_name="Smith",
        email="john.smith@example.com",
        city="Atlanta",
        state="GA",
        transaction_count=2,
        total_spend=145.49,
        average_transaction_value=72.745,
    )


def test_create_profile(
    repository: Customer360Repository,
    profile: Customer360Profile,
) -> None:
    created = repository.create(profile)

    assert created.customer_id == "1001"
    assert created.email == "john.smith@example.com"


def test_get_by_customer_id(
    repository: Customer360Repository,
    profile: Customer360Profile,
) -> None:
    repository.create(profile)

    result = repository.get_by_customer_id("1001")

    assert result is not None
    assert result.first_name == "John"


def test_get_missing_customer_returns_none(
    repository: Customer360Repository,
) -> None:
    result = repository.get_by_customer_id("missing")

    assert result is None


def test_list_all_orders_by_total_spend(
    repository: Customer360Repository,
) -> None:
    repository.create(
        Customer360Profile(
            customer_id="1001",
            first_name="John",
            last_name="Smith",
            email="john@example.com",
            transaction_count=1,
            total_spend=100.0,
            average_transaction_value=100.0,
        )
    )

    repository.create(
        Customer360Profile(
            customer_id="1002",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            transaction_count=2,
            total_spend=300.0,
            average_transaction_value=150.0,
        )
    )

    profiles = repository.list_all()

    assert [profile.customer_id for profile in profiles] == [
        "1002",
        "1001",
    ]


def test_update_profile(
    repository: Customer360Repository,
    profile: Customer360Profile,
) -> None:
    repository.create(profile)

    profile.total_spend = 500.0
    updated = repository.update(profile)

    assert updated.total_spend == 500.0


def test_delete_profile(
    repository: Customer360Repository,
    profile: Customer360Profile,
) -> None:
    repository.create(profile)

    deleted = repository.delete("1001")

    assert deleted is True
    assert repository.get_by_customer_id("1001") is None


def test_delete_missing_profile_returns_false(
    repository: Customer360Repository,
) -> None:
    deleted = repository.delete("missing")

    assert deleted is False