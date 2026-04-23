"""
Persistent, filesystem-backed store for saved GitHub tokens.
Tokens are kept in ~/.pdmanager/github_tokens.json (chmod 600).
Raw values are NEVER returned via the API — only hints (last 4 chars).
"""
import json
import os
import uuid
from typing import Optional

_TOKENS_FILE = os.path.expanduser("~/.pdmanager/github_tokens.json")


def load() -> list[dict]:
    try:
        with open(_TOKENS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save(tokens: list[dict]) -> None:
    os.makedirs(os.path.dirname(_TOKENS_FILE), exist_ok=True)
    with open(_TOKENS_FILE, "w") as f:
        json.dump(tokens, f)
    os.chmod(_TOKENS_FILE, 0o600)


def resolve(token_id: str) -> Optional[str]:
    """Return the raw token for a given ID, or None if not found."""
    for t in load():
        if t["id"] == token_id:
            return t["token"]
    return None


def add(label: str, token: str) -> None:
    tokens = load()
    existing = next((t for t in tokens if t["label"] == label), None)
    if existing:
        existing["token"] = token
    else:
        tokens.append({"id": str(uuid.uuid4()), "label": label, "token": token})
    save(tokens)


def remove(token_id: str) -> None:
    save([t for t in load() if t["id"] != token_id])


def list_hints() -> list[dict]:
    """Return token list with only id, label, and last-4-char hint. Never raw values."""
    return [{"id": t["id"], "label": t["label"], "token_hint": t["token"][-4:]} for t in load()]
