from __future__ import annotations

import re

_CHARACTER_ID_RE = re.compile(r"☘(?:️)?\s*(\d+)")


def parse_character_ids(text: str) -> list[int]:
    """Extract ordered unique IDs that follow the clover marker."""
    seen: set[int] = set()
    result: list[int] = []
    for match in _CHARACTER_ID_RE.finditer(text or ""):
        value = int(match.group(1))
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
