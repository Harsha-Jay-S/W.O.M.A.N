"""Runtime reranker for heuristic command candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from .features import build_inference_frame
from .safety import rerank_with_safety

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent / "models" / "woman_reranker.joblib"
)


class WomanReranker:
    def __init__(self, model_path: str | Path | None = None) -> None:
        self.model_path = (
            Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH
        )
        self.model = None
        if self.model_path.exists():
            try:
                import joblib
                self.model = joblib.load(self.model_path)
            except ImportError:
                pass  # ML reranker disabled; graceful fallback to heuristic

    @property
    def available(self) -> bool:
        return self.model is not None

    def rerank(
        self,
        query: str,
        os_name: str,
        recent_history: Sequence[str] | str,
        candidates: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        rows = build_inference_frame(query, os_name, recent_history, candidates)
        if not rows:
            return []
        if self.model is None:
            return rerank_with_safety(rows)

        import pandas as pd  # lazy import; pandas is an optional ML dependency
        frame = pd.DataFrame(rows)
        probs = self.model.predict_proba(frame)[:, 1]

        scored: list[dict[str, object]] = []
        for row, prob in zip(rows, probs, strict=False):
            item = dict(row)
            item["ml_score"] = float(prob)
            scored.append(item)
        return rerank_with_safety(scored)
