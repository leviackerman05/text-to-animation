"""
LLM-first Manim script generation with validate-and-retry loop.
"""

import ast
import re
from pathlib import Path
from typing import Callable, Optional, Tuple

from dotenv import load_dotenv

from app.llm import call_llm, get_model
from app.prompt_engine.prompts import PROMPT_TEMPLATES
from app.prompt_engine.script_validation import validate_script
from app.renderer import RenderResult, extract_class_name, render_manim_script

try:
    from app.prompt_engine.smart_intent_detector import detect_intent
except Exception:
    from app.prompt_engine.intent_detector import detect_intent

from app.template_engine import generate_from_template

load_dotenv()

MAX_RETRIES = 3
DEFAULT_OUTPUT = "app/static/outputs/generated_scene.py"

StatusCallback = Callable[[str, str], None]


def extract_code_from_response(text: str) -> str:
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    start_index = text.find("from manim import *")
    return text[start_index:].strip() if start_index != -1 else text.strip()


def normalize_script(script_code: str) -> str:
    if "from manim import *" not in script_code:
        script_code = "from manim import *\n" + script_code
    script_code = re.sub(
        r"class\s+\w+\s*\(\s*(ThreeDScene|Scene)\s*\)",
        r"class GeneratedScene(\1)",
        script_code,
    )
    return script_code.strip() + "\n"


def build_generation_prompt(latest_message: str, history: Optional[list] = None) -> str:
    """Merge chat history so follow-ups refine the original request, not replace it."""
    if not history:
        return latest_message.strip()

    user_messages = [
        m["content"].strip()
        for m in history
        if m.get("role") == "user" and m.get("content", "").strip()
    ]
    if len(user_messages) <= 1:
        return latest_message.strip()

    original = user_messages[0]
    corrections = user_messages[1:]

    lines = [
        f"ORIGINAL ANIMATION REQUEST:\n{original}",
        "",
        "USER CORRECTIONS (apply to the original — do NOT animate this feedback literally):",
    ]
    for i, correction in enumerate(corrections, 1):
        lines.append(f"{i}. {correction}")
    lines.extend(
        [
            "",
            "Create the animation for the ORIGINAL REQUEST, updated with all corrections.",
            "Show the actual subject (e.g. a ball falling under gravity), not text about the user's complaint.",
            "Never turn a ball into a cube unless the user explicitly asks for a cube.",
        ]
    )
    return "\n".join(lines)


def get_intent_source(user_prompt: str) -> str:
    """Use the original request for intent when the prompt contains conversation context."""
    marker = "ORIGINAL ANIMATION REQUEST:"
    if marker in user_prompt:
        start = user_prompt.index(marker) + len(marker)
        rest = user_prompt[start:].strip()
        end = rest.find("\n\n")
        original = rest[:end].strip() if end != -1 else rest.split("\n")[0].strip()
        corrections_block = user_prompt.split("USER CORRECTIONS", 1)
        corrections = corrections_block[1] if len(corrections_block) > 1 else ""
        return f"{original} {corrections}"
    return user_prompt


def get_system_prompt(user_prompt: str) -> str:
    intent_source = get_intent_source(user_prompt)
    intent = detect_intent(intent_source)
    template_fn = PROMPT_TEMPLATES.get(intent, PROMPT_TEMPLATES["concept_explanation"])
    return template_fn(intent_source).strip()


def _build_user_message(user_prompt: str, previous_code: str = "", error: str = "") -> str:
    if not previous_code:
        return f"Create a Manim animation for this request:\n\n{user_prompt.strip()}"
    return (
        f"Fix the Manim script below. The previous version failed.\n\n"
        f"ORIGINAL REQUEST:\n{user_prompt.strip()}\n\n"
        f"ERROR:\n{error[-2000:]}\n\n"
        f"BROKEN CODE:\n```python\n{previous_code}\n```\n\n"
        f"Return ONLY the corrected Python code."
    )


def generate_script_with_llm(
    user_prompt: str,
    model: Optional[str] = None,
    previous_code: str = "",
    error: str = "",
    on_status: Optional[StatusCallback] = None,
) -> str:
    if on_status:
        on_status("writing_code", "Generating Manim script...")

    system_prompt = get_system_prompt(user_prompt)
    user_message = _build_user_message(user_prompt, previous_code, error)
    resolved_model = model or get_model()

    raw_output = call_llm(user_message, system=system_prompt, model=resolved_model, timeout=120)
    if not raw_output:
        return ""

    script_code = normalize_script(extract_code_from_response(raw_output))
    is_valid, err = validate_script(script_code)
    if not is_valid:
        print(f" Validation failed: {err}")
        if on_status:
            on_status("writing_code", f"Fixing script: {err}")
    return script_code


def try_template_fallback(user_prompt: str) -> Optional[str]:
    """Optional fast-path for well-structured math prompts."""
    script_code, status = generate_from_template(user_prompt)
    if script_code:
        is_valid, _ = validate_script(script_code)
        if is_valid:
            print(f" Template fallback succeeded")
            return script_code
    print(f" Template fallback skipped: {status}")
    return None


def generate_script(
    user_prompt: str,
    model: Optional[str] = None,
    output_path: str = DEFAULT_OUTPUT,
    on_status: Optional[StatusCallback] = None,
    use_template_fallback: bool = False,
) -> str:
    """
    LLM-first script generation. Templates are optional fallback only.
    """
    if on_status:
        on_status("analyzing", "Analyzing your prompt...")

    script_code = ""
    if use_template_fallback:
        script_code = try_template_fallback(user_prompt) or ""

    if not script_code:
        script_code = generate_script_with_llm(user_prompt, model, on_status=on_status)

    if not script_code:
        return ""

    is_valid, err = validate_script(script_code)
    if not is_valid:
        for attempt in range(MAX_RETRIES - 1):
            print(f" Retry {attempt + 1}/{MAX_RETRIES - 1} after validation error")
            fixed = generate_script_with_llm(
                user_prompt,
                model,
                previous_code=script_code,
                error=err,
                on_status=on_status,
            )
            if not fixed:
                continue
            script_code = fixed
            is_valid, err = validate_script(script_code)
            if is_valid:
                break

    if not validate_script(script_code)[0]:
        print(f" Failed to produce valid script: {err}")
        return ""

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(script_code, encoding="utf-8")
    print(f" Manim script saved to: {output_path}")
    return script_code


def generate_and_render(
    user_prompt: str,
    model: Optional[str] = None,
    output_path: str = DEFAULT_OUTPUT,
    hd: bool = False,
    on_status: Optional[StatusCallback] = None,
) -> Tuple[str, RenderResult]:
    """
    Full pipeline: generate script, render video, retry on render errors.
    Returns (script_code, RenderResult).
    """
    script_code = generate_script(user_prompt, model, output_path, on_status=on_status)
    if not script_code:
        return "", RenderResult(success=False, error_log="Script generation failed")

    class_name = extract_class_name(output_path)
    previous_code = script_code

    for attempt in range(MAX_RETRIES):
        if on_status:
            on_status("rendering", f"Rendering video (attempt {attempt + 1})...")

        result = render_manim_script(output_path, class_name, hd=hd)
        if result.success:
            if on_status:
                on_status("done", "Video ready!")
            return script_code, result

        print(f" Render failed (attempt {attempt + 1}): {result.error_log[:200]}")
        if attempt >= MAX_RETRIES - 1:
            break

        if on_status:
            on_status("writing_code", "Fixing code after render error...")

        fixed = generate_script_with_llm(
            user_prompt,
            model,
            previous_code=previous_code,
            error=result.error_log,
            on_status=on_status,
        )
        if not fixed:
            continue

        is_valid, err = validate_script(fixed)
        if not is_valid:
            result.error_log = err
            continue

        previous_code = fixed
        script_code = fixed
        Path(output_path).write_text(script_code, encoding="utf-8")
        class_name = extract_class_name(output_path)

    if on_status:
        on_status("error", "Failed to generate video")
    return script_code, result
