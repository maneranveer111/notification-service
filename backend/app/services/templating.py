import re
from typing import Any

VARIABLE_REGEX = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class MissingVariables(Exception):
    def __init__(self, names: list[str]):
        self.names = names
        super().__init__(f"Missing variables: {', '.join(names)}")


def extract_variables(text: str | None) -> list[str]:
    if not text:
        return []
    matches = VARIABLE_REGEX.findall(text)
    # Return unique variable names preserving order of appearance
    return list(dict.fromkeys(matches))


def render(text: str | None, variables: dict[str, Any] | None, is_subject: bool = False) -> str:
    if not text:
        return ""

    variables = variables or {}
    needed = extract_variables(text)
    missing = [name for name in needed if name not in variables]
    if missing:
        raise MissingVariables(missing)

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        val = str(variables[var_name])[:2000]
        if is_subject:
            val = val.replace("\r", "").replace("\n", "")
        return val

    return VARIABLE_REGEX.sub(_replace, text)

