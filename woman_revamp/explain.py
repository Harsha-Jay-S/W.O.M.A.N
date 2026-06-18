"""Command explanation engine for woman."""

from __future__ import annotations

from .engine import (
    build_vocabulary,
    correct_typos,
    expand_synonyms,
    extract_intent,
    extract_numbers,
    normalize_query,
    rank_candidates,
    tokenize,
)
from .registry import get_registry, normalize_os_name


def explain_command(
    query: str, context: str = "", os_info: str | None = None
) -> str:
    """Return a structured explanation of the best matching command."""
    candidates = rank_candidates(
        query, context=context, os_info=os_info, limit=3
    )
    if not candidates:
        return "No matching command found."

    best = candidates[0]

    normalized_os = normalize_os_name(
        str(os_info) if os_info is not None else None
    )
    registry = get_registry(normalized_os)
    query_text = normalize_query(query)
    tokens = tokenize(query_text)
    vocabulary = build_vocabulary(registry)
    tokens = correct_typos(tokens, vocabulary)
    tokens = expand_synonyms(tokens)
    intents = extract_intent(query_text)
    signals = extract_numbers(query_text)

    lines: list[str] = []
    lines.append(f"Command:  {best['rendered']}")
    lines.append("─" * 50)
    lines.append(
        f"Source:   Heuristic engine (confidence: {best['score']:.2f})"
    )
    if intents:
        lines.append(f"Intent:   {', '.join(intents)}")
    if signals:
        lines.append("Signals:")
        for k, v in signals.items():
            lines.append(f"  {k} = {v}")
    lines.append("")

    cmd = str(best["rendered"])
    parts = cmd.split()
    for i, part in enumerate(parts):
        if part.startswith("-") and len(part) > 1:
            idx = i + 1
            lines.append(f"  {part}")
            if part in ("-name", "-iname"):
                if idx < len(parts):
                    lines[-1] += f" {parts[idx]}  ← Filter by name pattern"
            elif part in ("-type",):
                if idx < len(parts):
                    kind = parts[idx]
                    label = "directories" if kind == "d" else "files"
                    lines[-1] += f"  ← Only {label}"
            elif part in ("-mtime", "-atime", "-ctime"):
                if idx < len(parts):
                    lines[-1] += f" {parts[idx]}  ← Modified time filter"
            elif part in ("-r", "-R", "--recursive"):
                lines[-1] += "  ← Recurse into subdirectories"
            elif part in ("-f", "--force"):
                lines[-1] += "  ← Force operation"
            elif part in ("-rf",):
                lines[-1] += "  ← Recursive force (dangerous)"
            else:
                lines[-1] += "  ← Flag option"

    if len(candidates) > 1:
        lines.append("")
        lines.append("Alternatives:")
        for item in candidates[1:]:
            lines.append(
                f"  [{item['score']:.2f}] {item['rendered']}"
            )

    lines.append("")
    lines.append(
        "Run `woman manual <command>` for the full man page."
    )

    return "\n".join(lines)
