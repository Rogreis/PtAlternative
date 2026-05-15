from __future__ import annotations

import difflib
import html
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from scripts.repository import BookRepository
from .ai_helper import AIHelper
from .log import debug_log


PARAGRAPH_FILENAME_PATTERN = re.compile(r"Par_(\d{3})_(\d{3})_(\d{3})\.md$")


@dataclass(frozen=True)
class ParagraphLink:
    """Represents a navigable paragraph reference for previous/next links."""

    paper: int
    section: int
    paragraph: int
    title: str

    @property
    def href(self) -> str:
        """Returns the route path to open this paragraph in the review screen."""
        return f"/paragraph/{self.paper}/{self.section}/{self.paragraph}"


def split_tokens(text: str):
    """Splits text preserving whitespace chunks for token-based diff rendering."""
    return re.split(r"(\s+)", text)


def extract_english_text(english_paragraph) -> str:
    """Extracts only the paragraph Text field expected by the translation pipeline."""
    if isinstance(english_paragraph, dict):
        return str(english_paragraph.get("Text", "") or "")
    return str(english_paragraph or "")


def merge_preview_html(base_text: str, proposed_text: str) -> str:
    """Builds HTML markup highlighting differences between current and proposed text."""
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



def translate(english_paragraph) -> dict[str, str]:
    """Calls translate_urantia_paragraph and returns translation plus optional comments."""
    debug_log(f"[translate] start type={type(english_paragraph).__name__}")
    english_text = extract_english_text(english_paragraph)
    debug_log(f"[translate] english_length={len(english_text)}")
    if not english_text.strip():
        debug_log("[translate] empty_english_text")
        return {"translation": "", "comments": "Texto em ingles vazio."}

    result = AIHelper.translate_urantia_paragraph(english_text)
    debug_log(f"[translate] result_keys={list(result.keys())}")
    
    # Handle error responses
    if "error" in result:
        debug_log(f"[translate] ai_error={result.get('error', '')}")
        return {"translation": "", "comments": result.get("error", "Erro na tradução.")}
    
    return {
        "translation": result.get("translation", ""),
        "comments": result.get("comments", "")
    }


def generate_corrected_translation_from_ai(english) -> str:
    """Generates a short AI explanation by invoking the external WSL helper script."""
    english_text = extract_english_text(english)
    if not english_text.strip():
        return ""

    result = AIHelper.translate_urantia_paragraph(english_text)
    if result.get("error"):
        debug_log(f"[generate_corrected_translation_from_ai] translate_error={result['error']}")
        return ""

    return result.get("translation", "")


def build_current_button(paper: int, section: int, paragraph: int):
    """Builds metadata for the button that points to the current Portuguese text panel."""
    return {
        "label": "Atual",
        "tooltip": "Texto atual da trdução",
        "mode": "current",
        "variant": "current",
        "href": f"/paragraph/{paper}/{section}/{paragraph}#panel-current",
    }


def build_proposed_button(paper: int, section: int, paragraph: int):
    """Builds metadata for the button that points to the proposed translation panel."""
    return {
        "label": "Proposto",
        "tooltip": "Tradução Proposta",
        "mode": "proposed",
        "variant": "proposed",
        "href": f"/paragraph/{paper}/{section}/{paragraph}#panel-proposed",
    }


def build_merge_button(paper: int, section: int, paragraph: int):
    """Builds metadata for the button that points to the merge/diff panel."""
    return {
        "label": "Merge",
        "tooltip": "Alterações",
        "mode": "merge",
        "variant": "merge",
        "href": f"/paragraph/{paper}/{section}/{paragraph}#panel-current",
    }


def build_comments_button(paper: int, section: int, paragraph: int):
    """Builds metadata for the button that points to AI comments view."""
    return {
        "label": "Comments",
        "tooltip": "Comentários da IA",
        "mode": "comments",
        "variant": "comments",
        "href": f"/paragraph/{paper}/{section}/{paragraph}#panel-current",
    }


def build_view_mode_buttons(paper: int, section: int, paragraph: int):
    """Returns the set of panel shortcut buttons shown in the paragraph review screen."""
    return [
        build_current_button(paper, section, paragraph),
        build_proposed_button(paper, section, paragraph),
        build_merge_button(paper, section, paragraph),
        build_comments_button(paper, section, paragraph),
    ]


def load_paragraph_data(repository: BookRepository, paper: int, section: int, paragraph: int):
    """Loads English/Portuguese paragraph data and computes previous/next navigation links."""
    english = repository.get_english_paragraph(paper, section, paragraph)
    if english is None:
        raise HTTPException(status_code=404, detail="Parágrafo em inglês não encontrado.")

    document_dir = repository.get_document_dir(paper)
    if document_dir is None:
        raise HTTPException(status_code=404, detail="Documento português não encontrado.")

    portuguese_path = repository.get_portuguese_paragraph_path(paper, section, paragraph)
    portuguese_text = repository.load_portuguese_paragraph(paper, section, paragraph)
    document_notes = repository.load_notes(document_dir)
    document_summary = {"notes_count": len(document_notes)}
    paragraph_files = repository.list_paragraph_files(document_dir)

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


def build_paragraph_fields(english, portuguese_text: str, proposed_text: str | None = None):
    """Returns template-ready field values for English text, Portuguese text, proposal and merge preview."""
    english_text = extract_english_text(english)
    debug_log(f"[build_paragraph_fields] english_length={len(english_text)}")
    proposal = portuguese_text if proposed_text is None else proposed_text.strip()

    return {
        "english": english,
        "portuguese_text": portuguese_text,
        "proposal": proposal,
        "ai_proposal": "",
        "ai_comments": "",
        "merge_html": merge_preview_html(portuguese_text, proposal),
    }
