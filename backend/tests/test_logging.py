"""Secret redaction for the logging pipeline (the project contract)."""

from app.core.logging import redact


def test_redacts_unquoted_pairs() -> None:
    assert redact("api_key=sk-abc123") == "api_key=***REDACTED***"
    assert redact("password: hunter2") == "password: ***REDACTED***"


def test_redacts_quoted_values() -> None:
    assert redact('api_key="sk-abc123"') == 'api_key="***REDACTED***"'
    assert redact("secret:'s3cr3t'") == "secret:'***REDACTED***'"


def test_redacts_quoted_keys_json_and_repr() -> None:
    assert redact('"password": "hunter2"') == '"password": "***REDACTED***"'
    assert redact("{'token': 'abc.def'}") == "{'token': '***REDACTED***'}"


def test_redacts_bearer_tokens_case_insensitive() -> None:
    assert redact("Authorization: Bearer abc.def.ghi") == "Authorization: Bearer ***REDACTED***"
    assert redact("bearer XYZ") == "bearer ***REDACTED***"


def test_leaves_benign_text_untouched() -> None:
    assert redact("analysis abc123 scored 72 in 41ms") == "analysis abc123 scored 72 in 41ms"
    assert redact("") == ""
