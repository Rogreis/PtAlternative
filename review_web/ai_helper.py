from __future__ import annotations

import json
import subprocess

from .log import debug_log


class AIHelper:
    """Utility helper for AI translation calls used by the review page."""

    @staticmethod
    def _generate_prompt(english_text) -> str:
        """Builds the translation prompt from the English paragraph text."""

        system_instruction = (
            "You are a scholar and expert translator of The Urantia Book. "
            "Your goal is to translate paragraphs from English to Brazilian Portuguese. "
            "Maintain the solemn, philosophical, and elevated tone of the book. "
            "Adhere strictly to the standard Urantia terminology in Portuguese (e.g., 'Thought Adjuster' as 'Ajustador do Pensamento'). "
            "The output must be a valid JSON object with two fields: "
            "'translation' (the translated text) and 'comments' (brief linguistic or terminological notes about the translation)."
        )

        return system_instruction + "\n\nText to translate:\n" + str(english_text)

    # Full path to wsl.exe avoids PATH resolution failures when running under uvicorn.
    _WSL_EXE = r"C:\Windows\System32\wsl.exe"
    _WSL_PYTHON = "/home/r/mcp-fraud-detector/.venv/bin/python"
    _WSL_SCRIPT = "server/helpers/ai_call.py"
    _WSL_CWD = "/home/r/mcp-fraud-detector"

    @staticmethod
    def run_ai_call_in_wsl(prompt: str) -> dict[str, str]:
        """Runs the external WSL AI script and captures console output.

        Mirrors the C# ExecuteWslCommandAsync pattern: uses the wsl.exe full
        path and passes arguments directly as a list instead of wrapping in
        bash -lc, with explicit UTF-8 encoding on stdout/stderr.
        """
        debug_log(f"[run_ai_call_in_wsl] executing command in WSL for prompt_length={len(prompt)}")

        try:
            completed = subprocess.run(
                [
                    AIHelper._WSL_EXE,
                    "--cd", AIHelper._WSL_CWD,
                    AIHelper._WSL_PYTHON,
                    AIHelper._WSL_SCRIPT,
                    "--model", "claude",
                    prompt,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=120,
            )
        except FileNotFoundError:
            debug_log(f"[run_ai_call_in_wsl] wsl executable not found at {AIHelper._WSL_EXE}")
            return {"output": "", "error": f"wsl.exe nao encontrado em {AIHelper._WSL_EXE}."}
        except subprocess.TimeoutExpired:
            debug_log("[run_ai_call_in_wsl] command timeout")
            return {"output": "", "error": "Tempo limite excedido ao executar script no WSL."}
        except OSError as exc:
            debug_log(f"[run_ai_call_in_wsl] os_error={exc}")
            return {"output": "", "error": f"Falha ao executar WSL: {exc}"}

        stdout_text = (completed.stdout or "").strip()
        stderr_text = (completed.stderr or "").strip()
        debug_log(
            "[run_ai_call_in_wsl] "
            f"return_code={completed.returncode} stdout_len={len(stdout_text)} stderr_len={len(stderr_text)}"
        )

        if completed.returncode != 0:
            error_message = stderr_text or stdout_text or "Erro desconhecido na execucao do script no WSL."
            return {"output": stdout_text, "error": error_message}

        return {"output": stdout_text, "error": ""}

    @staticmethod
    def translate_urantia_paragraph(english_text):
        # Uses the WSL helper script to produce a translated output.

        try:
            prompt = AIHelper._generate_prompt(english_text)
            debug_log(f"\n\n[translate_urantia_paragraph] Prompt:\n{prompt}\n")
            wsl_result = AIHelper.run_ai_call_in_wsl(prompt)
            if wsl_result.get("error"):
                return {"error": wsl_result["error"]}

            raw_text = wsl_result.get("output", "")
            debug_log(f"[translate_urantia_paragraph] raw_ai_text={raw_text}")

            # Strip markdown code block wrappers (```json ... ```) that some models emit.
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            json_text = raw_text[start : end + 1] if start != -1 and end != -1 else raw_text

            # Accept JSON payloads when available, otherwise treat output as translation text.
            try:
                response_data = json.loads(json_text)
                if isinstance(response_data, dict):
                    response_data.setdefault("translation", "")
                    response_data.setdefault("comments", "")
                    debug_log(f"[translate_urantia_paragraph] parsed_keys={list(response_data.keys())}")
                    return response_data
            except json.JSONDecodeError:
                pass

            return {"translation": raw_text, "comments": ""}

        except json.JSONDecodeError:
            debug_log("[translate_urantia_paragraph] invalid_json_response")
            return {"error": "IA nao retornou um JSON valido"}
        except Exception as exc:
            debug_log(f"[translate_urantia_paragraph] exception={exc}")
            return {"error": str(exc)}
