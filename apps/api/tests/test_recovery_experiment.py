from datetime import date, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.models.domain import (
    Customer,
    Invoice,
    InvoiceStatus,
    PromiseStatus,
    PromiseToPay,
    RecoveryCase,
    RecoveryPriority,
    RecoveryState,
)
from app.reporting.recovery_experiment import build_recovery_experiment


OPERATING_DATE = date(2026, 8, 26)


def _id(label: str):
    return uuid5(NAMESPACE_URL, f"reconmate.experiment.test/{label}")


def _case(
    label: str,
    amount: str,
    *,
    status: InvoiceStatus = InvoiceStatus.OVERDUE,
    priority: RecoveryPriority = RecoveryPriority.NORMAL,
    strategic: bool = False,
    promise: bool = False,
) -> RecoveryCase:
    customer = Customer(
        id=_id(f"customer/{label}"), name=f"{label} Company",
        account_reference=f"EXP-{label}", is_strategic_account=strategic,
    )
    invoice = Invoice(
        id=_id(f"invoice/{label}"), customer=customer, invoice_number=f"INV-{label}",
        issue_date=OPERATING_DATE - timedelta(days=75), due_date=OPERATING_DATE - timedelta(days=45),
        original_amount=Decimal(amount), outstanding_amount=Decimal(amount), status=status,
    )
    if promise:
        PromiseToPay(
            id=_id(f"promise/{label}"), customer=customer, invoice=invoice,
            promised_amount=Decimal(amount) / 2,
            promised_date=OPERATING_DATE + timedelta(days=60), status=PromiseStatus.ACTIVE,
        )
    return RecoveryCase(
        id=_id(f"case/{label}"), customer=customer, invoice=invoice,
        current_state=RecoveryState.AWAITING_CUSTOMER if status is InvoiceStatus.DISPUTED else RecoveryState.IN_PROGRESS,
        priority=priority,
    )


def _portfolio() -> list[RecoveryCase]:
    return [
        _case("NORMAL", "1000"),
        _case("PROMISE", "600", priority=RecoveryPriority.HIGH, strategic=True, promise=True),
        _case("DISPUTE", "400", status=InvoiceStatus.DISPUTED, priority=RecoveryPriority.CRITICAL),
    ]


def test_seeded_experiment_is_reproducible_and_rerunnable() -> None:
    cases = _portfolio()
    first = build_recovery_experiment(simulation_date=OPERATING_DATE, cases=cases, seed=451)
    second = build_recovery_experiment(simulation_date=OPERATING_DATE, cases=cases, seed=451)
    assert first == second


def test_paired_cohorts_are_isolated_and_start_from_exact_financial_twins() -> None:
    cases = _portfolio()
    before = [
        (case.invoice.outstanding_amount, case.invoice.status, [promise.status for promise in case.invoice.promises_to_pay], len(case.actions))
        for case in cases
    ]
    result = build_recovery_experiment(simulation_date=OPERATING_DATE, cases=cases, seed=451)
    after = [
        (case.invoice.outstanding_amount, case.invoice.status, [promise.status for promise in case.invoice.promises_to_pay], len(case.actions))
        for case in cases
    ]
    cohort = result["cohort_construction"]
    assert before == after
    assert cohort["pair_count"] == cohort["baseline_account_count"] == cohort["reconmate_account_count"] == 3
    assert cohort["exact_starting_exposure_match"] is True
    assert cohort["baseline_starting_exposure"] == cohort["reconmate_starting_exposure"] == "2000.00"


def test_experiment_arithmetic_and_difference_are_exact() -> None:
    result = build_recovery_experiment(simulation_date=OPERATING_DATE, cases=_portfolio(), seed=451)
    for arm_name in ("baseline", "reconmate"):
        arm = result[arm_name]
        assert Decimal(arm["starting_overdue_exposure"]) == Decimal(arm["recovered_amount"]) + Decimal(arm["remaining_overdue"])
        assert arm["equation_holds"] is True
        expected_rate = (Decimal(arm["recovered_amount"]) / Decimal(arm["starting_overdue_exposure"]) * 100).quantize(Decimal("0.01"))
        assert Decimal(arm["recovery_rate"]) == expected_rate
    assert Decimal(result["difference"]["recovered_amount"]) == Decimal(result["reconmate"]["recovered_amount"]) - Decimal(result["baseline"]["recovered_amount"])
    assert Decimal(result["difference"]["remaining_overdue"]) == Decimal(result["reconmate"]["remaining_overdue"]) - Decimal(result["baseline"]["remaining_overdue"])


def test_overlapping_exception_categories_are_not_double_counted_as_accounts() -> None:
    result = build_recovery_experiment(simulation_date=OPERATING_DATE, cases=_portfolio(), seed=451)
    cohort = result["cohort_construction"]
    promise_row = next(row for row in result["evidence"] if row["invoice_number"] == "INV-PROMISE")
    assert set(promise_row["exception_categories"]) >= {"ACTIVE_PAYMENT_PROMISE", "STRATEGIC_ACCOUNT", "ELEVATED_PRIORITY"}
    assert cohort["exception_categories_overlap"] is True
    assert cohort["exception_memberships"] > cohort["unique_accounts_with_exceptions"]


def test_blocked_or_nonintervened_cases_receive_no_intervention_attribution() -> None:
    result = build_recovery_experiment(simulation_date=OPERATING_DATE, cases=_portfolio(), seed=451)
    promise_row = next(row for row in result["evidence"] if row["invoice_number"] == "INV-PROMISE")
    assert promise_row["reconmate"]["intentionally_deferred"] is True
    assert promise_row["reconmate"]["actions"] == []
    assert all(payment["association"] != "INTERVENTION_ASSOCIATED" for payment in promise_row["reconmate"]["payments"])
    assert result["reconmate"]["dispute_contact_violations"] == 0
    assert result["reconmate"]["active_promise_contact_violations"] == 0
    for row in result["evidence"]:
        completed = {action["action_reference"]: action for action in row["reconmate"]["actions"] if action["completed"]}
        for payment in row["reconmate"]["payments"]:
            if payment["association"] != "INTERVENTION_ASSOCIATED":
                continue
            action = completed[payment["action_reference"]]
            assert action["simulated_response_increment"] != "0"
            assert action["day"] <= payment["day"] < action["day"] + result["methodology"]["attribution_window_days"]
