import json
import logging

from agentic.telemetry.logging import RedactingJsonFormatter


def test_structured_logging_redacts_secrets_and_cards():
    record = logging.LogRecord(
        name="agentic.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Bearer secret-token card 4111 1111 1111 1111",
        args=(),
        exc_info=None,
    )
    record.task_id = "task-1"
    payload = json.loads(RedactingJsonFormatter().format(record))
    assert payload["task_id"] == "task-1"
    assert "4111" not in payload["message"]
    assert "secret-token" not in payload["message"]


def test_structured_logging_records_redacted_exception_details():
    try:
        raise RuntimeError("Bearer secret-token provider rejected request")
    except RuntimeError as exc:
        record = logging.LogRecord(
            name="agentic.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="agent task execution failed",
            args=(),
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    payload = json.loads(RedactingJsonFormatter().format(record))
    assert payload["exception_type"] == "RuntimeError"
    assert "secret-token" not in payload["exception_message"]
