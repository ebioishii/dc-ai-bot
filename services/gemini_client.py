from __future__ import annotations
import os
import re
import json
import hashlib

import google.generativeai as genai
from dotenv import load_dotenv

try:
    from google.generativeai import caching
except Exception:  # pragma: no cover - optional SDK surface
    caching = None

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

GM_MODEL = "gemini-2.5-flash-lite"
BASE_MODEL = "gemini-2.5-flash-lite"
_PROMPT_CACHE: dict[str, str] = {}


def _cache_key(model_name: str, system: str) -> str:
    digest = hashlib.sha256(f"{model_name}\n{system}".encode("utf-8")).hexdigest()[:24]
    return f"static-rules-{digest}"


def _generation_config(max_tokens: int, temperature: float, response_mime_type: str | None = None):
    kwargs = {"max_output_tokens": max_tokens, "temperature": temperature}
    if response_mime_type:
        kwargs["response_mime_type"] = response_mime_type
    return genai.types.GenerationConfig(**kwargs)


def _cached_model(model_name: str, system: str):
    if caching is None or not system or len(system) < 1200:
        return None
    key = _cache_key(model_name, system)
    try:
        cached_name = _PROMPT_CACHE.get(key)
        if not cached_name:
            cached = caching.CachedContent.create(
                model=model_name,
                display_name=key[:128],
                system_instruction=system,
                contents=["Static Discord RP game rules cached for reuse."],
                ttl=3600,
            )
            cached_name = cached.name
            _PROMPT_CACHE[key] = cached_name
        return genai.GenerativeModel.from_cached_content(cached_name)
    except Exception as e:
        print(f"⚠️ Gemini prompt cache unavailable, falling back: {e}")
        return None

async def call_gemini(system: str, user: str, model: str = None,
                      temperature: float = 0.75, max_tokens: int = 600,
                      use_prompt_cache: bool = False) -> str | None:
    """統一的 Gemini 呼叫函式。回傳文字內容，失敗或被擋時回傳 None。"""
    try:
        model_name = model or GM_MODEL
        generation_config = _generation_config(max_tokens, temperature)
        gemini_model = _cached_model(model_name, system) if use_prompt_cache else None
        if gemini_model:
            resp = await gemini_model.generate_content_async(user, generation_config=generation_config)
        else:
            gemini_model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
                generation_config=generation_config
            )
            resp = await gemini_model.generate_content_async(user)

        if resp.prompt_feedback.block_reason:
            print(f"⚠️ Gemini 安全過濾：{resp.prompt_feedback.block_reason.name}")
            return None

        text = resp.text
        if not text or not text.strip():
            print("⚠️ Gemini 回傳空內容")
            return None
        return text.strip()
    except Exception as e:
        print(f"⚠️ Gemini 呼叫失敗：{e}")
        return None


def extract_json_object(text: str) -> dict | None:
    """從模型輸出中解析 JSON；容忍 ```json fence 或前後雜訊。"""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            return None
    return None


async def call_gemini_json(system: str, user: str, model: str = None,
                           temperature: float = 0.65, max_tokens: int = 1000,
                           use_prompt_cache: bool = False) -> dict | None:
    """Gemini JSON 呼叫。優先要求 application/json；失敗時回傳 None。"""
    try:
        model_name = model or GM_MODEL
        generation_config = _generation_config(max_tokens, temperature, response_mime_type="application/json")
        gemini_model = _cached_model(model_name, system) if use_prompt_cache else None
        if gemini_model:
            resp = await gemini_model.generate_content_async(user, generation_config=generation_config)
        else:
            gemini_model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
                generation_config=generation_config
            )
            resp = await gemini_model.generate_content_async(user)
        if resp.prompt_feedback.block_reason:
            print(f"⚠️ Gemini 安全過濾：{resp.prompt_feedback.block_reason.name}")
            return None
        return extract_json_object(resp.text)
    except Exception as e:
        print(f"⚠️ Gemini JSON 呼叫失敗：{e}")
        return None


