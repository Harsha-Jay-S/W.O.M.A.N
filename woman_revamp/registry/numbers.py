"""Regex patterns for number-like signals in user prompts."""

NUMBER_PATTERNS: dict[str, str] = {
    "port": r"\b(?:port\s+)?(?P<port>\d{2,5})\b",
    "pid": r"\b(?:pid|process)\s+(?P<pid>\d+)\b",
    "lines": r"\b(?P<lines>\d+)\s+lines?\b",
    "days": r"\b(?P<days>\d+)\s+days?\b",
    "hours": r"\b(?P<hours>\d+)\s+hours?\b",
    "size": r"\b(?P<size>\d+(?:\.\d+)?\s*[kmgt]?b?)\b",
    "count": r"\b(?P<count>\d+)\b",
}
