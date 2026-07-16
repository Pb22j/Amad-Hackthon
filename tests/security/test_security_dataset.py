from pathlib import Path

import pytest

from agentic.evals.runner import load_security_dataset, run_security_dataset
from agentic.policy.engine import PolicyEngine


@pytest.mark.security
def test_complete_security_dataset_passes(app_config):
    path = Path("agentic/evals/datasets/security.jsonl")
    report = run_security_dataset(path, PolicyEngine(app_config.policies))
    assert report.total >= 9
    assert report.pass_rate == 1
    assert report.failures == []


def test_invalid_dataset_reports_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"invalid":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_security_dataset(path)

