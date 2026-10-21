"""Đọc dataset golden (`evals/golden/<slug>/`): thông tin sách, nguồn cố định, dữ kiện phải đúng."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from book_review_api.rag.ingest import Document, ingest_text
from book_review_api.rag.memory import to_chunks
from book_review_api.rag.retrieve import Chunk


@dataclass(frozen=True)
class GoldenFact:
    id: str
    fact: str
    # Cụm từ phải xuất hiện trong nguồn của sách: bảo vệ dataset khỏi dữ kiện không có căn cứ.
    needle: str


@dataclass(frozen=True)
class GoldenBook:
    slug: str
    title: str
    author: str
    year: int
    kind: Literal["fiction", "non_fiction"]
    sources: dict[str, str]  # tên file -> văn bản
    facts: list[GoldenFact]

    def documents(self) -> list[Document]:
        docs: list[Document] = []
        for name, text in self.sources.items():
            docs += ingest_text(
                text,
                url=f"golden://{self.slug}/{name}",
                title=name,
                book_id=self.slug,
                source_id=f"{self.slug}/{name}",
            )
        return docs

    def chunks(self) -> list[Chunk]:
        return to_chunks(self.documents())


def load_golden_book(directory: Path) -> GoldenBook:
    info = json.loads((directory / "book.json").read_text(encoding="utf-8"))
    sources = {
        p.name: p.read_text(encoding="utf-8") for p in sorted((directory / "sources").glob("*.txt"))
    }
    facts = [
        GoldenFact(str(f["id"]), f["fact"], f["needle"])
        for f in json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    ]
    return GoldenBook(
        slug=directory.name,
        title=info["title"],
        author=info["author"],
        year=int(info["year"]),
        kind=info["kind"],
        sources=sources,
        facts=facts,
    )


def load_golden(root: Path) -> list[GoldenBook]:
    return [load_golden_book(d) for d in sorted(root.iterdir()) if (d / "book.json").is_file()]
