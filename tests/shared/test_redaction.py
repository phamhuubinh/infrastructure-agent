from src.shared.redaction import redact_sensitive


def test_shared_redaction_covers_common_provider_credentials() -> None:
    text = (
        "password=hunter2 "
        "api_key=sk-abcdefghijklmnopqrstuvwxyz "
        "Authorization: Bearer secret-token "
        "https://user:secret@example.com/"
    )

    redacted = redact_sensitive(text)

    assert "hunter2" not in redacted
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "secret-token" not in redacted
    assert "user:secret@" not in redacted


def test_shared_redaction_removes_private_key_block() -> None:
    text = """failure:
-----BEGIN PRIVATE KEY-----
super-secret-material
-----END PRIVATE KEY-----
"""

    redacted = redact_sensitive(text)

    assert "super-secret-material" not in redacted
    assert "<redacted>" in redacted
