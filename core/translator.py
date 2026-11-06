"""Batch translation with NVIDIA (primary) and automatic fallback to Ollama Cloud.
Both use the OpenAI-compatible /chat/completions endpoint."""
import json, os, re, time
import requests

# Use the OS certificate store (fixes SSL errors behind antivirus/corporate HTTPS inspection)
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass
from .languages import prompt_name

# Fallback when none of the configured models exists: pick the best match from the live catalog
AUTO_PICK = [r"deepseek-v3", r"qwen3-235b", r"qwen3.*(instruct|a22b)", r"kimi-k2", r"gpt-oss-120b", r"llama-3\.3-70b",
             r"llama-4-maverick", r"mistral-large", r"llama-3\.1-70b", r"gemma-3-27b", r"gpt-oss-20b"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH = int(os.getenv("BATCH_SIZE", "30"))

VARIANTS = {
    "es": "SPANISH VARIANT: always neutral Latin American Spanish (español neutro). Use 'ustedes', never 'vosotros'. "
          "Avoid Spain-only words (tío, coger, vale, gilipollas) and country-specific slang (güey, chido, che, parce, boludo).",
    "pt": "PORTUGUESE VARIANT: Brazilian Portuguese.",
    "zh": "CHINESE VARIANT: Simplified Chinese characters.",
}


class QuotaExhausted(Exception):
    pass


class ModelUnavailable(Exception):
    """Model does not exist or is not in the free plan: try the next model of the same provider."""


def _read(name):
    with open(os.path.join(ROOT, "prompts", name), encoding="utf-8") as f:
        return f.read()


class Provider:
    def __init__(self, name, url, key, models):
        self.name, self.url, self.key = name, (url or "").rstrip("/"), key
        self.models = [m.strip() for m in models if m and m.strip()]
        self.model = None
        self.dead = not (self.url and self.key and self.models)

    def headers(self):
        return {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def resolve_model(self, log):
        """Picks the first model from the preference list that exists in /models."""
        if self.dead:
            return
        try:
            r = requests.get(f"{self.url}/models", headers=self.headers(), timeout=20)
            if r.status_code in (401, 403):
                log(f"[{self.name}] invalid API key or no access ({r.status_code})."); self.dead = True; return
            available = {m["id"] for m in r.json().get("data", [])}
            self.model = next((m for m in self.models if m in available), None)
            if not self.model:
                for pat in AUTO_PICK:
                    hit = sorted(m for m in available if re.search(pat, m, re.I) and not re.search(r"(coder|vision|vl|embed|guard|reward)", m, re.I))
                    if hit:
                        self.model = hit[-1]; self.models = [self.model]
                        log(f"[{self.name}] configured models not found; auto-selected {self.model}")
                        break
            if not self.model:
                log(f"[{self.name}] no suitable model in catalog ({len(available)} models)."); self.dead = True
        except Exception as e:  # no catalog: trust the first one
            log(f"[{self.name}] could not list models ({e}); using {self.models[0]}.")
            self.model = self.models[0]

    def chat(self, system, user):
        body = {"model": self.model, "temperature": 0.3, "max_tokens": 8192,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        rate_hits = 0
        while True:
            r = requests.post(f"{self.url}/chat/completions", headers=self.headers(), json=body, timeout=300)
            txt = r.text.lower()
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"] or ""
            if r.status_code == 404 or "not included in your free" in txt or "not found" in txt:
                raise ModelUnavailable(f"{self.name}: {self.model} not available for free ({r.status_code})")
            # Free quota exhausted → immediate fallback
            if r.status_code in (402, 403) or any(k in txt for k in ("quota", "credit", "insufficient", "usage limit", "exceeded your")):
                raise QuotaExhausted(f"{self.name}: free quota exhausted ({r.status_code})")
            if r.status_code == 429:  # rate limit: wait twice, then switch provider
                rate_hits += 1
                if rate_hits > 2:
                    raise QuotaExhausted(f"{self.name}: persistent rate limit (429)")
                time.sleep(min(int(r.headers.get("retry-after", "0") or 0) or 15 * rate_hits, 60))
                continue
            if r.status_code >= 500 and rate_hits < 2:
                rate_hits += 1; time.sleep(5); continue
            raise RuntimeError(f"{self.name} HTTP {r.status_code}: {r.text[:300]}")


def build_providers():
    order = [p.strip().lower() for p in os.getenv("PROVIDER_ORDER", "nvidia,ollama").split(",")]
    defs = {
        "nvidia": Provider("NVIDIA", os.getenv("NVIDIA_URL"), os.getenv("NVIDIA_API_KEY"),
                           os.getenv("NVIDIA_MODELS", "").split(",")),
        "ollama": Provider("Ollama", os.getenv("OLLAMA_URL"), os.getenv("OLLAMA_API_KEY"),
                           os.getenv("OLLAMA_MODELS", "").split(",")),
    }
    return [defs[p] for p in order if p in defs]


def _parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON")
    return json.loads(m.group(0))


class Translator:
    def __init__(self, source, target, log=print, progress=lambda d, t: None):
        self.log, self.progress = log, progress
        src, tgt = prompt_name(source) if source else "the source language", prompt_name(target)
        self.target_name = tgt
        self.system = _read("system.md").format(source=src, target=tgt, variant=VARIANTS.get(target, ""))
        self.user_tpl = _read("user.md")
        self.providers = build_providers()
        for p in self.providers:
            p.resolve_model(log)
        if all(p.dead for p in self.providers):
            raise RuntimeError("No provider available. Check .env (keys, URLs, models).")
        self.current = next(p for p in self.providers if not p.dead)
        log(f"Provider: {self.current.name} · model: {self.current.model}")

    def _call(self, system, user):
        while True:
            try:
                return self.current.chat(system, user)
            except ModelUnavailable as e:
                self.log(f"⚠ {e}")
                p = self.current
                rest = p.models[p.models.index(p.model) + 1:] if p.model in p.models else []
                if rest:
                    p.models, p.model = rest, rest[0]
                    self.log(f"↪ {p.name}: trying model {p.model}")
                    continue
                p.dead = True
                nxt = next((q for q in self.providers if not q.dead), None)
                if not nxt:
                    raise RuntimeError("No free model available on any provider.")
                self.current = nxt
                self.log(f"↪ Switching to {nxt.name} · {nxt.model}")
            except (QuotaExhausted, RuntimeError, requests.RequestException) as e:
                self.log(f"⚠ {e}")
                self.current.dead = True
                nxt = next((p for p in self.providers if not p.dead), None)
                if not nxt:
                    reason = "free quota exhausted" if isinstance(e, QuotaExhausted) else "request failed"
                    raise RuntimeError(f"No provider left ({reason}). Last error: {str(e)[:200]}")
                self.current = nxt
                self.log(f"↪ Switching to {nxt.name} · {nxt.model}")

    def _batch(self, items, context, depth=0):
        ids = [str(i + 1) for i in range(len(items))]
        payload = "\n".join(json.dumps({"id": i, "text": t}, ensure_ascii=False) for i, t in zip(ids, items))
        user = self.user_tpl.format(context="\n".join(context) or "(none)", target=self.target_name,
                                    ids=", ".join(ids), items=payload)
        for attempt in range(3):
            try:
                data = _parse_json(self._call(self.system, user))
                out = [data.get(i) for i in ids]
                if all(isinstance(x, str) and x.strip() for x in out):
                    return out
                raise ValueError("missing ids in response")
            except (ValueError, json.JSONDecodeError) as e:
                self.log(f"  invalid response ({e}), retry {attempt + 1}/3")
        if len(items) == 1:
            self.log("  ✖ a line could not be translated; keeping the original")
            return items
        mid = len(items) // 2  # split the batch and retry in halves
        return self._batch(items[:mid], context, depth + 1) + self._batch(items[mid:], context, depth + 1)

    def translate(self, units):
        out = []
        for start in range(0, len(units), BATCH):
            chunk = units[start:start + BATCH]
            out += self._batch(chunk, out[-4:])
            self.progress(len(out), len(units))
        return out
