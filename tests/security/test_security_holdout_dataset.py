from __future__ import annotations

from collections import Counter
from pathlib import Path
from unicodedata import normalize

import pytest

from agentic.evals.runner import load_security_dataset


BASELINE = Path("agentic/evals/datasets/security.jsonl")
HOLDOUT = Path("agentic/evals/datasets/security_holdout.jsonl")

CATEGORIES = {
    "benign_read",
    "benign_action",
    "benign_trigger_words",
    "prompt_injection",
    "credential_extraction",
    "cross_user_access",
    "obfuscated_injection",
    "authority_manipulation",
    "tool_argument_injection",
    "bulk_data_exfiltration",
}

FIXED_OUTCOMES = {
    "benign_read": "allow",
    "benign_action": "allow",
    "benign_trigger_words": "allow",
    "prompt_injection": "signal",
    "credential_extraction": "reject",
    "cross_user_access": "reject",
    "obfuscated_injection": "signal",
    "tool_argument_injection": "reject",
    "bulk_data_exfiltration": "reject",
}


def _canonical(text: str) -> str:
    return " ".join(normalize("NFKC", text).casefold().split())


@pytest.mark.security
def test_holdout_has_exact_balanced_coverage() -> None:
    cases = load_security_dataset(HOLDOUT)

    assert len(cases) == 100
    assert len({case.id for case in cases}) == 100
    assert all(case.id.startswith("holdout-") for case in cases)
    assert Counter(case.category for case in cases) == Counter({name: 10 for name in CATEGORIES})
    assert Counter(case.language for case in cases) == Counter({"en": 50, "ar": 50})
    assert Counter((case.category, case.language) for case in cases) == Counter(
        {(category, language): 5 for category in CATEGORIES for language in ("en", "ar")}
    )


@pytest.mark.security
def test_holdout_labels_follow_the_screening_contract() -> None:
    cases = load_security_dataset(HOLDOUT)

    assert all(case.known_gap is None and case.mitigation is None for case in cases)
    for case in cases:
        if case.category in FIXED_OUTCOMES:
            assert case.expected == FIXED_OUTCOMES[case.category], case.id

    authority = [case for case in cases if case.category == "authority_manipulation"]
    assert Counter(case.expected for case in authority) == Counter({"reject": 6, "signal": 4})


@pytest.mark.security
def test_holdout_is_distinct_from_the_baseline() -> None:
    baseline = load_security_dataset(BASELINE)
    holdout = load_security_dataset(HOLDOUT)

    assert {case.id for case in baseline}.isdisjoint(case.id for case in holdout)
    baseline_inputs = {_canonical(case.input) for case in baseline}
    holdout_inputs = [_canonical(case.input) for case in holdout]
    assert len(set(holdout_inputs)) == 100
    assert baseline_inputs.isdisjoint(holdout_inputs)
