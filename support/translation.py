"""Language detection and translation via ModelRouter."""

from __future__ import annotations

import re

from .state import logger, router


async def detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code."""
    if not text.strip():
        return "zh"

    # Simple heuristic for unique-script languages (avoid API call)
    chinese_ratio = len(re.findall(r'[\u4e00-\u9fff]', text)) / max(len(text), 1)
    if chinese_ratio > 0.3:
        return "zh"

    if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
        return "ja"
    if re.search(r'[\uac00-\ud7af]', text):
        return "ko"
    if re.search(r'[\u0e00-\u0e7f]', text):
        return "th"
    if re.search(r'[\u0600-\u06ff]', text):
        return "ar"
    if re.search(r'[\u0400-\u04ff]', text):
        return "ru"

    # Latin script — use LLM for accurate detection (fr/es/de/pt/etc.)
    if router.get_backend("detect_lang") and re.search(r'[a-zA-Z]{3,}', text):
        try:
            code = await router.chat(
                "detect_lang",
                [
                    {"role": "system", "content": "Detect the language of the text. Reply with ONLY the ISO 639-1 code (e.g. en, fr, de, es, pt, vi, id). Nothing else."},
                    {"role": "user", "content": text},
                ],
                temperature=0,
                max_tokens=5,
                timeout=5,
            )
            code = code.strip().lower()[:2]
            if re.match(r'^[a-z]{2}$', code):
                return code
        except Exception as e:
            logger.warning("language detection API failed: %s", e)

    # Fallback: Latin script = English
    if re.search(r'[a-zA-Z]{3,}', text):
        return "en"

    return "zh"


async def translate_text(text: str, target_lang: str, source_lang: str = "") -> str:
    """Translate text via ModelRouter. Returns translated text."""
    if not router.get_backend("translate") or not text.strip():
        return text

    if source_lang == target_lang:
        return text

    lang_names = {
        "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
        "th": "Thai", "ar": "Arabic", "ru": "Russian", "es": "Spanish",
        "fr": "French", "de": "German", "pt": "Portuguese", "vi": "Vietnamese",
        "id": "Indonesian", "ms": "Malay", "tl": "Filipino",
    }
    target_name = lang_names.get(target_lang, target_lang)

    try:
        return await router.chat(
            "translate",
            [
                {"role": "system", "content": f"Translate the following text to {target_name}. Only output the translation, nothing else."},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=1000,
            timeout=10,
        )
    except Exception as e:
        logger.warning("translation failed: %s", e)
        return text
