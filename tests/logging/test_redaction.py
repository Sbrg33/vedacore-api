from __future__ import annotations

from app.core.logging import JsonFormatter


def test_redaction_strips_token_and_authorization_and_query() -> None:
    fmt = JsonFormatter()
    # Build a fake message that includes a URL with token and an Authorization header
    msg = (
        "GET /api/v1/stream?topic=x&token=abc.def.ghi HTTP/1.1\n"
        "Authorization: Bearer header.token.value\n"
        "Referer: https://app.example.com/page?token=leaky\n"
    )
    redacted = fmt._redact(msg)  # type: ignore[attr-defined]
    assert "token=abc" not in redacted
    assert "Authorization: Bearer header.token.value" not in redacted
    assert "/api/v1/stream?" not in redacted
    assert "/api/v1/stream" in redacted
    assert "Referer: [REDACTED]" in redacted
