"""Top-11 languages. The UI always shows 10 = 11 minus the source language."""

# code, UI label, prompt name, ISO 639-2 aliases found in MKV tags
TOP_LANGUAGES = [
    ("en", "English", "English", {"eng", "en"}),
    ("es", "Spanish (Neutral)", "neutral Latin American Spanish (español neutro, no regional slang, use 'ustedes')", {"spa", "es", "esp"}),
    ("zh", "Chinese (Simplified)", "Simplified Chinese", {"zho", "chi", "zh", "chs"}),
    ("hi", "Hindi", "Hindi", {"hin", "hi"}),
    ("ar", "Arabic", "Modern Standard Arabic", {"ara", "ar"}),
    ("pt", "Portuguese (Brazil)", "Brazilian Portuguese", {"por", "pt", "pob"}),
    ("fr", "French", "French", {"fra", "fre", "fr"}),
    ("ru", "Russian", "Russian", {"rus", "ru"}),
    ("ja", "Japanese", "Japanese", {"jpn", "ja"}),
    ("de", "German", "German", {"deu", "ger", "de"}),
    ("ko", "Korean", "Korean", {"kor", "ko"}),
]

BY_CODE = {c: (c, ui, prompt, al) for c, ui, prompt, al in TOP_LANGUAGES}


def normalize(tag: str | None) -> str | None:
    """Maps 'eng' / 'en-US' / 'zh-cn' to a 2-letter code, or None."""
    if not tag:
        return None
    t = tag.lower().replace("_", "-").split("-")[0]
    for code, _ui, _p, aliases in TOP_LANGUAGES:
        if t in aliases:
            return code
    return t if len(t) == 2 else None


def ui_name(code: str) -> str:
    return BY_CODE[code][1] if code in BY_CODE else code.upper()


def prompt_name(code: str) -> str:
    return BY_CODE[code][2] if code in BY_CODE else code


def targets_for(source_code: str | None) -> list[tuple[str, str]]:
    """Exactly 10 targets: the 11 minus the source (if the source is not in the top list, the first 10)."""
    out = [(c, ui) for c, ui, _p, _a in TOP_LANGUAGES if c != source_code]
    return out[:10]


def detect_language(tag, sub):
    code = normalize(tag)
    if code and code != "und":
        return code, "MKV tag"
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
        return normalize(detect(sub.sample_text())), "text detection"
    except Exception:
        return None, "unknown"
