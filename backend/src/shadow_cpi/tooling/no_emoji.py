"""Finds emoji characters in the codebase.

Added to make sure AI-written code does not use emoji characters.

This project writes status text such as ``[WARNING]``, ``[AUTO-HEALING]``, and
``[RESOLVED]`` instead of emoji, and uses named icon components in the user
interface instead of emoji glyphs. Plain text labels are searchable, readable in
log aggregators and terminals, and screen readers announce them predictably.

No single linter can enforce that across Python, TypeScript, and Markdown at
once, so this module provides one detector that the pre-commit hook, the CI
pipeline, and a unit test all share.

The product requirements document is skipped: it is an external input file whose
original wording is preserved as received.

Run it directly to check files:

    python backend/src/shadow_cpi/tooling/no_emoji.py            # whole repository
    python backend/src/shadow_cpi/tooling/no_emoji.py file.py    # specific files

The exit code is 0 when clean and 1 when at least one emoji was found, so it can
be used directly as a build step.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

# Unicode blocks that contain emoji, pictographs, dingbats, and the invisible
# "render this as emoji" modifier. Accented letters (Cafe, naive) and
# box-drawing characters sit outside these ranges and are therefore allowed.
_EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x2190, 0x21FF),  # arrows, which some platforms render as emoji
    (0x2300, 0x23FF),  # watch, hourglass, media control symbols
    (0x2460, 0x24FF),  # enclosed numbers used as emoji
    (0x25A0, 0x27BF),  # geometric shapes, miscellaneous symbols, dingbats
    (0x2900, 0x297F),  # supplemental arrows
    (0x2B00, 0x2BFF),  # extra arrows and stars
    (0xFE00, 0xFE0F),  # variation selectors, the emoji-style modifier
    (0x1F000, 0x1FAFF),  # the main emoji and pictograph blocks
)

# Text-based file types worth scanning. Anything else is treated as binary.
_SCANNED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".json",
        ".md",
        ".yml",
        ".yaml",
        ".toml",
        ".css",
        ".sql",
        ".cypher",
        ".sh",
        ".html",
    }
)

# Directories that contain third-party or generated code we do not control.
_EXCLUDED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        "out",
        "storybook-static",
        "coverage",
        "htmlcov",
        "designs",
    }
)

DEFAULT_EXCLUDED_FILES: frozenset[str] = frozenset({"SHADOW_CPI_PRD_AND_ARCHITECTURE.md"})


@dataclass(frozen=True, slots=True)
class EmojiHit:
    """One emoji character found in a file.

    Attributes:
        line: Line number, counting from 1.
        column: Column number, counting from 1.
        character: The character itself.
    """

    line: int
    column: int
    character: str


def _is_emoji(character: str) -> bool:
    code_point = ord(character)
    return any(start <= code_point <= end for start, end in _EMOJI_RANGES)


def find_emoji(text: str) -> tuple[EmojiHit, ...]:
    """Find every emoji character in a piece of text.

    Args:
        text: Text to inspect. An empty string is valid and returns no hits.

    Returns:
        Hits in reading order, with line and column positions. Empty when the
        text contains no emoji.

    Example:
        >>> find_emoji("all clear")
        ()
        >>> len(find_emoji(chr(0x2705) + " done"))
        1
    """
    hits: list[EmojiHit] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for column, character in enumerate(line, start=1):
            if _is_emoji(character):
                hits.append(EmojiHit(line=line_number, column=column, character=character))
    return tuple(hits)


def iter_source_files(
    root: Path,
    excluded_files: Iterable[str] = DEFAULT_EXCLUDED_FILES,
) -> Iterator[Path]:
    """Yield the text files under a directory that this check applies to.

    Args:
        root: Directory to walk.
        excluded_files: File names to skip wherever they appear.

    Yields:
        Paths to text files, skipping binaries, dependency folders, and build
        output.
    """
    skipped = frozenset(excluded_files)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SCANNED_SUFFIXES:
            continue
        if path.name in skipped:
            continue
        if any(part in _EXCLUDED_DIRECTORIES for part in path.relative_to(root).parts[:-1]):
            continue
        yield path


def scan_paths(paths: Iterable[Path]) -> dict[Path, tuple[EmojiHit, ...]]:
    """Scan files and return only the ones containing emoji.

    Args:
        paths: Files to scan.

    Returns:
        A mapping of file to the emoji found in it. An empty mapping means
        everything scanned is clean.
    """
    findings: dict[Path, tuple[EmojiHit, ...]] = {}
    for path in paths:
        hits = find_emoji(path.read_text(encoding="utf-8", errors="replace"))
        if hits:
            findings[path] = hits
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the check from the command line.

    Args:
        argv: File paths to check. When empty, the whole repository is scanned.

    Returns:
        0 when no emoji were found, 1 otherwise.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        candidates: Iterable[Path] = [Path(argument) for argument in arguments]
        candidates = [path for path in candidates if path.suffix.lower() in _SCANNED_SUFFIXES]
        candidates = [path for path in candidates if path.name not in DEFAULT_EXCLUDED_FILES]
    else:
        # This file lives at backend/src/shadow_cpi/tooling/no_emoji.py, so four
        # levels up from its directory is the repository root.
        candidates = iter_source_files(Path(__file__).resolve().parents[4])

    findings = scan_paths(candidates)
    for path, hits in findings.items():
        for hit in hits:
            code_point = f"U+{ord(hit.character):04X}"
            sys.stdout.write(f"{path}:{hit.line}:{hit.column}: disallowed emoji {code_point}\n")
    if findings:
        sys.stdout.write("Emoji are not allowed in this repository; use text labels instead\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
