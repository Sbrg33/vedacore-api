#!/usr/bin/env python3
"""
Downgrade an OpenAPI 3.1 spec to 3.0.3 for tooling compatibility:
 - Set openapi to 3.0.3
 - Convert anyOf [<type>, null] to {type: <type>, nullable: true}
 - Ensure text/event-stream content has a basic schema (type: string)

Usage:
  python tools/openapi_downgrade_31_to_30.py [path]
  (defaults to ./openapi.json in repo root)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def convert_anyof_nullable(node: object) -> object:
    if isinstance(node, dict):
        # Convert anyOf with null
        if "anyOf" in node and isinstance(node["anyOf"], list):
            types = []
            for entry in node["anyOf"]:
                if isinstance(entry, dict) and "type" in entry:
                    types.append(entry["type"])
            if len(types) == 2 and "null" in types:
                non_null = [t for t in types if t != "null"][0]
                # Preserve description/title/default if present
                new_node = {k: v for k, v in node.items() if k not in ("anyOf", "oneOf", "allOf")}
                new_node["type"] = non_null
                new_node["nullable"] = True
                node = new_node
        # Recurse
        # Drop 3.1-specific or problematic keys
        for bad in ("const", "prefixItems", "$schema", "propertyNames"):
            if bad in node:
                node.pop(bad, None)
        # Recurse
        for k, v in list(node.items()):
            node[k] = convert_anyof_nullable(v)
    elif isinstance(node, list):
        return [convert_anyof_nullable(x) for x in node]
    return node


def ensure_event_stream_schema(spec: dict) -> None:
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for m, op in methods.items():
            if not isinstance(op, dict):
                continue
            responses = op.get("responses", {})
            r200 = responses.get("200", {})
            content = r200.get("content", {})
            if "text/event-stream" in content:
                ces = content["text/event-stream"]
                if not isinstance(ces, dict):
                    content["text/event-stream"] = {"schema": {"type": "string"}}
                else:
                    ces.setdefault("schema", {"type": "string"})


def ensure_array_items(node: object) -> object:
    """Ensure all array schemas specify items to satisfy generators."""
    if isinstance(node, dict):
        if node.get("type") == "array" and "items" not in node:
            node["items"] = {"type": "object"}
        for k, v in list(node.items()):
            node[k] = ensure_array_items(v)
    elif isinstance(node, list):
        return [ensure_array_items(x) for x in node]
    return node


def main():
    root = Path(__file__).resolve().parents[1]
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "openapi.json"
    spec = json.loads(path.read_text())
    spec["openapi"] = "3.0.3"
    spec = convert_anyof_nullable(spec)
    spec = ensure_array_items(spec)
    ensure_event_stream_schema(spec)
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Downgraded spec written to {path} (openapi={spec['openapi']})")


if __name__ == "__main__":
    main()
