"""Small, centralized configuration for constrained simulation randomness."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioConfig:
    primary_event_population: tuple[str, ...] = ("PARTIAL_PAYMENT", "PARTIAL_PAYMENT", "FULL_PAYMENT", "PROMISE_CREATED", "PROMISE_BROKEN", "DISPUTE_OPENED", "DISPUTE_RESOLVED", "CUSTOMER_DELAY_RESPONSE")
    secondary_count_population: tuple[int, ...] = (0, 1, 1, 1, 2, 2, 2, 3, 3, 4)
    payment_fraction_min: float = 0.08
    payment_fraction_max: float = 0.65
    promise_fraction_min: float = 0.20
    promise_fraction_max: float = 0.75
    promise_days_min: int = 3
    promise_days_max: int = 14
    same_account_probability: float = 0.45
    judge_seed: int = 101


SCENARIO_CONFIG = ScenarioConfig()
