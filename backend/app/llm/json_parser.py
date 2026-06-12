from __future__ import annotations

import ast
import json
import re
from typing import Any

from .exceptions import StructuredOutputError


_FENCED_JSON = re.compile(
    r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL
)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for start, opening in enumerate(text):
        if opening not in "[{":
            continue
        closing = "}" if opening == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
    return candidates


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


def parse_json_tolerantly(text: str) -> Any:
    stripped = text.strip()
    candidates = [stripped]
    candidates.extend(match.group(1).strip() for match in _FENCED_JSON.finditer(text))
    candidates.extend(_balanced_json_candidates(text))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        repaired = _TRAILING_COMMA.sub(r"\1", candidate)
        for value in (candidate, repaired):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        try:
            literal = ast.literal_eval(repaired)
        except (SyntaxError, ValueError):
            continue
        if _is_json_value(literal):
            return literal

    raise StructuredOutputError("The model response did not contain valid JSON")

