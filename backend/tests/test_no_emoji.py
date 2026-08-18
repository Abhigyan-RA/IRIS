"""Tests for the emoji checker that keeps status text plain and searchable."""

from __future__ import annotations

from pathlib import Path

from shadow_cpi.tooling.no_emoji import (
    DEFAULT_EXCLUDED_FILES,
    EmojiHit,
    find_emoji,
    iter_source_files,
    main,
    scan_paths,
)


def test_plain_ascii_text_has_no_hits() -> None:
    assert find_emoji("log.info('ingestion resumed')") == ()


def test_empty_text_has_no_hits() -> None:
    assert find_emoji("") == ()


def test_bracketed_status_labels_are_allowed() -> None:
    """Bracketed text labels are the replacement for emoji status markers."""
    narration = "[WARNING] 03:00 layout changed -> [AUTO-HEALING] 03:02 -> [RESOLVED] 03:03"

    assert find_emoji(narration) == ()


def test_pictographic_emoji_is_reported_with_position() -> None:
    hits = find_emoji("first line\nstatus: \u2705 done")

    assert hits == (EmojiHit(line=2, column=9, character="\u2705"),)


def test_warning_sign_and_variation_selector_are_reported() -> None:
    hits = find_emoji("\u26a0\ufe0f alert")

    assert [hit.character for hit in hits] == ["\u26a0", "\ufe0f"]


def test_robot_emoji_outside_the_basic_plane_is_reported() -> None:
    hits = find_emoji("\U0001f916 self-healing")

    assert hits == (EmojiHit(line=1, column=1, character="\U0001f916"),)


def test_accented_latin_text_is_not_treated_as_emoji() -> None:
    assert find_emoji("Cafe\u0301 na\u00efve \u00fcber") == ()


def test_box_drawing_characters_are_not_treated_as_emoji() -> None:
    assert find_emoji("\u250c\u2500\u2510") == ()


def test_scan_paths_reports_only_offending_files(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("value = 1\n", encoding="utf-8")
    dirty = tmp_path / "dirty.py"
    dirty.write_text('MESSAGE = "\U0001f680 ship it"\n', encoding="utf-8")

    findings = scan_paths([clean, dirty])

    assert list(findings) == [dirty]
    assert findings[dirty][0].character == "\U0001f680"


def test_iter_source_files_covers_code_and_docs_but_skips_binaries(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "page.tsx").write_text("export const a = 1;\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")

    names = sorted(path.name for path in iter_source_files(tmp_path))

    assert names == ["README.md", "app.py", "page.tsx"]


def test_iter_source_files_skips_dependency_and_build_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.py").write_text("x = 1\n", encoding="utf-8")
    for ignored in ("node_modules", ".venv", ".git", "dist"):
        (tmp_path / ignored).mkdir()
        (tmp_path / ignored / "skip.py").write_text('X = "\U0001f680"\n', encoding="utf-8")

    names = sorted(path.name for path in iter_source_files(tmp_path))

    assert names == ["keep.py"]


def test_iter_source_files_skips_the_requirements_document(tmp_path: Path) -> None:
    """The requirements document is an external input and is left untouched."""
    (tmp_path / "SHADOW_CPI_PRD_AND_ARCHITECTURE.md").write_text("\u26a0\ufe0f", encoding="utf-8")
    (tmp_path / "notes.md").write_text("clean\n", encoding="utf-8")

    names = [path.name for path in iter_source_files(tmp_path)]

    assert names == ["notes.md"]
    assert "SHADOW_CPI_PRD_AND_ARCHITECTURE.md" in DEFAULT_EXCLUDED_FILES


def test_main_returns_zero_for_clean_files(tmp_path: Path, capsys) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("value = 1\n", encoding="utf-8")

    exit_code = main([str(clean)])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_main_reports_offenders_with_code_points(tmp_path: Path, capsys) -> None:
    dirty = tmp_path / "dirty.ts"
    dirty.write_text('export const label = "\u2705";\n', encoding="utf-8")

    exit_code = main([str(dirty)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "U+2705" in output
    assert "Emoji are not allowed" in output


def test_main_ignores_binary_and_excluded_paths(tmp_path: Path) -> None:
    image = tmp_path / "logo.png"
    image.write_bytes(b"\x89PNG")
    requirements_doc = tmp_path / "SHADOW_CPI_PRD_AND_ARCHITECTURE.md"
    requirements_doc.write_text("\u26a0\ufe0f", encoding="utf-8")

    assert main([str(image), str(requirements_doc)]) == 0


def test_repository_sources_contain_no_emoji() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    findings = scan_paths(iter_source_files(repo_root))

    assert findings == {}, f"emoji found in: {sorted(str(path) for path in findings)}"
