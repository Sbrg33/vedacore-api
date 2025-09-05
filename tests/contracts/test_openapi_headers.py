from __future__ import annotations

def test_sse_headers_doc_present(openapi_spec):
    spec = openapi_spec
    get_op = spec["paths"]["/api/v1/stream"]["get"]
    h = get_op["responses"]["200"].get("headers", {})
    assert "Cache-Control" in h, "Missing Cache-Control header docs on SSE 200 response"
    assert "Referrer-Policy" in h, "Missing Referrer-Policy header docs on SSE 200 response"
    assert "Vary" in h, "Missing Vary header docs on SSE 200 response"
