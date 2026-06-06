"""
Unified LLM client. Defaults to Groq (free tier, hosted).

Set LLM_PROVIDER=groq and GROQ_API_KEY in .env (get a free key at console.groq.com).
Set LLM_PROVIDER=gemini to use Google Gemini instead.
"""

import json
import os
import re
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "groq").lower()


def get_model() -> str:
    if get_provider() == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    return os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def _call_groq(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Optional[str]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ GROQ_API_KEY not set. Get a free key at https://console.groq.com")
        return None

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or get_model(),
                "messages": messages,
                "temperature": 0.2,
            },
            timeout=timeout,
        )

        if response.status_code != 200:
            print(f"Groq API error: {response.status_code}")
            print(response.text)
            return None

        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error calling Groq: {e}")
        return None


def _call_gemini(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Optional[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set")
        return None

    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    payload = {"contents": [{"parts": [{"text": full_prompt}]}]}

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model or get_model()}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )

        if response.status_code != 200:
            print(f"Gemini API error: {response.status_code}")
            print(response.text)
            return None

        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None


def call_llm(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Optional[str]:
    provider = get_provider()
    print(f"Using LLM provider: {provider} ({model or get_model()})")

    if provider == "gemini":
        return _call_gemini(prompt, system, model, timeout)
    return _call_groq(prompt, system, model, timeout)


def parse_json_response(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    print(f"Failed to parse JSON from LLM response: {text[:200]}...")
    return None


def call_llm_json(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    text = call_llm(
        prompt,
        system=system or "Respond with valid JSON only. No markdown or explanation.",
        model=model,
    )
    if not text:
        return None
    return parse_json_response(text)
