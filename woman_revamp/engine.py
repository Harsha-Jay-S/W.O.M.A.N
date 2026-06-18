"""Scoring and template resolution for the local woman registry."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from difflib import get_close_matches
import getpass
import math
import re
import shlex
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .registry import get_registry, normalize_os_name
from .registry.extension_hints import EXTENSION_HINTS
from .registry.intent_phrases import INTENT_PHRASES
from .registry.modifiers import FLAGS_AWARE_COMMANDS, MODIFIER_FLAGS
from .registry.numbers import NUMBER_PATTERNS
from .registry.pipes import PIPE_PATTERNS
from .registry.runners import RUNNERS, RUNNABLE_EXTENSIONS
from .registry.synonyms import SYNONYMS

# Project-type → commands that receive a scoring boost
_PROJECT_BOOSTS: dict[str, tuple[set[str], float]] = {
    "git":    ({"git"}, 0.30),
    "docker": ({"docker"}, 0.25),
    "python": ({"python", "pip", "pytest"}, 0.20),
    "node":   ({"npm", "node"}, 0.20),
    "make":   ({"make"}, 0.15),
    "rust":   ({"cargo"}, 0.20),
    "go":     ({"go"}, 0.20),
}

MIN_CONFIDENCE = 0.30
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
PATH_RE = re.compile(
    r"(?:[a-zA-Z]:\\[^\s]+|/[^\s]+|\./[^\s]+|\../[^\s]+|[^\s]+\.[a-zA-Z0-9]{1,8})"
)
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


# Module-level scorer/vocabulary caches keyed by registry object id
_scorer_cache: dict[int, "TfIdfScorer"] = {}
_vocab_cache: dict[int, list[str]] = {}


class TfIdfScorer:
    """BM25 similarity scorer for command keywords (replaces TF-IDF)."""

    def __init__(self, registry: Mapping[str, Mapping]) -> None:
        self.doc_freq: Counter[str] = Counter()
        self.num_docs = len(registry)
        total_len = 0
        for _name, spec in registry.items():
            kw_tokens = tokenize(" ".join(str(k) for k in spec.get("keywords", [])))
            total_len += len(kw_tokens)
            for t in set(kw_tokens):
                self.doc_freq[t] += 1
        self.avgdl: float = total_len / max(self.num_docs, 1)

    def tfidf(
        self, query_tokens: Sequence[str], cmd_tokens: Sequence[str]
    ) -> float:
        """BM25 similarity between query tokens and command keyword tokens."""
        if not query_tokens:
            return 0.0
        cmd_set = set(cmd_tokens)
        qtf = Counter(query_tokens)
        dl = len(cmd_tokens)
        k1, b = 1.5, 0.75
        score = 0.0
        max_possible = 0.0
        for token, tf in qtf.items():
            df = self.doc_freq.get(token, 0)
            idf = math.log((self.num_docs - df + 0.5) / (df + 0.5) + 1)
            bm25_tf = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / (self.avgdl or 1)))
            if token in cmd_set:
                score += idf * bm25_tf
            max_possible += idf * bm25_tf
        return score / (max_possible or 1)


def _get_scorer(registry: Mapping[str, Mapping]) -> "TfIdfScorer":
    key = id(registry)
    if key not in _scorer_cache:
        _scorer_cache[key] = TfIdfScorer(registry)
    return _scorer_cache[key]


def _get_vocabulary(registry: Mapping[str, Mapping]) -> list[str]:
    key = id(registry)
    if key not in _vocab_cache:
        _vocab_cache[key] = build_vocabulary(registry)
    return _vocab_cache[key]


@dataclass(frozen=True)
class RankedCommand:
    name: str
    score: float
    template_key: str
    rendered: str | None
    intent: str | None = None


@dataclass
class WomanResult:
    """Typed result from rank_candidates(); use to_dict() for backward compat."""
    command: str
    rendered: str
    confidence_score: float
    source: str
    os_detected: str
    intent: str | None
    template_key: str
    danger_score: float = 0.0
    danger_reasons: list[str] = field(default_factory=list)
    ml_score: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "score": self.confidence_score,
            "rendered": self.rendered,
            "template": self.template_key,
            "intent": self.intent,
            "source": self.source,
        }


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


def build_vocabulary(registry: Mapping[str, Mapping]) -> list[str]:
    vocabulary: set[str] = set()
    vocabulary.update(_intent_tokens())
    for canonical, phrases in SYNONYMS.items():
        vocabulary.add(canonical)
        for phrase in phrases:
            vocabulary.update(tokenize(phrase))
    for spec in registry.values():
        vocabulary.update(tokenize(" ".join(spec.get("keywords", []))))
        vocabulary.update(tokenize(" ".join(spec.get("templates", {}).keys())))
        vocabulary.update(tokenize(" ".join(spec.get("intent_map", {}).keys())))
    for ext, hints in EXTENSION_HINTS.items():
        vocabulary.add(ext.lstrip("."))
        vocabulary.update(hints)
    for key in NUMBER_PATTERNS:
        vocabulary.add(key)
    return sorted(vocabulary)


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
    if not ordered:
        first_word = q.split()[0] if q.strip() else ""
        for intent, _ in INTENT_PHRASES:
            if first_word == intent:
                ordered.append(intent)
                break
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


def hints_from_context(context: object) -> list[str]:
    """Bias the score using file extensions from context only."""

    text = _flatten(context).lower()
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


_NEGATION_RE = re.compile(
    r"\b(?:not|without|except|excluding|no)\s+([a-z0-9_.-]+)", re.I
)


def extract_negations(query: str) -> set[str]:
    """Return the set of tokens that appear after negation words in the query."""
    return {m.group(1).lower() for m in _NEGATION_RE.finditer(query)}


def extract_modifier_flags(query: str) -> str:
    """Return a space-joined string of CLI flags found via modifier words."""
    text = query.lower()
    flags: list[str] = []
    for word, flag in MODIFIER_FLAGS.items():
        if word in text and flag not in flags:
            flags.append(flag)
    return " ".join(flags)


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
        if cleaned.startswith(
            (
                "OS:",
                "Current directory:",
                "Files in directory:",
                "Last shell commands:",
                "Recent shell commands:",
            )
        ):
            continue
        if (
            cleaned.startswith(("/", "./", "../"))
            or re.match(r"^[A-Za-z]:\\", cleaned)
            or re.search(r"\.[a-zA-Z0-9]{1,8}$", cleaned)
        ):
            paths.append(cleaned)
    return paths


def _candidate_paths(context: object) -> list[str]:
    paths = _context_paths(context)
    return [item for item in dict.fromkeys(paths) if item]


def _match_context_path(
    context: object, *, extensions: Sequence[str] = (), names: Sequence[str] = ()
) -> str:
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
    match = re.search(
        r"\brename\b.*?\ball\b.*?\b([a-z0-9]+)\b.*?\bfiles?\b.*?\bto\b.*?\b([a-z0-9]+)\b",
        text,
    )
    if match:
        from_e = match.group(1)
        to_e = match.group(2)
        return {
            "from_ext": from_e,
            "to_ext": to_e,
        }
    match = re.search(
        r"\b(?:extension|suffix)\s+([a-z0-9]+)\b.*?\bto\b\s+([a-z0-9]+)\b", text
    )
    if match:
        from_e = match.group(1)
        to_e = match.group(2)
        return {
            "from_ext": from_e,
            "to_ext": to_e,
        }
    return {}


def _default_command_slots(
    query: str,
    context: object,
    signals: Mapping[str, str],
    active_files: list[Path] | None = None,
) -> dict[str, str]:
    slots = _infer_slots(query, context, signals)
    query_text = normalize_query(query)
    rename_slots = _infer_batch_rename(query_text)
    slots.update(rename_slots)

    if any(word in query_text for word in ("extract", "unpack", "decompress", "untar")):
        matched = slots.get("file") or slots.get("path")
        if not matched or matched in (".", ""):
            matched = _match_context_path(
                context, extensions=(".tar.gz", ".tgz", ".gz", ".zip", ".bz2", ".xz")
            )
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
            slots["from_ext"] = rename_slots.get("from_ext", "")
            slots["to_ext"] = rename_slots.get("to_ext", "")

    if any(word in query_text for word in ("copy", "duplicate")):
        source = slots.get("file") or slots.get("path", "")
        if source in (".", "", None):
            source = _match_context_path(context)
        to_match = re.search(r"\bto\s+(\S+)", query_text)
        if to_match and source:
            slots["source"] = source
            slots["destination"] = to_match.group(1)
        elif source:
            slots["source"] = source
            slots["destination"] = str(Path(source).with_suffix(".copy"))

    if any(word in query_text for word in ("run", "execute")):
        # Prefer structured active_files list over text-scan
        if active_files:
            runnable = [p for p in active_files if p.suffix in RUNNABLE_EXTENSIONS]
            if runnable:
                slots["file"] = runnable[0].name
        if not slots.get("file"):
            matched = _match_context_path(context, extensions=(".py", ".sh", ".js", ".ts"))
            if matched:
                slots["file"] = matched

    if any(word in query_text for word in ("delete", "remove", "erase")):
        matched = _match_context_path(context)
        if matched and (not slots.get("path") or slots["path"] in (".", "")):
            slots["path"] = matched

    # Populate {flags} slot from modifier words in the query
    mod_flags = extract_modifier_flags(query)
    if mod_flags:
        slots["flags"] = mod_flags
    else:
        slots.setdefault("flags", "")

    return slots


def _pick_command_name(
    query: str, tokens: Sequence[str], registry: Mapping[str, Mapping]
) -> str:
    for token in tokens:
        if token in registry:
            return token
    for name in registry:
        if name.lower() in query:
            return name
    return ""


def _score_similarity(token: str, keyword: str) -> float:
    if token == keyword:
        return 1.0
    if token in keyword or keyword in token:
        return 0.7
    return 0.0


def _template_tokens(template_key: str) -> list[str]:
    return [token for token in re.split(r"[_\s-]+", template_key.lower()) if token]


def _infer_slots(
    query: str, context: object, signals: Mapping[str, str]
) -> dict[str, str]:
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
        "user": getpass.getuser(),
        "group": getpass.getuser(),
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

    word_match = re.search(
        r"\b(?:service|process|package|module|host|label|domain|key)\s+([a-zA-Z0-9._-]+)",
        text,
    )
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
    if any(
        word in query.lower()
        for word in ("directory", "directories", "folder", "folders")
    ):
        slots["kind"] = "d"
    elif any(word in query.lower() for word in ("file", "files")):
        slots["kind"] = "f"
    return slots


def _template_score(
    template: str, query: str, tokens: Sequence[str], slots: Mapping[str, str]
) -> int:
    score = 0
    template_words = set(_template_tokens(template))
    if template_words & set(tokens):
        score += len(template_words & set(tokens)) * 2
    if any(marker in query for marker in template_words):
        score += 2
    if slots.get("kind") == "d" and (
        "-type" in template or "directory" in query or "folder" in query
    ):
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
    if "{file}" in template and any(
        token in query for token in ("file", "archive", "zip", "gz", "tar")
    ):
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
        before = match.string[match.start() - 1] if match.start() > 0 else ""
        after = match.string[match.end()] if match.end() < len(match.string) else ""
        if (before == "'" and after == "'") or (before == '"' and after == '"'):
            return str(value)
        return shlex.quote(str(value))

    rendered = PLACEHOLDER_RE.sub(replace, template)
    if PLACEHOLDER_RE.search(rendered):
        return None
    return rendered


def _template_renderable(template: str, slots: Mapping[str, str]) -> bool:
    return fill_template(template, slots) is not None


def _score_command(
    name: str,
    spec: Mapping[str, object],
    tokens: Sequence[str],
    query: str,
    intents: Sequence[str],
    hints: Sequence[str],
    signals: Mapping[str, str],
    tfidf_scorer: TfIdfScorer | None = None,
    project_signals: dict[str, bool] | None = None,
    negations: set[str] | None = None,
) -> tuple[float, str]:
    keywords = [str(item).lower() for item in spec.get("keywords", [])]
    intent_map = {
        str(key).lower(): str(value)
        for key, value in spec.get("intent_map", {}).items()
    }
    templates = {
        str(key).lower(): str(value) for key, value in spec.get("templates", {}).items()
    }
    score = 0.0

    if name.lower() in query:
        score += 0.15

    if tfidf_scorer is not None:
        score += tfidf_scorer.tfidf(tokens, keywords) * 0.50

    for hint in hints:
        if hint in keywords or hint in tokens:
            score += 0.05

    for intent in intents:
        template_key = intent_map.get(intent)
        if template_key:
            # Bounded additive boost to prevent amplifying noise scores
            score = min(score + 0.25, score * 1.4) if score > 0.15 else score + 0.10
            if template_key in templates:
                score += 0.15
                template = templates[template_key]
                slot_values = _default_command_slots(query, "", signals)
                placeholders = PLACEHOLDER_RE.findall(template)
                query_filled = sum(
                    1
                    for p in placeholders
                    if slot_values.get(p, "") not in (".", "", None)
                )
                if query_filled == len(placeholders) and query_filled > 0:
                    score += 0.20

    query_token_set = set(tokens)
    for key in templates:
        key_toks = _template_tokens(key)
        # Use whole-token matching to prevent single-char keys matching as substrings
        if key_toks and any(t in query_token_set for t in key_toks):
            score += 0.06
        for token in key_toks:
            if token in query_token_set:
                score += 0.03

    if "port" in signals and any(
        word in keywords for word in ("port", "network", "socket")
    ):
        score += 0.08
    if "pid" in signals and any(word in keywords for word in ("process", "pid")):
        score += 0.08
    if "days" in signals and any(
        word in keywords for word in ("older", "mtime", "log", "files")
    ):
        score += 0.05

    if name == "mv" and any(word in query for word in ("rename", "move")):
        score += 0.12
    if name == "cp" and any(word in query for word in ("copy", "duplicate")):
        score += 0.12
        if " to " in query:
            score += 0.12
    if name == "rm" and any(word in query for word in ("delete", "remove", "erase")):
        score += 0.12

    best_template = ""
    best_template_score = -999.0
    for key, template in templates.items():
        template_score = _template_score(
            template, query, tokens, _default_command_slots(query, "", signals)
        )
        if not _template_renderable(
            template, _default_command_slots(query, "", signals)
        ):
            template_score -= 100
        if template_score > best_template_score:
            best_template_score = template_score
            best_template = template
    # Project-type context boosts — only when there's some vocabulary overlap
    # (prevents boosting commands with zero base score above MIN_CONFIDENCE)
    if project_signals and score > 0.05:
        for proj, (cmd_set, boost) in _PROJECT_BOOSTS.items():
            if project_signals.get(proj) and name.lower() in cmd_set:
                score += boost
                break  # only one boost per command

    # Negation penalty — user explicitly said "not <cmd>" or "without <cmd>"
    if negations and (name.lower() in negations or any(k in negations for k in keywords)):
        score -= 0.40

    return min(score, 1.0), best_template


def _choose_template(
    spec: Mapping[str, object],
    query: str,
    intents: Sequence[str],
    tokens: Sequence[str],
    signals: Mapping[str, str],
    slots: Mapping[str, str],
) -> str:
    templates = {
        str(key).lower(): str(value) for key, value in spec.get("templates", {}).items()
    }
    intent_map = {
        str(key).lower(): str(value)
        for key, value in spec.get("intent_map", {}).items()
    }
    if not templates:
        return ""

    if (
        "from_ext" in slots
        and "to_ext" in slots
        and slots["from_ext"]
        and slots["to_ext"]
    ):
        rename_template = templates.get("rename")
        if rename_template:
            return rename_template

    # Modifier flags win over all other heuristics: "recursively" → "recursive" template
    flags_str = extract_modifier_flags(query)
    if flags_str:
        flag_key_map = {"-r": "recursive", "-f": "force", "-v": "verbose", "-q": "quiet"}
        for flag, key in flag_key_map.items():
            if flag in flags_str and key in templates:
                return templates[key]

    if "days" in signals:
        for key in ("mtime", "files", "directories", "size"):
            template = templates.get(key)
            if template:
                return template

    if any(word in query for word in ("directory", "directories", "folder", "folders")):
        for key in ("directories", "type", "basic"):
            template = templates.get(key)
            if template and ("-type d" in template or key in {"directories", "type"}):
                return template
    if any(word in query for word in ("file", "files")):
        ext_match = re.search(r"\.([a-z0-9]+)", query)
        has_pattern_words = any(
            w in query for w in ("name", "extension", "called", "pattern")
        )
        if ext_match or has_pattern_words:
            for key in ("name", "files", "type", "basic"):
                template = templates.get(key)
                if template:
                    return template
        else:
            for key in ("files", "type", "basic", "name"):
                template = templates.get(key)
                if template:
                    return template

    # Intent-map after structural heuristics so "find directories" prefers the
    # "directories" template over "search" → "name" from the intent_map
    for intent in intents:
        mapped = intent_map.get(intent)
        if mapped and mapped in templates:
            return templates[mapped]

    query_tok_set = set(tokens)
    for key in templates:
        key_toks = _template_tokens(key)
        if key_toks and all(t in query_tok_set for t in key_toks):
            return templates[key]

    scored: list[tuple[int, str]] = []
    for key, template in templates.items():
        local = 0
        for token in _template_tokens(key):
            if token in query_tok_set:
                local += 3
        if any(slot in template for slot in signals):
            local += 1
        local += _template_score(template, query, tokens, slots)
        if not _template_renderable(template, slots):
            local -= 100
        scored.append((local, key))
    scored.sort(key=lambda item: item[0], reverse=True)
    return templates[scored[0][1]] if scored else next(iter(templates.values()))


def rank_candidates(
    query: str,
    context: object = "",
    os_info: object | None = None,
    limit: int = 5,
    active_files: list[Path] | None = None,
    project_signals: dict[str, bool] | None = None,
) -> list[dict[str, object]]:
    """Return ranked command candidates for inspection or JSON output."""

    normalized_os = normalize_os_name(str(os_info) if os_info is not None else None)
    registry = get_registry(normalized_os)
    query_text = normalize_query(query)
    tokens = tokenize(query_text)
    # Use cached scorer and vocabulary to avoid rebuilding on every call
    tfidf_scorer = _get_scorer(registry)
    vocabulary = _get_vocabulary(registry)
    tokens = correct_typos(tokens, vocabulary)
    tokens = expand_synonyms(tokens)
    intents = extract_intent(query_text)
    hints = hints_from_context(context)
    signals = extract_numbers(query_text)
    slot_values = _default_command_slots(query_text, context, signals, active_files)
    negations = extract_negations(query_text)

    # Pre-filter registry to candidates with keyword overlap
    query_tok_set = set(tokens)
    def _fast_candidate(cname: str, cspec: Mapping) -> bool:
        kw_tokens = set(tokenize(" ".join(str(k) for k in cspec.get("keywords", []))))
        return bool(query_tok_set & kw_tokens) or cname.lower() in query_text

    candidates_to_score = {n: s for n, s in registry.items() if _fast_candidate(n, s)}
    if len(candidates_to_score) < 5:
        candidates_to_score = dict(registry)

    # "Run" shortcut: if intent is run/execute and active_files has runnable scripts,
    # return them directly without scoring the full registry.
    if active_files and any(i in ("run", "execute") for i in intents):
        runnable = [p for p in active_files if p.suffix in RUNNABLE_EXTENSIONS]
        if runnable:
            shortcuts: list[dict[str, object]] = []
            for p in runnable[:limit]:
                runner = RUNNERS[p.suffix]
                shortcuts.append({
                    "command": runner.split()[0],
                    "score": 1.0 if len(runnable) == 1 else 0.95,
                    "rendered": f"{runner} {p.name}",
                    "template": "run_shortcut",
                    "intent": "run",
                    "source": "shortcut",
                })
            return shortcuts[:limit]

    # Pipe pattern shortcut — check query against pre-composed pipe templates
    for pattern, label, pipe_template in PIPE_PATTERNS:
        if pattern.search(query_text) or pattern.search(query):
            rendered_pipe = fill_template(pipe_template, slot_values) or pipe_template
            if rendered_pipe:
                pipe_result: list[dict[str, object]] = [{
                    "command": pipe_template.split()[0],
                    "score": 0.92,
                    "rendered": rendered_pipe,
                    "template": label,
                    "intent": label,
                    "source": "pipe_shortcut",
                }]
                # Still score the rest and prepend the pipe result
                break
    else:
        pipe_result = []

    ranked: list[RankedCommand] = []
    for name, spec in candidates_to_score.items():
        score, _ = _score_command(
            name, spec, tokens, query_text, intents, hints, signals, tfidf_scorer,
            project_signals=project_signals,
            negations=negations,
        )
        template = _choose_template(
            spec, query_text, intents, tokens, signals, slot_values
        )
        rendered = fill_template(template, slot_values) if template else ""
        if rendered is None:
            continue
        # Append modifier flags that aren't already present in the rendered command
        flags = slot_values.get("flags", "")
        if flags and name in FLAGS_AWARE_COMMANDS:
            new_flags = []
            for flag in flags.split():
                # For single-char flags (-r, -i, etc.) check combined-flag sequences too
                if re.match(r"-[a-zA-Z]$", flag):
                    char = flag[1]
                    if not re.search(rf"-[a-zA-Z]*{re.escape(char)}[a-zA-Z]*", rendered):
                        new_flags.append(flag)
                elif flag not in rendered:
                    new_flags.append(flag)
            if new_flags:
                rendered = rendered.rstrip() + " " + " ".join(new_flags)
        ranked.append(
            RankedCommand(
                name=name,
                score=score,
                template_key=template,
                rendered=rendered,
                intent=intents[0] if intents else None,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    payload: list[dict[str, object]] = list(pipe_result)
    remaining = max(1, limit) - len(payload)
    for item in ranked[:remaining]:
        payload.append(
            {
                "command": item.name,
                "score": item.score,
                "rendered": item.rendered,
                "template": item.template_key,
                "intent": item.intent,
                "source": "heuristic",
            }
        )
    return payload


def call_local_registry(
    query: str, context: object = "", os_info: object | None = None
) -> str:
    """Return the best local command or an empty string if confidence is low."""

    candidates = rank_candidates(query, context=context, os_info=os_info, limit=1)
    if not candidates:
        return ""
    best = candidates[0]
    if float(best["score"]) < MIN_CONFIDENCE:
        return ""
    rendered = best.get("rendered")
    return str(rendered) if rendered else ""


__all__ = [
    "MIN_CONFIDENCE",
    "RankedCommand",
    "TfIdfScorer",
    "call_local_registry",
    "correct_typos",
    "extract_intent",
    "extract_numbers",
    "fill_template",
    "hints_from_context",
    "rank_candidates",
    "tokenize",
]
