from agentic.evals.mutation_gate import mutation_score


def test_mutation_score_counts_survivors():
    results = """
    package.x_mutant_1: killed
    package.x_mutant_2: survived
    package.x_mutant_3: killed
    """
    assert mutation_score(results) == (2, 3, 2 / 3)


def test_mutation_gate_main_passes_and_fails(monkeypatch, capsys):
    import sys

    from agentic.evals import mutation_gate

    monkeypatch.setattr(mutation_gate.shutil, "which", lambda _: "/bin/mutmut")
    monkeypatch.setattr(
        mutation_gate.subprocess,
        "check_output",
        lambda *args, **kwargs: "a: killed\nb: killed\nc: survived\n",
    )
    monkeypatch.setattr(sys, "argv", ["mutation-gate", "--minimum", "0.60"])
    mutation_gate.main()
    assert "66.67%" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["mutation-gate", "--minimum", "0.90"])
    try:
        mutation_gate.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover
        raise AssertionError("mutation gate should fail below the threshold")
