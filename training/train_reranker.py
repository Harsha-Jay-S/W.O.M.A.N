"""Train the LogisticRegression reranker from a processed pairwise dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer

DEFAULT_INPUT = Path.home() / "Downloads" / "processed_pairwise_reranker_data.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "ml" / "models" / "woman_reranker.joblib"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train woman reranker model")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Processed pairwise CSV")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Joblib output path")
    return parser


def build_pipeline() -> Pipeline:
    numeric_cols = ["token_overlap_ratio", "query_length", "candidate_length", "heuristic_rank"]
    bool_cols = ["has_pipe", "has_sudo", "has_git", "has_docker", "has_python", "is_destructive"]
    categorical_cols = ["os"]
    text_cols = ["query", "candidate_command", "recent_history", "combined_text"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("tfidf_query", TfidfVectorizer(ngram_range=(1, 2), min_df=1), "query"),
            ("tfidf_candidate", TfidfVectorizer(ngram_range=(1, 2), min_df=1), "candidate_command"),
            ("tfidf_history", TfidfVectorizer(ngram_range=(1, 2), min_df=1), "recent_history"),
            ("tfidf_combined", TfidfVectorizer(ngram_range=(1, 2), min_df=1), "combined_text"),
            (
                "num_bool",
                Pipeline(
                    [
                        ("select", SimpleImputer(strategy="constant", fill_value=0)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric_cols + bool_cols,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_cols,
            ),
        ],
        remainder="drop",
    )

    return Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "model",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="liblinear",
                    random_state=42,
                ),
            ),
        ]
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    df = df.copy()
    for column in ["query", "candidate_command", "recent_history", "combined_text", "os"]:
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str)
    for column in ["token_overlap_ratio", "query_length", "candidate_length", "heuristic_rank", "has_pipe", "has_sudo", "has_git", "has_docker", "has_python", "is_destructive"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    required = [
        "query",
        "candidate_command",
        "recent_history",
        "combined_text",
        "os",
        "token_overlap_ratio",
        "query_length",
        "candidate_length",
        "heuristic_rank",
        "has_pipe",
        "has_sudo",
        "has_git",
        "has_docker",
        "has_python",
        "is_destructive",
        "label",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise SystemExit(f"missing required columns: {', '.join(missing)}")

    groups = df["query"]
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(splitter.split(df, df["label"], groups=groups))
    train_df = df.iloc[train_idx].copy()
    test_df = df.iloc[test_idx].copy()

    pipeline = build_pipeline()
    pipeline.fit(train_df, train_df["label"].astype(int))

    probabilities = pipeline.predict_proba(test_df)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    print(classification_report(test_df["label"].astype(int), predictions))
    print("roc_auc:", roc_auc_score(test_df["label"].astype(int), probabilities))
    print("pr_auc:", average_precision_score(test_df["label"].astype(int), probabilities))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, output_path)
    print(f"saved model to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
