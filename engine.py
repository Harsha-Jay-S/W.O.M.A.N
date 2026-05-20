"""Scoring and template resolution for the local woman registry."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
import os
import re
import shutil
import shlex
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .registry import get_registry, normalize_os_name
from .registry.extension_hints import EXTENSION_HINTS
from .registry.intent_phrases import INTENT_PHRASES
from .registry.numbers import NUMBER_PATTERNS
from .registry.synonyms import SYNONYMS

MIN_CONFIDENCE = 12
STOP_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "for",
    "from",
    "get",
    "i",
    "in",
    "into",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "the",
    "to",
    "up",
    "what",
    "whats",
    "with",
    "you",
    "your",
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*", re.IGNORECASE)
PATH_RE = re.compile(r"(?:[a-zA-Z]:\\[^\s]+|/[^\s]+|\./[^\s]+|\../[^\s]+|[^\s]+\.[a-zA-Z0-9]{1,8})")
URL_RE = re.compile(r"https?://[^\s'\"]+")
QUOTED_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"")
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
REQUIRED_PLACEHOLDERS = {
    "days": "days",
    "port": "port",
    "pid": "pid",
    "service": "service",
    "package": "package",
    "process": "process",
    "file": "file",
    "path": "path",
    "kind": "kind",
}


@dataclass(frozen=True)
class RankedCommand:
    name: str
    score: int
    template_key: str
    rendered: str | None
    intent: str | None = None


def _flatten(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            parts.append(f"{key}: {item}")
        return "\n".join(parts)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return "\n".join(str(item) for item in value)
    return str(value)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip().lower()


def tokenize(text: str) -> list[str]:
    """Tokenize text into a stable, low-noise set of lowercase tokens."""

    tokens: list[str] = []
    for match in TOKEN_RE.findall(text.lower()):
        pieces = [piece for piece in re.split(r"[._/-]+", match) if piece]
        tokens.append(match)
        tokens.extend(pieces)
    filtered: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if len(token) < 2 or token in STOP_WORDS:
            continue
        if token not in seen:
            filtered.append(token)
            seen.add(token)
    return filtered


def _synonym_lookup() -> dict[str, str]:
    reverse: dict[str, str] = {}
    for canonical, phrases in SYNONYMS.items():
        reverse[canonical] = canonical
        for phrase in phrases:
            reverse[phrase.lower()] = canonical
    return reverse


def _intent_tokens() -> set[str]:
    values: set[str] = set()
    for intent, phrases in INTENT_PHRASES:
        values.add(intent)
        for phrase in phrases:
            values.update(tokenize(phrase))
    return values


def _hashable_registry(registry: Mapping[str, Mapping]) -> tuple:
    """Convert registry to a hashable form for caching."""
    return tuple(
        (name, tuple(spec.get("keywords", [])), tuple(spec.get("templates", {}).items()), tuple(spec.get("intent_map", {}).items()))
        for name, spec in sorted(registry.items())
    )


@lru_cache(maxsize=1)
def _cached_vocabulary(registry_hash: tuple) -> list[str]:
    vocabulary: set[str] = set()
    vocabulary.update(_intent_tokens())
    for canonical, phrases in SYNONYMS.items():
        vocabulary.add(canonical)
        for phrase in phrases:
            vocabulary.update(tokenize(phrase))
    for _name, keywords, templates, intent_map in registry_hash:
        kw_text = " ".join(keywords)
        tmpl_text = " ".join(k for k, _v in templates)
        intent_text = " ".join(k for k, _v in intent_map)
        vocabulary.update(tokenize(kw_text))
        vocabulary.update(tokenize(tmpl_text))
        vocabulary.update(tokenize(intent_text))
    for ext, hints in EXTENSION_HINTS.items():
        vocabulary.add(ext.lstrip("."))
        vocabulary.update(hints)
    for key in NUMBER_PATTERNS:
        vocabulary.add(key)
    return sorted(vocabulary)


def build_vocabulary(registry: Mapping[str, Mapping]) -> list[str]:
    return _cached_vocabulary(_hashable_registry(registry))


def correct_typos(tokens: list[str], vocabulary: Sequence[str]) -> list[str]:
    """Correct obvious typos with stdlib fuzzy matching."""

    corrected: list[str] = []
    vocabulary_set = set(vocabulary)
    for token in tokens:
        if token in vocabulary_set:
            corrected.append(token)
            continue
        matches = get_close_matches(token, vocabulary, n=1, cutoff=0.84)
        corrected.append(matches[0] if matches else token)
    return corrected


def extract_intent(query: str) -> list[str]:
    """Return canonical intents discovered from phrase matching."""

    q = normalize_query(query)
    hits: list[tuple[int, str]] = []
    for intent, phrases in INTENT_PHRASES:
        for phrase in sorted(phrases, key=len, reverse=True):
            position = q.find(phrase)
            if position != -1:
                hits.append((position, intent))
                break
    hits.sort(key=lambda item: item[0])
    ordered: list[str] = []
    seen: set[str] = set()
    for _, intent in hits:
        if intent not in seen:
            ordered.append(intent)
            seen.add(intent)
    return ordered


def expand_synonyms(tokens: Iterable[str]) -> list[str]:
    reverse = _synonym_lookup()
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        canonical = reverse.get(token)
        if canonical and canonical not in expanded:
            expanded.append(canonical)
    return expanded


def hints_from_context(query: str, context: object) -> list[str]:
    """Bias the score using file extensions and visible context hints."""

    text = f"{query}\n{_flatten(context)}".lower()
    hints: list[str] = []
    for ext, ext_hints in EXTENSION_HINTS.items():
        ext_name = ext.lstrip(".")
        if ext in text or re.search(rf"\b{re.escape(ext_name)}\b", text):
            hints.extend(ext_hints)
    for path in PATH_RE.findall(text):
        lower = path.lower()
        for ext, ext_hints in EXTENSION_HINTS.items():
            if lower.endswith(ext):
                hints.extend(ext_hints)
    return list(dict.fromkeys(hints))


def extract_numbers(query: str) -> dict[str, str]:
    """Extract numeric signals such as ports, pids, and line counts."""

    text = normalize_query(query)
    signals: dict[str, str] = {}
    for name, pattern in NUMBER_PATTERNS.items():
        match = re.search(pattern, text)
        if not match:
            continue
        group = match.groupdict()
        for key, value in group.items():
            if value:
                signals[key or name] = value
                break
    port = re.search(r"\bport\s+(\d{2,5})\b", text)
    if port:
        signals["port"] = port.group(1)
    pid = re.search(r"\bpid\s+(\d+)\b", text)
    if pid:
        signals["pid"] = pid.group(1)
    lines = re.search(r"\b(\d+)\s+lines?\b", text)
    if lines:
        signals["lines"] = lines.group(1)
    return signals


def _find_paths(text: str) -> list[str]:
    candidates: list[str] = []
    for quoted in QUOTED_RE.findall(text):
        candidate = next((item for item in quoted if item), "")
        if candidate:
            candidates.append(candidate)
    candidates.extend(PATH_RE.findall(text))
    return [item for item in dict.fromkeys(candidates) if item]


def _context_paths(context: object) -> list[str]:
    text = _flatten(context)
    paths: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip().strip("-•*")
        if not cleaned:
            continue
        if cleaned.startswith(("OS:", "Current directory:", "Files in directory:", "Last shell commands:", "Recent shell commands:")):
            continue
        if cleaned.startswith(("/", "./", "../")) or re.match(r"^[A-Za-z]:\\", cleaned) or "." in cleaned:
            paths.append(cleaned)
    return paths


def _candidate_paths(context: object) -> list[str]:
    paths = _context_paths(context)
    return [item for item in dict.fromkeys(paths) if item]


def _match_context_path(context: object, *, extensions: Sequence[str] = (), names: Sequence[str] = ()) -> str:
    candidates = _candidate_paths(context)
    if not candidates:
        return ""
    context_text = _flatten(context).lower()
    for candidate in candidates:
        if candidate.lower() in context_text:
            return candidate
    for ext in extensions:
        for candidate in candidates:
            if candidate.lower().endswith(ext.lower()):
                return candidate
    for name in names:
        for candidate in candidates:
            if candidate.lower().endswith(name.lower()):
                return candidate
    return candidates[0]


def _match_directory(context: object) -> str:
    candidates = _candidate_paths(context)
    for candidate in candidates:
        if Path(candidate).is_dir():
            return candidate
    return "."


def _infer_batch_rename(query: str) -> dict[str, str]:
    text = normalize_query(query)
    match = re.search(r"\brename\b.*?\ball\b.*?\b([a-z0-9]+)\b.*?\bfiles?\b.*?\bto\b.*?\b([a-z0-9]+)\b", text)
    if match:
        return {
            "from_ext": match.group(1),
            "to_ext": match.group(2),
            "source": f"*.{match.group(1)}",
            "destination": f"*.{match.group(2)}",
        }
    match = re.search(r"\b(?:extension|suffix)\s+([a-z0-9]+)\b.*?\bto\b\s+([a-z0-9]+)\b", text)
    if match:
        return {
            "from_ext": match.group(1),
            "to_ext": match.group(2),
            "source": f"*.{match.group(1)}",
            "destination": f"*.{match.group(2)}",
        }
    return {}


def _default_command_slots(query: str, context: object, signals: Mapping[str, str]) -> dict[str, str]:
    slots = _infer_slots(query, context, signals)
    query_text = normalize_query(query)
    rename_slots = _infer_batch_rename(query_text)
    slots.update(rename_slots)

    if any(word in query_text for word in ("extract", "unpack", "decompress", "untar")):
        matched = _match_context_path(context, extensions=(".tar.gz", ".tgz", ".gz", ".zip", ".bz2", ".xz"))
        if matched:
            slots["file"] = matched
            slots["path"] = matched
            slots["target"] = matched

    if any(word in query_text for word in ("rename", "move")):
        candidates = _candidate_paths(context)
        if len(candidates) >= 2 and not rename_slots:
            slots["source"] = candidates[0]
            slots["destination"] = candidates[1]
        if rename_slots:
            slots["source"] = rename_slots["source"]
            slots["destination"] = rename_slots["destination"]

    if any(word in query_text for word in ("copy", "duplicate")):
        candidates = _candidate_paths(context)
        if candidates:
            slots["source"] = candidates[0]
            slots["destination"] = str(Path(candidates[0]).with_suffix(".copy"))

    if any(word in query_text for word in ("run", "execute")):
        matched = _match_context_path(context, extensions=(".py", ".sh", ".js", ".ts"))
        if matched:
            slots["file"] = matched

    if any(word in query_text for word in ("delete", "remove", "erase")):
        slots["path"] = _match_context_path(context)

    return slots


def _pick_command_name(query: str, tokens: Sequence[str], registry: Mapping[str, Mapping]) -> str:
    for token in tokens:
        if token in registry:
            return token
    for name in registry:
        if name.lower() in query:
            return name
    return ""


def _score_similarity(token: str, keyword: str) -> int:
    if token == keyword:
        return 10
    if token in keyword or keyword in token:
        return 5
    ratio = SequenceMatcher(None, token, keyword).ratio()
    if ratio >= 0.88:
        return 3
    return 0


def _template_tokens(template_key: str) -> list[str]:
    return [token for token in re.split(r"[_\s-]+", template_key.lower()) if token]


def _infer_slots(query: str, context: object, signals: Mapping[str, str]) -> dict[str, str]:
    text = f"{query}\n{_flatten(context)}"
    slots: dict[str, str] = {
        "path": ".",
        "target": ".",
        "dir": ".",
        "file": "",
        "pattern": "*",
        "url": "https://example.com",
        "host": "localhost",
        "service": "service",
        "process": "process",
        "package": "package",
        "module": "module",
        "archive": "archive",
        "json": "{}",
        "text": "text",
        "command": "command",
        "user": os.environ.get("USER", "user"),
        "group": os.environ.get("USER", "group"),
        "mode": "755",
        "kind": "f",
        "attribute": "com.apple.quarantine",
        "domain": "com.example.app",
        "key": "SomeKey",
        "value": "SomeValue",
        "label": "label",
        "device": "/dev/sda1",
        "source": ".",
        "destination": "./backup",
        "old": "old",
        "new": "new",
        "column": "1",
    }
    slots.update({key: value for key, value in signals.items()})

    urls = URL_RE.findall(text)
    if urls:
        slots["url"] = urls[0]

    paths = _find_paths(text)
    if paths:
        slots["file"] = paths[0]
        slots["path"] = paths[0]
        slots["target"] = paths[0]
        slots["source"] = paths[0]
    if len(paths) > 1:
        slots["destination"] = paths[1]

    file_like = re.findall(r"\b[\w./-]+\.[a-z0-9]{1,8}\b", text.lower())
    if file_like and not slots.get("file"):
        slots["file"] = file_like[0]

    word_match = re.search(r"\b(?:service|process|package|module|host|label|domain|key)\s+([a-zA-Z0-9._-]+)", text)
    if word_match:
        slots.setdefault("service", word_match.group(1))
        slots.setdefault("process", word_match.group(1))
        slots.setdefault("package", word_match.group(1))
        slots.setdefault("module", word_match.group(1))
        slots.setdefault("host", word_match.group(1))

    if "port" in signals:
        slots["port"] = signals["port"]
    if "pid" in signals:
        slots["pid"] = signals["pid"]
    if "lines" in signals:
        slots["lines"] = signals["lines"]
    if "days" in signals:
        slots["days"] = signals["days"]
    if "hours" in signals:
        slots["hours"] = signals["hours"]
    if "size" in signals:
        slots["size"] = signals["size"]
    if any(word in text.lower() for word in ("directory", "directories", "folder", "folders")):
        slots["kind"] = "d"
    elif any(word in text.lower() for word in ("file", "files")):
        slots["kind"] = "f"
    return slots


def _template_score(template: str, query: str, tokens: Sequence[str], slots: Mapping[str, str]) -> int:
    score = 0
    template_words = set(_template_tokens(template))
    if template_words & set(tokens):
        score += len(template_words & set(tokens)) * 2
    if any(marker in query for marker in template_words):
        score += 2
    if slots.get("kind") == "d" and ("-type" in template or "directory" in query or "folder" in query):
        score += 8
    if slots.get("kind") == "f" and "-type f" in template:
        score += 3
    if "directory" in query or "directories" in query or "folder" in query:
        if "-type d" in template or "directories" in template:
            score += 10
        if "-name" in template:
            score -= 2
    if "{port}" in template and "port" in query:
        score += 3
    if "{pid}" in template and ("pid" in query or "process" in query):
        score += 3
    if "{file}" in template and any(token in query for token in ("file", "archive", "zip", "gz", "tar")):
        score += 3
    return score


def fill_template(template: str, slots: Mapping[str, str]) -> str | None:
    """Safely render a template with best-effort placeholder substitution."""

    placeholders = PLACEHOLDER_RE.findall(template)
    missing = [key for key in placeholders if not slots.get(key)]
    if missing and any(key in REQUIRED_PLACEHOLDERS for key in missing):
        return None

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = slots.get(key)
        if value in (None, ""):
            return match.group(0)
        if key in {"file", "path", "target", "source", "destination", "dir", "archive"}:
            return shlex.quote(str(value))
        return str(value)

    rendered = PLACEHOLDER_RE.sub(replace, template)
    if PLACEHOLDER_RE.search(rendered):
        return None
    return rendered


def _template_renderable(template: str, slots: Mapping[str, str]) -> bool:
    return fill_template(template, slots) is not None


def _score_command(name: str, spec: Mapping[str, object], tokens: Sequence[str], query: str, intents: Sequence[str], hints: Sequence[str], signals: Mapping[str, str]) -> tuple[int, str]:
    keywords = [str(item).lower() for item in spec.get("keywords", [])]
    intent_map = {str(key).lower(): str(value) for key, value in spec.get("intent_map", {}).items()}
    templates = {str(key).lower(): str(value) for key, value in spec.get("templates", {}).items()}
    score = 0

    if name.lower() in query:
        score += 7

    for token in tokens:
        for keyword in keywords:
            score += _score_similarity(token, keyword)

    for hint in hints:
        if hint in keywords or hint in tokens:
            score += 2

    for intent in intents:
        template_key = intent_map.get(intent)
        if template_key:
            score += 12
            if template_key in templates:
                score += 5

    for key in templates:
        if key in query:
            score += 4
        for token in _template_tokens(key):
            if token in tokens:
                score += 2

    if "port" in signals and any(word in keywords for word in ("port", "network", "socket")):
        score += 5
    if "pid" in signals and any(word in keywords for word in ("process", "pid")):
        score += 5
    if "days" in signals and any(word in keywords for word in ("older", "mtime", "log", "files")):
        score += 3

    if name in {"mv", "cp", "rm"} and any(word in query for word in ("rename", "move", "copy", "delete", "remove")):
        score += 10

    best_template = ""
    best_template_score = -1
    for key, template in templates.items():
        template_score = _template_score(template, query, tokens, _default_command_slots(query, "", signals))
        if not _template_renderable(template, _default_command_slots(query, "", signals)):
            template_score -= 100
        if template_score > best_template_score:
            best_template_score = template_score
            best_template = template
    return score, best_template


def _choose_template(spec: Mapping[str, object], query: str, intents: Sequence[str], tokens: Sequence[str], signals: Mapping[str, str], slots: Mapping[str, str]) -> str:
    templates = {str(key).lower(): str(value) for key, value in spec.get("templates", {}).items()}
    intent_map = {str(key).lower(): str(value) for key, value in spec.get("intent_map", {}).items()}
    if not templates:
        return ""

    if any(word in query for word in ("directory", "directories", "folder", "folders")):
        for key in ("directories", "type", "list", "basic"):
            template = templates.get(key)
            if template and ("-type d" in template or key in {"directories", "type", "list"}):
                return template
    if any(word in query for word in ("file", "files")):
        for key in ("files", "type", "basic", "name"):
            template = templates.get(key)
            if template and ("-type f" in template or key in {"files", "type", "basic", "name"}):
                return template

    for intent in intents:
        mapped = intent_map.get(intent)
        if mapped and mapped in templates:
            return templates[mapped]

    for key in templates:
        if key in query:
            return templates[key]

    scored: list[tuple[int, str]] = []
    for key, template in templates.items():
        local = 0
        for token in _template_tokens(key):
            if token in tokens:
                local += 3
        if any(slot in template for slot in signals):
            local += 1
        local += _template_score(template, query, tokens, slots)
        if not _template_renderable(template, slots):
            local -= 100
        scored.append((local, key))
    scored.sort(key=lambda item: item[0], reverse=True)
    return templates[scored[0][1]] if scored else next(iter(templates.values()))


def rank_candidates(query: str, context: object = "", os_info: object | None = None, limit: int = 5) -> list[dict[str, object]]:
    """Return ranked command candidates for inspection or JSON output."""

    normalized_os = normalize_os_name(str(os_info) if os_info is not None else None)
    registry = get_registry(normalized_os)
    query_text = normalize_query(query)
    tokens = tokenize(query_text)
    vocabulary = build_vocabulary(registry)
    tokens = correct_typos(tokens, vocabulary)
    tokens = expand_synonyms(tokens)
    intents = extract_intent(query_text)
    hints = hints_from_context(query_text, context)
    signals = extract_numbers(query_text)
    slot_values = _default_command_slots(query_text, context, signals)

    ranked: list[RankedCommand] = []
    for name, spec in registry.items():
        score, _ = _score_command(name, spec, tokens, query_text, intents, hints, signals)
        template = _choose_template(spec, query_text, intents, tokens, signals, slot_values)
        rendered = fill_template(template, slot_values) if template else ""
        if rendered is None:
            continue
        ranked.append(RankedCommand(name=name, score=score, template_key=template, rendered=rendered, intent=intents[0] if intents else None))

    ranked.sort(key=lambda item: item.score, reverse=True)
    payload: list[dict[str, object]] = []
    for item in ranked[: max(1, limit)]:
        payload.append(
            {
                "command": item.name,
                "score": item.score,
                "rendered": item.rendered,
                "template": item.template_key,
                "intent": item.intent,
            }
        )
    return payload


def call_local_registry(query: str, context: object = "", os_info: object | None = None) -> str:
    """Return the best local command or an empty string if confidence is low."""

    candidates = rank_candidates(query, context=context, os_info=os_info, limit=1)
    if not candidates:
        return ""
    best = candidates[0]
    if int(best["score"]) < MIN_CONFIDENCE:
        return ""
    rendered = best.get("rendered")
    return str(rendered) if rendered else ""


__all__ = [
    "MIN_CONFIDENCE",
    "RankedCommand",
    "call_local_registry",
    "correct_typos",
    "extract_intent",
    "extract_numbers",
    "fill_template",
    "hints_from_context",
    "rank_candidates",
    "tokenize",
]
