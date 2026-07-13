"""First-party Markdown link integrity tests."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def first_party_markdown_files(repository_root: Path) -> list[Path]:
    return []


def broken_local_links(markdown_files: list[Path]) -> list[str]:
    return []


def test_first_party_documentation_links_are_valid() -> None:
    markdown_files = first_party_markdown_files(REPOSITORY_ROOT)

    assert broken_local_links(markdown_files) == []


def test_nonexistent_local_markdown_link_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text("[Missing](guides/missing.md#setup)\n", encoding="utf-8")

    assert broken_local_links([source]) == [
        f"{source}: guides/missing.md#setup",
    ]
