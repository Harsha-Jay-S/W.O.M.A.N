"""Post-render finalize layer: scope correctness + safety, in one place.

Every generated command should pass through ``finalize_command`` before it is
shown or run.  This is the single chokepoint where we:

1. make absolute paths under the cwd portable (relative),
2. correct archive *scope* (``all folders`` → one archive per top-level folder,
   not one archive of everything including loose + hidden files),
3. detect output-file collisions (don't silently overwrite),
4. compute a risk level from the *actual* command.

Keeping these here (rather than scattered per registry entry) means new edge
cases extend a dispatch table and gain a regression test, instead of becoming
another bespoke patch.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .ml.safety import calculate_danger_score

# --- scope detection -------------------------------------------------------

# Distributive reading ("one per folder") only triggers on the *plural*.
_PLURAL_FOLDER_RE = re.compile(r"\bfolders\b|\bdirectories\b", re.IGNORECASE)
# Words that flip the default per-folder reading into one combined archive.
_MERGE_WORDS = (
    "into one",
    "into a single",
    "single archive",
    "one archive",
    "combined",
    "combine",
)

# Archive op detected from the rendered command verb (not the intent — "zip"
# isn't a synonym in the registry, so the intent list is often empty).
_ZIP_RE = re.compile(r"^\s*zip\b")
_TAR_CREATE_RE = re.compile(r"^\s*tar\s+-?[a-z]*c")


@dataclass
class FinalizedCommand:
    command: str
    restatement: str = ""
    risk_level: str = "Low"
    risk_score: float = 0.0
    risk_reasons: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    overwrite: bool = False


def _quote_if_needed(token: str) -> str:
    if token and (" " in token) and not (token.startswith(('"', "'"))):
        return f'"{token}"'
    return token


def _make_relative(command: str, cwd: str) -> str:
    """Replace tokens equal to / under the absolute ``cwd`` with ``.``.

    Generic — fixes the absolute-path leak for any command, not just archives.
    """
    try:
        abs_cwd = os.path.abspath(cwd)
    except (OSError, ValueError):
        return command
    if abs_cwd in ("/", "") or len(abs_cwd) < 2:
        return command  # never rewrite the root path

    out: list[str] = []
    for tok in command.split(" "):
        stripped = tok.strip("'\"")
        if stripped == abs_cwd:
            out.append(".")
        elif stripped.startswith(abs_cwd + "/"):
            out.append(_quote_if_needed("./" + stripped[len(abs_cwd) + 1:]))
        else:
            out.append(tok)
    return " ".join(out)


def _detect_archive_op(command: str) -> tuple[str, str, str] | None:
    """Return ``(verb, ext, name)`` for an archive-creating command, else None.

    ``verb`` is the command prefix to reuse, ``ext`` the output suffix, ``name``
    the archive base name found in the command (default ``archive``).
    """
    if _ZIP_RE.match(command):
        return ("zip -r", ".zip", _archive_base(command, ".zip"))
    if _TAR_CREATE_RE.match(command):
        ext = ".tgz" if ".tgz" in command else ".tar.gz"
        return ("tar -czf", ext, _archive_base(command, ext))
    return None


def _archive_base(command: str, ext: str) -> str:
    for tok in command.split():
        tok = tok.strip("'\"")
        if tok.endswith(ext):
            return Path(tok[: -len(ext)]).name or "archive"
    return "archive"


def _toplevel_dirs(cwd: str) -> list[str]:
    """Top-level, non-hidden directory names in ``cwd`` (mirrors ``*/``)."""
    try:
        return sorted(
            p.name
            for p in Path(cwd).iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
    except OSError:
        return []


def _per_folder_loop(verb: str, ext: str) -> str:
    # POSIX-portable: woman executes via `sh -c`, which may be dash (no `shopt`).
    # The `[ -d "$d" ]` guard handles the no-match case (where `*/` stays literal)
    # without relying on bash's nullglob.
    return (
        "for d in */; do\n"
        '  [ -d "$d" ] || continue\n'
        f'  {verb} "${{d%/}}{ext}" "$d"\n'
        "done"
    )


def _risk_level(score: float) -> str:
    if score >= 0.85:
        return "High"
    if score >= 0.40:
        return "Moderate"
    return "Low"


def finalize_command(
    query: str,
    command: str,
    intents: list[str] | None = None,
    cwd: str = ".",
) -> FinalizedCommand:
    """Finalize a rendered command: portability, scope, collisions, risk."""
    _ = intents  # archive op is read from the command verb; kept for API/extension
    q = query.lower()
    cmd = _make_relative(command, cwd)
    restatement = ""
    collisions: list[str] = []

    op = _detect_archive_op(cmd)
    if op and _PLURAL_FOLDER_RE.search(q):
        verb, ext, base = op
        if any(w in q for w in _MERGE_WORDS):
            cmd = f"{verb} {base}{ext} */"
            restatement = (
                'Interpreting "all folders" as: combine all top-level folders into '
                "ONE combined archive (loose files excluded) — edit if you meant one "
                "archive per folder"
            )
            predicted = [f"{base}{ext}"]
        else:
            cmd = _per_folder_loop(verb, ext)
            restatement = (
                'Interpreting "all folders" as: archive each top-level folder into '
                "its own archive (excluding hidden folders) — edit if you meant one "
                "combined archive"
            )
            predicted = [f"{d}{ext}" for d in _toplevel_dirs(cwd)]
        collisions = [n for n in predicted if (Path(cwd) / n).exists()]
    else:
        snippet = cmd.splitlines()[0][:60]
        restatement = f"Interpreting as: run `{snippet}` in the current directory"

    score, reasons = calculate_danger_score(cmd)
    reasons = list(reasons)
    overwrite = bool(collisions)
    if overwrite:
        reasons.append(f"Overwrites existing: {', '.join(collisions)}")
        score = max(score, 0.50)

    return FinalizedCommand(
        command=cmd,
        restatement=restatement,
        risk_level=_risk_level(score),
        risk_score=score,
        risk_reasons=reasons,
        collisions=collisions,
        overwrite=overwrite,
    )
