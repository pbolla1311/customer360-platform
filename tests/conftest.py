import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import Base


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    with TestingSession() as database_session:
        yield database_session

    Base.metadata.drop_all(engine)


@pytest.fixture
def repository(session: Session) -> Customer360Repository:
    return Customer360Repository(session)