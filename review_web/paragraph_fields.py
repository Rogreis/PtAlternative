from __future__ import annotations

import difflib
import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from scripts.repository import BookRepository

import anthropic
import json
SUA_CHAVE_API="os.environ.get("ANTHROPIC_API_KEY", "")"
client = anthropic.Anthropic(api_key=SUA_CHAVE_API)
LOGGER = __import__("logging").getLogger("uvicorn.error")


def debug_log(message: str):
    print(message, flush=True)
    LOGGER.info(message)


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

class AIHelper:
    """Utility helper for AI translation calls used by the review page."""

    @staticmethod
    def _load_api_key() -> str:
        """Loads the API key used by the AI provider from environment variables."""
        key_file_candidates = [
            Path("/y/home/r/.ssh/gemini.key"),
            Path("Y:/home/r/.ssh/gemini.key"),
            Path("\\\\wsl$\\Ubuntu\\home\\r\\.ssh\\gemini.key"),
            Path("\\\\wsl$\\Ubuntu-22.04\\home\\r\\.ssh\\gemini.key"),
        ]

        for key_file in key_file_candidates:
            try:
                if key_file.exists():
                    key_text = key_file.read_text(encoding="utf-8").strip()
                    if key_text:
                        return key_text.splitlines()[0].strip()
            except OSError:
                continue

        return (
            os.getenv("AI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or ""
        ).strip()

    @staticmethod
    def _generate_prompt() -> str:
        """Builds the translation prompt from the English paragraph text."""

        system_instruction = (
            "You are a scholar and expert translator of The Urantia Book. "
            "Your goal is to translate paragraphs from English to Brazilian Portuguese. "
            "Maintain the solemn, philosophical, and elevated tone of the book. "
            "Adhere strictly to the standard Urantia terminology in Portuguese (e.g., 'Thought Adjuster' as 'Ajustador do Pensamento'). "
            "The output must be a valid JSON object with two fields: "
            "'translation' (the translated text) and 'comments' (brief linguistic or terminological notes about the translation)."
        )

        return system_instruction + "\n\n"

    @staticmethod
    def translate_urantia_paragraph(english_text):
        # Makwg the API call to the AI provider using the anthropic client
        debug_log(f"[translate_urantia_paragraph] start english_length={len(str(english_text))}")

        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1500,
                temperature=0, # Essencial para manter a consistência terminológica
                system=AIHelper._generate_prompt(),
                messages=[
                    {
                        "role": "user", 
                        "content": f"Translate this paragraph:\n\n{english_text}"
                    }
                ]
            )
            
            # Faz o parse do JSON retornado pela IA
            debug_log(f"[translate_urantia_paragraph] raw_ai_text={message.content[0].text}")
            response_data = json.loads(message.content[0].text)
            debug_log(f"[translate_urantia_paragraph] parsed_keys={list(response_data.keys())}")
            return response_data
        
        except json.JSONDecodeError:
            debug_log("[translate_urantia_paragraph] invalid_json_response")
            return {"error": "IA não retornou um JSON válido"}
        except Exception as e:
            debug_log(f"[translate_urantia_paragraph] exception={e}")
            return {"error": str(e)}

# # Exemplo de teste
# p_eng = "The Universal Father is the God of all creation, the First Source and Center of all things and beings."
# res = translate_urantia_paragraph(p_eng)

# print(f"Tradução: {res.get('translation')}")
# print(f"Comentários: {res.get('comments')}")


def split_tokens(text: str):
    """Splits text preserving whitespace chunks for token-based diff rendering."""
    return re.split(r"(\s+)", text)


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
    english_text = (
        english_paragraph.get("Text", "")
        if isinstance(english_paragraph, dict)
        else str(english_paragraph or "")
    )
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
    """Placeholder for AI translation generation from the English paragraph text.

    For now, it returns an empty string. In a next step, this function can call an
    external AI model using API key, model name, and endpoint URL settings.
    """
    result = AIHelper.translate(english)
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
    debug_log(f"[build_paragraph_fields] start proposed_text_provided={proposed_text is not None}")
    proposal = portuguese_text if proposed_text is None else proposed_text.strip()
    ai_result = {"translation": "", "comments": ""}

    if proposed_text is not None:
        debug_log("[build_paragraph_fields] calling translate")
        ai_result = translate(english)
        debug_log(f"[build_paragraph_fields] ai_translation_length={len(ai_result.get('translation', ''))} ai_comments_length={len(ai_result.get('comments', ''))}")
    else:
        debug_log("[build_paragraph_fields] skipping translation on GET render")

    return {
        "english": english,
        "portuguese_text": portuguese_text,
        "proposal": proposal,
        "ai_proposal": ai_result.get("translation", ""),
        "ai_comments": ai_result.get("comments", ""),
        "merge_html": merge_preview_html(portuguese_text, proposal),
    }
