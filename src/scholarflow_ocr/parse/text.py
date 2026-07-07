import re

_WS = re.compile(r"\s+")


def normalize(s: str) -> str:
    return _WS.sub(" ", (s or "").strip())


def split_name(name: str) -> tuple[str, str]:
    """Split a display name into (forename, surname). Last token is the surname."""
    parts = normalize(name).split(" ")
    if not parts or parts == [""]:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    return (" ".join(parts[:-1]), parts[-1])
