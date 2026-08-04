"""First-party Markdown link integrity tests."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IGNORED_DIRECTORY_NAMES = {
    ".venv",
    "__pycache__",
    "node_modules",
    "site-packages",
    "vendor",
}
INLINE_LINK_PATTERN = re.compile(r"!?\[[^\]\n]*\]\((?P<target><[^>\n]+>|[^)\n]+)\)")
REFERENCE_LINK_PATTERN = re.compile(
    r"^\s{0,3}\[[^\]\n]+\]:\s*(?P<target><[^>\n]+>|\S+)",
    re.MULTILINE,
)


def first_party_markdown_files(repository_root: Path) -> list[Path]:
    explicit_files = [
        repository_root / "README.md",
        repository_root / "AGENTS.md",
        repository_root / "scripts/README.md",
        repository_root / "tools/README.md",
        repository_root / "Emotion-LLaMA/README.md",
        repository_root / "R1-Omni/README.md",
    ]
    discovered_files = list((repository_root / "docs").rglob("*.md"))
    discovered_files.extend((repository_root / "UI_API").rglob("README.md"))

    return sorted(
        {
            path
            for path in [*explicit_files, *discovered_files]
            if path.is_file() and not IGNORED_DIRECTORY_NAMES.intersection(path.parts)
        }
    )


def markdown_link_targets(markdown: str) -> list[str]:
    content_without_fences = _remove_fenced_code_blocks(markdown)
    content_without_inline_code = re.sub(r"`[^`\n]*`", "", content_without_fences)
    matches = [
        *INLINE_LINK_PATTERN.finditer(content_without_inline_code),
        *REFERENCE_LINK_PATTERN.finditer(content_without_inline_code),
    ]
    return [_normalize_link_target(match.group("target")) for match in matches]


def _remove_fenced_code_blocks(markdown: str) -> str:
    kept_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    for line in markdown.splitlines(keepends=True):
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None:
            kept_lines.append(line)

    return "".join(kept_lines)


def _normalize_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    else:
        target = target.split(maxsplit=1)[0]
    return unquote(target.replace(r"\ ", " "))


def broken_local_links(markdown_files: list[Path]) -> list[str]:
    broken_links: list[str] = []

    for source in markdown_files:
        markdown = source.read_text(encoding="utf-8")
        for target in markdown_link_targets(markdown):
            normalized_target = target.casefold()
            if (
                not target
                or target.startswith("#")
                or normalized_target.startswith("http://")
                or normalized_target.startswith("https://")
                or normalized_target.startswith("mailto:")
            ):
                continue

            local_path, _, _anchor = target.partition("#")
            if not local_path:
                continue
            if not (source.parent / local_path).resolve().is_file():
                broken_links.append(f"{source}: {target}")

    return sorted(broken_links)


def test_first_party_documentation_links_are_valid() -> None:
    markdown_files = first_party_markdown_files(REPOSITORY_ROOT)

    assert broken_local_links(markdown_files) == []


def test_nonexistent_local_markdown_link_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text("[Missing](guides/missing.md#setup)\n", encoding="utf-8")

    assert broken_local_links([source]) == [
        f"{source}: guides/missing.md#setup",
    ]


def test_external_anchor_and_existing_fragment_links_are_ignored(tmp_path: Path) -> None:
    existing = tmp_path / "guide.md"
    existing.write_text("# Setup\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text(
        "\n".join(
            (
                "[Web](https://example.com/docs)",
                "[Insecure web](http://example.com/docs)",
                "[Email](mailto:owner@example.com)",
                "[Section](#section)",
                "[Guide](guide.md#setup)",
            )
        ),
        encoding="utf-8",
    )

    assert broken_local_links([source]) == []
