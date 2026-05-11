from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from review_web.paragraph_fields import build_paragraph_fields, build_view_mode_buttons, load_paragraph_data
from scripts.repository import BookRepository


BASE_DIR = Path(__file__).resolve().parent
REPOSITORY = BookRepository(BASE_DIR.parent)
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
LAST_PARAGRAPH_PATH = BASE_DIR / "last_saved_paragraph.json"

app = FastAPI(title="PtAlternative Review")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
logger = logging.getLogger("uvicorn.error")


def debug_log(message: str):
    print(message, flush=True)
    logger.info(message)


@app.on_event("startup")
def startup_trace():
    debug_log("[startup] review_web.main loaded and startup completed")


STATUS_LABELS = [
    (0, "Started"),
    (1, "Working"),
    (2, "Doubt"),
    (3, "Ok"),
    (4, "Closed"),
]

STATUS_LABEL_MAP = {str(status): label for status, label in STATUS_LABELS}

PARAGRAPH_FILENAME_PATTERN = re.compile(r"Par_(\d{3})_(\d{3})_(\d{3})\.md$")


def status_label_lines(status_counts: dict[str, int]):
    return [
        {
            "label": label,
            "value": status_counts.get(str(status), 0),
        }
        for status, label in STATUS_LABELS
    ]


def paragraph_status_label(repository: BookRepository, document_dir, paper: int, section: int, paragraph: int) -> str:
    """Returns the status label for the given paragraph from Notes.json, when available."""
    notes = repository.load_notes(document_dir)
    for note in reversed(notes):
        if (
            int(note.get("Paper", -1)) == paper
            and int(note.get("Section", -1)) == section
            and int(note.get("Paragraph", -1)) == paragraph
        ):
            return STATUS_LABEL_MAP.get(str(note.get("Status", "")), str(note.get("Status", "-")))

    return "-"


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


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


@app.get("/", response_class=HTMLResponse)
def home(request: Request, ref: str | None = None):
    debug_log(f"[home] start ref={ref!r}")
    if not ref:
        last_paragraph = load_last_saved_paragraph()
        if last_paragraph is not None:
            paper, section, paragraph = last_paragraph
            debug_log(f"[home] redirecting to last paragraph {paper}/{section}/{paragraph}")
            return RedirectResponse(url=f"/paragraph/{paper}/{section}/{paragraph}", status_code=303)

    debug_log("[home] calling dashboard")
    return dashboard(request, ref)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, ref: str | None = None):
    debug_log(f"[dashboard] start ref={ref!r}")
    summaries = REPOSITORY.summarize_documents()
    debug_log(f"[dashboard] summaries_loaded={len(summaries)}")
    reference_input = (ref or "").strip()
    reference_error = ""

    if reference_input:
        parsed_reference = parse_paragraph_reference(reference_input)
        if parsed_reference is not None:
            paper, section, paragraph = parsed_reference
            debug_log(f"[dashboard] redirecting to paragraph {paper}/{section}/{paragraph}")
            return RedirectResponse(url=f"/paragraph/{paper}/{section}/{paragraph}", status_code=303)
        reference_error = "Use exatamente 3 inteiros no formato D.S-P, separados por espaço, . , - ou : (ex.: 9.0-12)."

    total_documents = len(REPOSITORY.summarize_documents())
    total_paragraphs = sum(item["paragraph_count"] for item in REPOSITORY.summarize_documents())

    return TEMPLATES.TemplateResponse(
        request,
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
    debug_log(f"[paragraph_view] start paper={paper} section={section} paragraph={paragraph} saved={saved}")
    context = load_paragraph_data(REPOSITORY, paper, section, paragraph)
    debug_log("[paragraph_view] load_paragraph_data done")
    fields = build_paragraph_fields(context["english"], context["portuguese_text"])
    debug_log("[paragraph_view] build_paragraph_fields done")
    view_mode_buttons = build_view_mode_buttons(paper, section, paragraph)
    debug_log("[paragraph_view] build_view_mode_buttons done")
    paragraph_status = paragraph_status_label(REPOSITORY, context["document_dir"], paper, section, paragraph)
    debug_log(f"[paragraph_view] paragraph_status={paragraph_status}")

    debug_log("[paragraph_view] rendering TemplateResponse")
    return TEMPLATES.TemplateResponse(
        request,
        "paragraph.html",
        {
            "request": request,
            "paper": paper,
            "section": section,
            "paragraph": paragraph,
            **fields,
            "portuguese_path": context["portuguese_path"],
            "document_dir": context["document_dir"],
            "document_summary": context["document_summary"],
            "previous_link": context["previous_link"],
            "next_link": context["next_link"],
            "view_mode_buttons": view_mode_buttons,
            "paragraph_status": paragraph_status,
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
    debug_log(f"[paragraph_submit] start paper={paper} section={section} paragraph={paragraph}")
    body = (await request.body()).decode("utf-8", errors="replace")
    debug_log(f"[paragraph_submit] body_length={len(body)}")
    form_data = parse_qs(body)
    proposed_text = form_data.get("proposed_text", [""])[0]
    action = form_data.get("action", ["preview"])[0]
    debug_log(f"[paragraph_submit] action={action} proposed_length={len(proposed_text)}")

    debug_log("[paragraph_submit] loading paragraph data")
    context = load_paragraph_data(REPOSITORY, paper, section, paragraph)
    current_text = context["portuguese_text"]

    if action == "save":
        debug_log("[paragraph_submit] saving paragraph")
        REPOSITORY.save_portuguese_paragraph(paper, section, paragraph, proposed_text.strip())
        save_last_saved_paragraph(paper, section, paragraph)
        debug_log("[paragraph_submit] reload paragraph data after save")
        context = load_paragraph_data(REPOSITORY, paper, section, paragraph)
        current_text = context["portuguese_text"]

    debug_log("[paragraph_submit] building fields")
    fields = build_paragraph_fields(context["english"], current_text, proposed_text)
    debug_log("[paragraph_submit] fields built")
    view_mode_buttons = build_view_mode_buttons(paper, section, paragraph)
    debug_log("[paragraph_submit] buttons built")
    paragraph_status = paragraph_status_label(REPOSITORY, context["document_dir"], paper, section, paragraph)
    note_summary = REPOSITORY.summarize_notes(REPOSITORY.load_notes(context["document_dir"]))
    debug_log(f"[paragraph_submit] paragraph_status={paragraph_status} notes={note_summary.get('count', 0)}")

    debug_log("[paragraph_submit] rendering TemplateResponse")
    return TEMPLATES.TemplateResponse(
        request,
        "paragraph.html",
        {
            "request": request,
            "paper": paper,
            "section": section,
            "paragraph": paragraph,
            **fields,
            "portuguese_path": context["portuguese_path"],
            "document_dir": context["document_dir"],
            "document_summary": context["document_summary"],
            "previous_link": context["previous_link"],
            "next_link": context["next_link"],
            "view_mode_buttons": view_mode_buttons,
            "paragraph_status": paragraph_status,
            "saved": action == "save",
            "status_lines": status_label_lines(note_summary.get("status_counts", {})),
        },
    )


@app.middleware("http")
async def request_trace_middleware(request: Request, call_next):
    debug_log(f"[http] --> {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        debug_log(f"[http] <-- {request.method} {request.url.path} {response.status_code}")
        return response
    except Exception as exc:
        debug_log(f"[http] !! {request.method} {request.url.path} {type(exc).__name__}: {exc}")
        raise
