from __future__ import annotations

import difflib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.repository import BookRepository


BASE_DIR = Path(__file__).resolve().parent
REPOSITORY = BookRepository(BASE_DIR.parent)
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
LAST_PARAGRAPH_PATH = BASE_DIR / "last_saved_paragraph.json"

app = FastAPI(title="PtAlternative Review")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


STATUS_LABELS = [
    (0, "Started"),
    (1, "Working"),
    (2, "Doubt"),
    (3, "Ok"),
    (4, "Closed"),
]

PARAGRAPH_FILENAME_PATTERN = re.compile(r"Par_(\d{3})_(\d{3})_(\d{3})\.md$")


@dataclass(frozen=True)
class ParagraphLink:
    paper: int
    section: int
    paragraph: int
    title: str

    @property
    def href(self) -> str:
        return f"/paragraph/{self.paper}/{self.section}/{self.paragraph}"


def status_label_lines(status_counts: dict[str, int]):
    return [
        {
            "label": label,
            "value": status_counts.get(str(status), 0),
        }
        for status, label in STATUS_LABELS
    ]


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def split_tokens(text: str):
    return re.split(r"(\s+)", text)


def merge_preview_html(base_text: str, proposed_text: str) -> str:
    base_tokens = split_tokens(base_text)
    proposed_tokens = split_tokens(proposed_text)
    matcher = difflib.SequenceMatcher(None, base_tokens, proposed_tokens)

    chunks: list[str] = []
    for tag, start_base, end_base, start_new, end_new in matcher.get_opcodes():
        base_chunk = html.escape("".join(base_tokens[start_base:end_base]))
        new_chunk = html.escape("".join(proposed_tokens[start_new:end_new]))

        if tag == "equal":
            chunks.append(f"<span class=\"merge-equal\">{base_chunk}</span>")
        elif tag == "delete":
            chunks.append(f"<del class=\"merge-delete\">{base_chunk}</del>")
        elif tag == "insert":
            chunks.append(f"<ins class=\"merge-insert\">{new_chunk}</ins>")
        else:
            chunks.append(f"<del class=\"merge-delete\">{base_chunk}</del><ins class=\"merge-insert\">{new_chunk}</ins>")

    return "".join(chunks) or "<span class=\"merge-empty\">Sem alterações.</span>"


def paragraph_target(paper: int, section: int, paragraph: int):
    return paper, section, paragraph


def load_last_saved_paragraph() -> tuple[int, int, int] | None:
    if not LAST_PARAGRAPH_PATH.exists():
        return None

    try:
        payload = json.loads(LAST_PARAGRAPH_PATH.read_text(encoding="utf-8"))
        paper = int(payload["paper"])
        section = int(payload["section"])
        paragraph = int(payload["paragraph"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None

    return paper, section, paragraph


def save_last_saved_paragraph(paper: int, section: int, paragraph: int):
    payload = {"paper": paper, "section": section, "paragraph": paragraph}
    LAST_PARAGRAPH_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def parse_paragraph_reference(value: str) -> tuple[int, int, int] | None:
    # Accept exactly three integers with separators: whitespace, dot, comma, dash, or colon.
    pattern = re.compile(r"^\s*(\d+)\s*(?:\s+|[.,\-:])\s*(\d+)\s*(?:\s+|[.,\-:])\s*(\d+)\s*$")
    match = pattern.fullmatch(value)
    if match is None:
        return None

    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def load_paragraph_data(paper: int, section: int, paragraph: int):
    english = REPOSITORY.get_english_paragraph(paper, section, paragraph)
    if english is None:
        raise HTTPException(status_code=404, detail="Parágrafo em inglês não encontrado.")

    document_dir = REPOSITORY.get_document_dir(paper)
    if document_dir is None:
        raise HTTPException(status_code=404, detail="Documento português não encontrado.")

    portuguese_path = REPOSITORY.get_portuguese_paragraph_path(paper, section, paragraph)
    portuguese_text = REPOSITORY.load_portuguese_paragraph(paper, section, paragraph)
    document_summary = REPOSITORY.get_document_summary(paper) or {}
    paragraph_files = REPOSITORY.list_paragraph_files(document_dir)

    ordered_links: list[ParagraphLink] = []
    current_index = None
    for index, paragraph_file in enumerate(paragraph_files):
        match = PARAGRAPH_FILENAME_PATTERN.fullmatch(paragraph_file.name)
        if match is None:
            continue

        link = ParagraphLink(
            paper=int(match.group(1)),
            section=int(match.group(2)),
            paragraph=int(match.group(3)),
            title=paragraph_file.stem,
        )
        ordered_links.append(link)
        if link.paper == paper and link.section == section and link.paragraph == paragraph:
            current_index = index

    previous_link = ordered_links[current_index - 1] if current_index is not None and current_index > 0 else None
    next_link = (
        ordered_links[current_index + 1]
        if current_index is not None and current_index + 1 < len(ordered_links)
        else None
    )

    return {
        "english": english,
        "portuguese_text": portuguese_text,
        "portuguese_path": portuguese_path,
        "document_dir": document_dir,
        "document_summary": document_summary,
        "previous_link": previous_link,
        "next_link": next_link,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request, ref: str | None = None):
    if not ref:
        last_paragraph = load_last_saved_paragraph()
        if last_paragraph is not None:
            paper, section, paragraph = last_paragraph
            return RedirectResponse(url=f"/paragraph/{paper}/{section}/{paragraph}", status_code=303)

    return dashboard(request, ref)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, ref: str | None = None):
    summaries = REPOSITORY.summarize_documents()
    reference_input = (ref or "").strip()
    reference_error = ""

    if reference_input:
        parsed_reference = parse_paragraph_reference(reference_input)
        if parsed_reference is not None:
            paper, section, paragraph = parsed_reference
            return RedirectResponse(url=f"/paragraph/{paper}/{section}/{paragraph}", status_code=303)
        reference_error = "Use exatamente 3 inteiros no formato D.S-P, separados por espaço, . , - ou : (ex.: 9.0-12)."

    total_documents = len(REPOSITORY.summarize_documents())
    total_paragraphs = sum(item["paragraph_count"] for item in REPOSITORY.summarize_documents())

    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "documents": summaries,
            "reference_input": reference_input,
            "reference_error": reference_error,
            "total_documents": total_documents,
            "total_paragraphs": total_paragraphs,
            "documents_with_notes": sum(1 for item in summaries if item["notes_present"]),
        },
    )


@app.get("/doc/{paper}")
def open_document(paper: int):
    return RedirectResponse(url=f"/paragraph/{paper}/0/0", status_code=303)


@app.get("/paragraph/{paper}/{section}/{paragraph}", response_class=HTMLResponse)
def paragraph_view(request: Request, paper: int, section: int, paragraph: int, saved: str | None = None):
    context = load_paragraph_data(paper, section, paragraph)
    proposal = context["portuguese_text"]
    merge_html = merge_preview_html(context["portuguese_text"], proposal)

    return TEMPLATES.TemplateResponse(
        "paragraph.html",
        {
            "request": request,
            "paper": paper,
            "section": section,
            "paragraph": paragraph,
            "english": context["english"],
            "portuguese_text": context["portuguese_text"],
            "proposal": proposal,
            "merge_html": merge_html,
            "portuguese_path": context["portuguese_path"],
            "document_dir": context["document_dir"],
            "document_summary": context["document_summary"],
            "previous_link": context["previous_link"],
            "next_link": context["next_link"],
            "saved": saved == "1",
            "status_lines": status_label_lines(REPOSITORY.summarize_notes(REPOSITORY.load_notes(context["document_dir"])).get("status_counts", {})),
        },
    )


@app.post("/paragraph/{paper}/{section}/{paragraph}", response_class=HTMLResponse)
async def paragraph_submit(
    request: Request,
    paper: int,
    section: int,
    paragraph: int,
):
    body = (await request.body()).decode("utf-8", errors="replace")
    form_data = parse_qs(body)
    proposed_text = form_data.get("proposed_text", [""])[0]
    action = form_data.get("action", ["preview"])[0]

    context = load_paragraph_data(paper, section, paragraph)
    current_text = context["portuguese_text"]
    proposal = proposed_text.strip()

    if action == "save":
        REPOSITORY.save_portuguese_paragraph(paper, section, paragraph, proposal)
        save_last_saved_paragraph(paper, section, paragraph)
        context = load_paragraph_data(paper, section, paragraph)
        current_text = context["portuguese_text"]

    merge_html = merge_preview_html(current_text, proposal)
    note_summary = REPOSITORY.summarize_notes(REPOSITORY.load_notes(context["document_dir"]))

    return TEMPLATES.TemplateResponse(
        "paragraph.html",
        {
            "request": request,
            "paper": paper,
            "section": section,
            "paragraph": paragraph,
            "english": context["english"],
            "portuguese_text": current_text,
            "proposal": proposal,
            "merge_html": merge_html,
            "portuguese_path": context["portuguese_path"],
            "document_dir": context["document_dir"],
            "document_summary": context["document_summary"],
            "previous_link": context["previous_link"],
            "next_link": context["next_link"],
            "saved": action == "save",
            "status_lines": status_label_lines(note_summary.get("status_counts", {})),
        },
    )
