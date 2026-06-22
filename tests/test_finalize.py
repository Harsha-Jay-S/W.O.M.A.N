"""Tests for the post-render finalize layer (scope correctness + safety)."""

from __future__ import annotations

from pathlib import Path

from woman_revamp.finalize import FinalizedCommand, finalize_command


def test_per_folder_is_the_default_reading_for_all_folders():
    """'all folders' with no merge words → one archive per top-level folder."""
    result = finalize_command(
        "zip all available folders in this directory",
        "zip -r archive.zip .",
        intents=[],
        cwd=".",
    )
    assert isinstance(result, FinalizedCommand)
    cmd = result.command
    # POSIX-portable: runs under /bin/sh (dash) as well as bash — no `shopt`.
    assert "shopt" not in cmd
    assert "for d in */" in cmd
    assert '[ -d "$d" ] || continue' in cmd
    assert 'zip -r "${d%/}.zip" "$d"' in cmd
    # restatement makes the chosen reading falsifiable
    assert "each top-level folder" in result.restatement
    assert "own archive" in result.restatement
    assert "excluding hidden" in result.restatement


def test_merge_words_select_one_combined_archive():
    """'into one archive' → single combined archive over top-level folders."""
    result = finalize_command(
        "zip all folders into one archive",
        "zip -r archive.zip .",
        intents=[],
        cwd=".",
    )
    assert result.command == "zip -r archive.zip */"
    assert "combined" in result.restatement.lower()
    assert "shopt" not in result.command  # not the per-folder loop


def test_tar_archive_op_detected_from_command_verb():
    """Per-folder reading also works when the op is tar, not zip."""
    result = finalize_command(
        "compress all folders here",
        "tar -czf archive.tar.gz .",
        intents=["compress"],
        cwd=".",
    )
    assert "for d in */" in result.command
    assert 'tar -czf "${d%/}.tar.gz" "$d"' in result.command


def test_path_portability_rewrites_absolute_cwd_to_dot():
    """A command echoing the absolute cwd is made relative (generic, any verb)."""
    cwd = "/home/someone/project"
    result = finalize_command(
        "list files here",
        f"ls -la {cwd}",
        intents=["list"],
        cwd=cwd,
    )
    assert result.command == "ls -la ."
    assert cwd not in result.command


def test_non_folder_archive_query_is_left_alone():
    """'compress this directory' is one archive of the dir, not a per-folder loop."""
    result = finalize_command(
        "compress this directory",
        "tar -czf archive.tar.gz .",
        intents=["compress"],
        cwd=".",
    )
    assert "for d in */" not in result.command
    assert result.command == "tar -czf archive.tar.gz ."


def test_collision_detected_and_flagged(tmp_path: Path):
    """Existing output names in cwd → overwrite flagged, not silently clobbered."""
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo.zip").write_text("old")  # would be overwritten
    result = finalize_command(
        "zip all folders here",
        "zip -r archive.zip .",
        intents=[],
        cwd=str(tmp_path),
    )
    assert result.overwrite is True
    assert "foo.zip" in result.collisions


def test_no_collision_when_outputs_absent(tmp_path: Path):
    (tmp_path / "foo").mkdir()
    (tmp_path / "bar").mkdir()
    result = finalize_command(
        "zip all folders here",
        "zip -r archive.zip .",
        intents=[],
        cwd=str(tmp_path),
    )
    assert result.overwrite is False
    assert result.collisions == []


def test_risk_low_for_per_folder_zip_without_collision(tmp_path: Path):
    (tmp_path / "foo").mkdir()
    result = finalize_command(
        "zip all folders here",
        "zip -r archive.zip .",
        intents=[],
        cwd=str(tmp_path),
    )
    assert result.risk_level == "Low"
    assert result.risk_score < 0.4


def test_risk_high_for_recursive_force_delete():
    result = finalize_command(
        "delete tmp",
        "rm -rf /tmp/scratch",
        intents=["delete"],
        cwd=".",
    )
    assert result.risk_level == "High"
    assert result.risk_score >= 0.85


def test_collision_raises_risk_off_low(tmp_path: Path):
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo.zip").write_text("old")
    result = finalize_command(
        "zip all folders here",
        "zip -r archive.zip .",
        intents=[],
        cwd=str(tmp_path),
    )
    assert result.risk_level != "Low"
    assert "Overwrites" in " ".join(result.risk_reasons)


def test_restatement_is_nonempty_when_scope_transformed():
    result = finalize_command(
        "zip all folders here",
        "zip -r archive.zip .",
        intents=[],
        cwd=".",
    )
    assert result.restatement.strip() != ""
