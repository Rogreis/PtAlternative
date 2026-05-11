from __future__ import annotations

import argparse
from pathlib import Path

from repository import BookRepository


STATUS_LABELS = [
    (0, "Started"),
    (1, "Working"),
    (2, "Doubt"),
    (3, "Ok"),
    (4, "Closed"),
]


def format_counter(counter):
    if not counter:
        return "-"

    return ", ".join(f"{key}:{value}" for key, value in counter.items())


def format_status_counts(status_counts):
    if not status_counts:
        return "-"

    return "<br>".join(
        f"{label} = {status_counts.get(str(status), 0)}"
        for status, label in STATUS_LABELS
    )


def print_summary(repository: BookRepository):
    summaries = repository.summarize_documents()
    total_documents = len(summaries)
    total_paragraphs = sum(item["paragraph_count"] for item in summaries)
    documents_with_notes = sum(1 for item in summaries if item["notes_present"])
    documents_without_notes = total_documents - documents_with_notes
    documents_with_duplicates = sum(1 for item in summaries if item["duplicate_notes"] > 0)

    print("Review dashboard")
    print(f"Repository: {repository.repo_root}")
    print(f"Documents: {total_documents}")
    print(f"Paragraph files: {total_paragraphs}")
    print(f"Documents with Notes.json: {documents_with_notes}")
    print(f"Documents without Notes.json: {documents_without_notes}")
    print(f"Documents with duplicated note entries: {documents_with_duplicates}")
    print()
    print("First documents:")

    for summary in summaries[:10]:
        title = summary["title"] or "(no title found)"
        print(
            f"  Doc{summary['document_number']:03d} | {title} | "
            f"paragraphs={summary['paragraph_count']} | notes={summary['notes_count']}"
        )


def print_document_details(repository: BookRepository, document_number: int):
    summary = repository.get_document_summary(document_number)
    if summary is None:
        raise SystemExit(f"Document Doc{document_number:03d} was not found.")

    document_dir = repository.repo_root / summary["document_name"]
    paragraph_files = repository.list_paragraph_files(document_dir)
    notes = repository.load_notes(document_dir)
    note_summary = repository.summarize_notes(notes)

    print(f"Document Doc{document_number:03d}")
    print(f"Title: {summary['title'] or '(no title found)'}")
    print(f"Directory: {document_dir}")
    print(f"Paragraph files: {summary['paragraph_count']}")
    print(f"First paragraph: {summary['first_paragraph'] or '-'}")
    print(f"Last paragraph: {summary['last_paragraph'] or '-'}")
    print(f"Notes entries: {note_summary['count']}")
    print(f"Unique note targets: {note_summary['unique_targets']}")
    print(f"Duplicated note entries: {note_summary['duplicate_notes']}")
    print(f"Status counts: {format_status_counts(note_summary['status_counts'])}")
    print(f"Format counts: {format_counter(note_summary['format_counts'])}")
    print()
    print("Paragraph files:")

    for path in paragraph_files[:20]:
        print(f"  {path.name}")

    if len(paragraph_files) > 20:
        print(f"  ... ({len(paragraph_files) - 20} more)")


def build_report(repository: BookRepository):
    summaries = repository.summarize_documents()
    lines = [
        "# Review dashboard",
        "",
        f"Generated from `{repository.repo_root}`.",
        "",
        "## Overview",
        f"- Documents: {len(summaries)}",
        f"- Paragraph files: {sum(item['paragraph_count'] for item in summaries)}",
        f"- Documents with Notes.json: {sum(1 for item in summaries if item['notes_present'])}",
        f"- Documents without Notes.json: {sum(1 for item in summaries if not item['notes_present'])}",
        f"- Documents with duplicated note entries: {sum(1 for item in summaries if item['duplicate_notes'] > 0)}",
        "",
        "## Documents",
        "| Doc | Title | Paragraphs | Notes | Duplicate notes | Status counts | Format counts |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]

    for summary in summaries:
        title = summary["title"].replace("|", "\\|") if summary["title"] else ""
        lines.append(
            "| "
            f"Doc{summary['document_number']:03d} | "
            f"{title} | "
            f"{summary['paragraph_count']} | "
            f"{summary['notes_count']} | "
            f"{summary['duplicate_notes']} | "
            f"{format_status_counts(summary['status_counts'])} | "
            f"{format_counter(summary['format_counts'])} |"
        )

    return "\n".join(lines) + "\n"


def write_report(repository: BookRepository, output_path: Path):
    report = build_report(repository)
    output_path.write_text(report, encoding="utf-8")
    print(f"Report written to {output_path}")


def build_parser():
    parser = argparse.ArgumentParser(description="Review helper for the PtAlternative repository")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("summary", help="Show a repository overview")

    document_parser = subparsers.add_parser("doc", help="Show details for one document")
    document_parser.add_argument("document_number", type=int, help="Document number, for example 0 or 42")

    report_parser = subparsers.add_parser("report", help="Write a markdown report")
    report_parser.add_argument(
        "-o",
        "--output",
        default="review_dashboard.md",
        help="Output file path relative to the repository root",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    repository = BookRepository()

    if args.command in (None, "summary"):
        print_summary(repository)
        return

    if args.command == "doc":
        print_document_details(repository, args.document_number)
        return

    if args.command == "report":
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = repository.repo_root / output_path
        write_report(repository, output_path)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
