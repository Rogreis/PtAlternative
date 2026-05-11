from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path


DOC_PATTERN = re.compile(r"Doc(\d{3})$")


@lru_cache(maxsize=1)
def _load_tr000_index(repo_root_str: str):
    repo_root = Path(repo_root_str)
    tr000_path = repo_root / "TR000.json"
    with tr000_path.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    paragraphs = {}
    for paper_entry in data.get("Papers", []):
        for paragraph in paper_entry.get("Paragraphs", []):
            key = (
                int(paragraph.get("Paper", -1)),
                int(paragraph.get("Section", -1)),
                int(paragraph.get("ParagraphNo", -1)),
            )
            paragraphs[key] = paragraph

    return data, paragraphs


class BookRepository:
    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parent.parent
        self.index_path = self.repo_root / "index.json"
        self.toc_path = self.repo_root / "TOC_Table.json"

    def load_json(self, path: Path):
        with path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle)

    def get_document_dir(self, document_number: int):
        document_dir = self.repo_root / f"Doc{document_number:03d}"
        return document_dir if document_dir.exists() else None

    def list_document_directories(self):
        documents = []
        for path in self.repo_root.iterdir():
            if not path.is_dir():
                continue

            match = DOC_PATTERN.fullmatch(path.name)
            if match is None:
                continue

            documents.append((int(match.group(1)), path))

        documents.sort(key=lambda item: item[0])
        return documents

    def list_paragraph_files(self, document_dir: Path):
        return sorted(
            [path for path in document_dir.glob("Par_*.md") if path.is_file()],
            key=lambda path: path.name,
        )

    def load_notes(self, document_dir: Path):
        notes_path = document_dir / "Notes.json"
        if not notes_path.exists():
            return []

        data = self.load_json(notes_path)
        return data.get("Notes", [])

    def get_document_title(self, document_dir: Path):
        paragraph_files = self.list_paragraph_files(document_dir)
        if not paragraph_files:
            return ""

        first_lines = paragraph_files[0].read_text(encoding="utf-8").splitlines()
        return first_lines[0].lstrip("\ufeff").strip() if first_lines else ""

    def get_english_paragraph(self, paper: int, section: int, paragraph_number: int):
        _, paragraphs = _load_tr000_index(str(self.repo_root))
        return paragraphs.get((paper, section, paragraph_number))

    def get_portuguese_paragraph_path(self, paper: int, section: int, paragraph_number: int):
        return self.repo_root / f"Doc{paper:03d}" / f"Par_{paper:03d}_{section:03d}_{paragraph_number:03d}.md"

    def load_portuguese_paragraph(self, paper: int, section: int, paragraph_number: int):
        paragraph_path = self.get_portuguese_paragraph_path(paper, section, paragraph_number)
        if not paragraph_path.exists():
            return ""

        return paragraph_path.read_text(encoding="utf-8").strip()

    def save_portuguese_paragraph(self, paper: int, section: int, paragraph_number: int, text: str):
        paragraph_path = self.get_portuguese_paragraph_path(paper, section, paragraph_number)
        paragraph_path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return paragraph_path

    def summarize_notes(self, notes):
        status_counter = Counter()
        format_counter = Counter()
        note_keys = Counter()

        for note in notes:
            status_counter[str(note.get("Status", "?"))] += 1
            format_counter[str(note.get("Format", "?"))] += 1
            note_key = (
                note.get("Paper"),
                note.get("Section"),
                note.get("Paragraph"),
                note.get("Status"),
                note.get("Format"),
            )
            note_keys[note_key] += 1

        duplicate_notes = sum(count - 1 for count in note_keys.values() if count > 1)
        unique_targets = len(note_keys)

        return {
            "count": len(notes),
            "unique_targets": unique_targets,
            "duplicate_notes": duplicate_notes,
            "status_counts": dict(sorted(status_counter.items())),
            "format_counts": dict(sorted(format_counter.items())),
        }

    def summarize_documents(self):
        summaries = []
        for document_number, document_dir in self.list_document_directories():
            paragraph_files = self.list_paragraph_files(document_dir)
            notes = self.load_notes(document_dir)
            note_summary = self.summarize_notes(notes)

            summaries.append(
                {
                    "document_number": document_number,
                    "document_name": document_dir.name,
                    "title": self.get_document_title(document_dir),
                    "paragraph_count": len(paragraph_files),
                    "first_paragraph": paragraph_files[0].name if paragraph_files else "",
                    "last_paragraph": paragraph_files[-1].name if paragraph_files else "",
                    "notes_present": bool(notes),
                    "notes_count": note_summary["count"],
                    "unique_note_targets": note_summary["unique_targets"],
                    "duplicate_notes": note_summary["duplicate_notes"],
                    "status_counts": note_summary["status_counts"],
                    "format_counts": note_summary["format_counts"],
                }
            )

        return summaries

    def get_document_summary(self, document_number: int):
        for summary in self.summarize_documents():
            if summary["document_number"] == document_number:
                return summary
        return None
