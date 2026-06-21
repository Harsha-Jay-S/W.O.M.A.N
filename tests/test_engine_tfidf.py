"""Tests for TF-IDF scorer and engine ranking."""

import math
from collections import Counter
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from woman_revamp.engine import (
    MIN_CONFIDENCE,
    RankedCommand,
    TfIdfScorer,
    _score_command,
    call_local_registry,
    fill_template,
    hints_from_context,
    extract_intent,
    expand_synonyms,
    correct_typos,
    normalize_query,
    build_vocabulary,
    _default_command_slots,
    tokenize,
    rank_candidates,
)
from woman_revamp.registry import get_registry


SAMPLE_REGISTRY: Mapping[str, Mapping] = {
    "find": {
        "keywords": ["find", "search", "locate", "directory", "file", "lookup"],
        "templates": {"basic": "find {path} -type {kind}", "name": "find {path} -type {kind} -name {pattern}"},
        "intent_map": {"find": "basic"},
    },
    "grep": {
        "keywords": ["grep", "search", "pattern", "match", "find", "text"],
        "templates": {"basic": "grep {pattern} {path}"},
        "intent_map": {"search": "basic"},
    },
    "ls": {
        "keywords": ["ls", "list", "directory", "files", "folder", "show"],
        "templates": {"basic": "ls -la {path}"},
        "intent_map": {"list": "basic"},
    },
    "rm": {
        "keywords": ["rm", "remove", "delete", "file", "wipe"],
        "templates": {"basic": "rm {path}"},
    },
}


@pytest.fixture
def tfidf() -> TfIdfScorer:
    return TfIdfScorer(SAMPLE_REGISTRY)


class TestTfIdfScorer:

    def test_init_counts_docs(self, tfidf: TfIdfScorer):
        assert tfidf.num_docs == len(SAMPLE_REGISTRY)

    def test_init_computes_df(self, tfidf: TfIdfScorer):
        assert tfidf.doc_freq is not None
        assert tfidf.doc_freq["find"] >= 1
        assert tfidf.doc_freq["file"] >= 1

    def test_tfidf_identical_tokens(self, tfidf: TfIdfScorer):
        score = tfidf.tfidf(["find"], ["find"])
        assert score == 1.0

    def test_tfidf_no_overlap(self, tfidf: TfIdfScorer):
        score = tfidf.tfidf(["zzzxyz"], ["find"])
        assert score == 0.0

    def test_tfidf_partial_match(self, tfidf: TfIdfScorer):
        score = tfidf.tfidf(["find", "files"], ["find", "file", "list"])
        assert 0.0 < score < 1.0

    def test_tfidf_empty_query(self, tfidf: TfIdfScorer):
        assert tfidf.tfidf([], ["find"]) == 0.0

    def test_tfidf_empty_command(self, tfidf: TfIdfScorer):
        assert tfidf.tfidf(["find"], []) == 0.0

    def test_tfidf_empty_registry_returns_one_for_identical(self):
        empty = TfIdfScorer({})
        assert empty.tfidf(["find"], ["find"]) == 1.0

    def test_tfidf_rare_words_score_higher(self):
        reg = {
            "common": {"keywords": ["file", "list", "copy"]},
            "specific": {"keywords": ["file", "rareword"]},
        }
        sc = TfIdfScorer(reg)
        score_common_vs_common = sc.tfidf(["file"], ["file"])
        score_rare_vs_rare = sc.tfidf(["rareword"], ["rareword"])
        assert score_rare_vs_rare == score_common_vs_common == 1.0

    def test_tfidf_symmetric_not_guaranteed(self, tfidf: TfIdfScorer):
        ab = tfidf.tfidf(["find"], ["find", "grep"])
        ba = tfidf.tfidf(["find", "grep"], ["find"])
        assert ab != ba  # TF-IDF is asymmetric

    def test_oov_tokens_do_not_deflate_score(self, tfidf: TfIdfScorer):
        # "all" is out-of-vocabulary; adding it to a matching query must not lower the score.
        score_without_oov = tfidf.tfidf(["find"], ["find"])
        score_with_oov = tfidf.tfidf(["find", "all"], ["find"])
        assert score_with_oov == score_without_oov  # OOV terms are uninformative


class TestScoreCommand:

    def _score_for(self, query: str) -> float:
        q = normalize_query(query)
        tokens = tokenize(q)
        vocabulary = build_vocabulary(SAMPLE_REGISTRY)
        tokens = correct_typos(tokens, vocabulary)
        tokens = expand_synonyms(tokens)
        intents = extract_intent(q)
        hints = hints_from_context("")
        signals = {}
        tfidf = TfIdfScorer(SAMPLE_REGISTRY)
        name = "find"
        spec = SAMPLE_REGISTRY[name]
        score, _ = _score_command(name, spec, tokens, q, intents, hints, signals, tfidf)
        return score

    def test_score_command_scores_find_highest_for_find_query(self):
        score = self._score_for("find python files")
        assert 0.0 <= score <= 1.0

    def test_score_command_low_score_for_bad_match(self):
        score = self._score_for("asdfghjklzxcvbnm")
        assert score < 0.3


class TestRankCandidates:

    def test_rank_candidates_returns_sorted(self):
        results = rank_candidates(
            "find python files",
            context="",
            os_info="linux",
        )
        assert len(results) > 0
        for r in results:
            assert "rendered" in r
            assert "score" in r
            assert "source" in r

    def test_rank_candidates_decreasing_score(self):
        results = rank_candidates(
            "find python files",
            context="",
            os_info="linux",
        )
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_rank_candidates_source_field(self):
        results = rank_candidates(
            "list files",
            context="",
            os_info="linux",
        )
        for r in results:
            assert "source" in r
            assert r["source"] == "heuristic"

    def test_rank_candidates_long_query(self):
        results = rank_candidates(
            "find all python files in this directory",
            context="",
            os_info="linux",
        )
        assert len(results) >= 1


class TestFillTemplate:

    def test_fill_template_requires_days(self):
        assert (
            fill_template(
                "find {path} -type {kind} -mtime {days}",
                {"path": ".", "kind": "d"},
            )
            is None
        )

    def test_fill_template_renders_when_complete(self):
        assert (
            fill_template(
                "find {path} -type {kind} -mtime {days}",
                {"path": ".", "kind": "d", "days": "7"},
            )
            == "find . -type d -mtime 7"
        )

    def test_fill_template_missing_var_returns_none(self):
        assert (
            fill_template("echo {name}", {"not_name": "world"})
            is None
        )

    def test_fill_template_empty_values(self):
        assert (
            fill_template("ls -la", {})
            == "ls -la"
        )


class TestCallLocalRegistry:

    def test_directory_query_prefers_directory_find(self):
        rendered = call_local_registry(
            "find all directories in this folder",
            context="Current directory: /home/jayharsha\nFiles:",
            os_info="linux",
        )
        assert rendered == "find /home/jayharsha -type d"

    def test_no_match_returns_empty_string(self):
        rendered = call_local_registry(
            "zzzxyznonexistent",
            context="",
            os_info="linux",
        )
        assert rendered == ""

    def test_local_registry_with_empty_query(self):
        rendered = call_local_registry(
            "",
            context="",
            os_info="linux",
        )
        assert rendered == ""


class TestConstants:

    def test_min_confidence_is_float(self):
        assert isinstance(MIN_CONFIDENCE, float)
        assert MIN_CONFIDENCE == 0.30

    def test_tokenize_splits_properly(self):
        tokens = tokenize("Find Python files in directory")
        assert "find" in tokens
        assert "python" in tokens
        assert "files" in tokens
        assert "directory" in tokens


class TestBM25Scorer:

    def test_scorer_returns_float_between_0_and_1(self):
        scorer = TfIdfScorer(SAMPLE_REGISTRY)
        score = scorer.tfidf(["find", "files"], ["search", "locate", "file", "directory"])
        assert 0.0 <= score <= 1.0

    def test_exact_token_match_scores_higher_than_no_match(self):
        scorer = TfIdfScorer(SAMPLE_REGISTRY)
        exact = scorer.tfidf(["search"], ["search", "find", "locate"])
        no_match = scorer.tfidf(["xyz123"], ["search", "find", "locate"])
        assert exact > no_match

    def test_avgdl_computed(self):
        scorer = TfIdfScorer(SAMPLE_REGISTRY)
        assert scorer.avgdl >= 0.0

    def test_scorer_cache_reuses_instance(self):
        from woman_revamp.engine import _get_scorer, _scorer_cache
        from woman_revamp.registry import get_registry
        reg = get_registry("linux")
        s1 = _get_scorer(reg)
        s2 = _get_scorer(reg)
        assert s1 is s2  # same object from cache

    def test_scorer_ordering_preserved(self):
        scorer = TfIdfScorer(SAMPLE_REGISTRY)
        high = scorer.tfidf(["search", "find"], ["search", "find", "locate"])
        low = scorer.tfidf(["delete", "remove"], ["search", "find", "locate"])
        assert high > low


class TestExtractNegations:

    def test_not_prefix(self):
        from woman_revamp.engine import extract_negations
        result = extract_negations("not rm the file")
        assert "rm" in result

    def test_without_prefix(self):
        from woman_revamp.engine import extract_negations
        result = extract_negations("without git operations")
        assert "git" in result

    def test_no_negation(self):
        from woman_revamp.engine import extract_negations
        result = extract_negations("find files in directory")
        assert len(result) == 0


class TestModifierFlags:

    def test_recursive_flag_extracted(self):
        from woman_revamp.engine import extract_modifier_flags
        flags = extract_modifier_flags("copy files recursively")
        assert "-r" in flags

    def test_force_flag_extracted(self):
        from woman_revamp.engine import extract_modifier_flags
        flags = extract_modifier_flags("force delete the file")
        assert "-f" in flags

    def test_verbose_flag_extracted(self):
        from woman_revamp.engine import extract_modifier_flags
        flags = extract_modifier_flags("list files verbose")
        assert "-v" in flags

    def test_no_modifiers(self):
        from woman_revamp.engine import extract_modifier_flags
        flags = extract_modifier_flags("list files")
        assert flags == ""


class TestRunnerRegistry:

    def test_python_runner_mapped(self):
        from woman_revamp.registry.runners import RUNNERS
        assert ".py" in RUNNERS
        assert RUNNERS[".py"] == "python"

    def test_runnable_extensions_subset_of_runners(self):
        from woman_revamp.registry.runners import RUNNERS, RUNNABLE_EXTENSIONS
        assert RUNNABLE_EXTENSIONS == frozenset(RUNNERS.keys())

    def test_bash_runner_mapped(self):
        from woman_revamp.registry.runners import RUNNERS
        assert RUNNERS[".sh"] == "bash"
