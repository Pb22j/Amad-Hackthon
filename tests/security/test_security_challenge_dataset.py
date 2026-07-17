from __future__ import annotations

from collections import Counter
from pathlib import Path
from unicodedata import normalize

import pytest

from agentic.evals.runner import load_security_dataset


CHALLENGE = Path("agentic/evals/datasets/security_challenge.jsonl")
EARLIER_DATASETS = (
    Path("agentic/evals/datasets/security.jsonl"),
    Path("agentic/evals/datasets/security_holdout.jsonl"),
)

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

EXPECTED_BY_CATEGORY = {
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
def test_challenge_has_exact_balanced_coverage() -> None:
    cases = load_security_dataset(CHALLENGE)

    assert len(cases) == 100
    assert Counter(case.category for case in cases) == Counter({name: 10 for name in CATEGORIES})
    assert Counter(case.language for case in cases) == Counter({"en": 50, "ar": 50})
    assert Counter((case.category, case.language) for case in cases) == Counter(
        {(category, language): 5 for category in CATEGORIES for language in ("en", "ar")}
    )
    assert len({case.id for case in cases}) == 100
    assert all(case.id.startswith("challenge-") for case in cases)


@pytest.mark.security
def test_challenge_uses_strict_intended_outcomes() -> None:
    cases = load_security_dataset(CHALLENGE)

    assert all(case.known_gap is None and case.mitigation is None for case in cases)
    for case in cases:
        if case.category in EXPECTED_BY_CATEGORY:
            assert case.expected == EXPECTED_BY_CATEGORY[case.category], case.id

    authority = [case for case in cases if case.category == "authority_manipulation"]
    assert Counter(case.expected for case in authority) == Counter({"reject": 6, "signal": 4})
    assert Counter(case.expected for case in cases) == Counter(
        {"allow": 30, "signal": 24, "reject": 46}
    )


@pytest.mark.security
def test_challenge_has_no_normalized_overlap_with_earlier_datasets() -> None:
    cases = load_security_dataset(CHALLENGE)
    earlier = [case for path in EARLIER_DATASETS for case in load_security_dataset(path)]

    challenge_inputs = [_canonical(case.input) for case in cases]
    earlier_inputs = {_canonical(case.input) for case in earlier}
    assert len(set(challenge_inputs)) == 100
    assert earlier_inputs.isdisjoint(challenge_inputs)
    assert {case.id for case in earlier}.isdisjoint(case.id for case in cases)
