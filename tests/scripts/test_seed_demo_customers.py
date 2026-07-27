import pytest
from sqlalchemy.orm import Session

from customer360.infrastructure.repository import Customer360Repository
from scripts.seed_demo_customers import (
    DEMO_CUSTOMERS,
    main,
    seed_demo_customers,
    seeding_enabled,
)


def test_seed_dataset_has_between_eight_and_twelve_records():
    assert 8 <= len(DEMO_CUSTOMERS) <= 12


def test_seed_dataset_uses_reserved_example_domains():
    for record in DEMO_CUSTOMERS:
        assert record["email"].endswith(("@example.com", "@example.org")), record[
            "email"
        ]


def test_seed_dataset_has_unique_customer_ids_and_emails():
    customer_ids = [record["customer_id"] for record in DEMO_CUSTOMERS]
    emails = [record["email"] for record in DEMO_CUSTOMERS]

    assert len(customer_ids) == len(set(customer_ids))
    assert len(emails) == len(set(emails))


def test_seed_demo_customers_creates_all_records(
    session: Session, repository: Customer360Repository
) -> None:
    result = seed_demo_customers(session)

    assert result.created == len(DEMO_CUSTOMERS)
    assert result.updated == 0
    assert len(repository.list_all()) == len(DEMO_CUSTOMERS)


def test_seed_demo_customers_is_idempotent(
    session: Session, repository: Customer360Repository
) -> None:
    seed_demo_customers(session)
    second_result = seed_demo_customers(session)

    assert second_result.created == 0
    assert second_result.updated == len(DEMO_CUSTOMERS)
    assert len(repository.list_all()) == len(DEMO_CUSTOMERS)


def test_seed_demo_customers_does_not_touch_created_at_on_update(
    session: Session, repository: Customer360Repository
) -> None:
    seed_demo_customers(session)
    first_created_at = repository.get_by_customer_id(
        DEMO_CUSTOMERS[0]["customer_id"]
    ).created_at

    seed_demo_customers(session)
    second_created_at = repository.get_by_customer_id(
        DEMO_CUSTOMERS[0]["customer_id"]
    ).created_at

    assert first_created_at == second_created_at


def test_seeding_enabled_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_DEMO_SEED", raising=False)

    assert seeding_enabled() is False


def test_seeding_enabled_true_when_env_var_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")

    assert seeding_enabled() is True


def test_seeding_enabled_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_DEMO_SEED", "TRUE")

    assert seeding_enabled() is True


def test_seeding_enabled_false_for_other_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_DEMO_SEED", "1")

    assert seeding_enabled() is False


def test_seeding_enabled_force_flag_bypasses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_DEMO_SEED", raising=False)

    assert seeding_enabled(force=True) is True


def test_main_refuses_to_run_when_not_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_DEMO_SEED", raising=False)

    exit_code = main([])

    assert exit_code == 1
