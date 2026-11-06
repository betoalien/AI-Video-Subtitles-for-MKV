"""SRT and ASS/SSA parsing/rebuilding.
Only the TEXT is sent to the LLM; numbers, timestamps, styles and {\\...} tags are protected in code."""
import re

TAG_RE = re.compile(r"\{[^}]*\}")          # ASS override tags / {\an8} in SRT
PH_RE = re.compile(r"⟦\d+⟧")


def read_text(path: str) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise RuntimeError("Could not decode the subtitle file")


def protect(text: str) -> tuple[str, list[str]]:
    tags = []
    def rep(m):
        tags.append(m.group(0))
        return f"⟦{len(tags)}⟧"
    return TAG_RE.sub(rep, text), tags


def restore(text: str, tags: list[str]) -> str:
    missing = []
    for i, t in enumerate(tags, 1):
        ph = f"⟦{i}⟧"
        if ph in text:
            text = text.replace(ph, t, 1)
        else:
            missing.append(t)
    text = PH_RE.sub("", text)
    return "".join(missing) + text


def has_words(protected: str) -> bool:
    return bool(re.sub(r"<[^>]+>", "", PH_RE.sub("", protected)).strip())


class Subtitle:
    """units: list of protected texts to translate. apply(): rebuilds the file."""

    def __init__(self, path: str, fmt: str):
        self.fmt = fmt
        self.raw = read_text(path).replace("\r\n", "\n").replace("\r", "\n")
        self.units, self._tags, self._slots = [], [], []
        (self._parse_ass if fmt == "ass" else self._parse_srt)()

    # ---- SRT
    def _parse_srt(self):
        self._blocks = []
        for block in re.split(r"\n\s*\n", self.raw.strip()):
            lines = block.split("\n")
            t = next((i for i, l in enumerate(lines) if "-->" in l), None)
            if t is None:
                continue
            head, body = lines[: t + 1], "\n".join(lines[t + 1:])
            self._blocks.append([head, body])
            self._add(body, ("srt", len(self._blocks) - 1))

    # ---- ASS/SSA
    def _parse_ass(self):
        self._lines = self.raw.split("\n")
        for i, line in enumerate(self._lines):
            if line.startswith("Dialogue:"):
                parts = line[len("Dialogue:"):].split(",", 9)
                if len(parts) == 10:
                    self._add(parts[9].replace("\\N", "\n"), ("ass", i))

    def _add(self, text, slot):
        p, tags = protect(text)
        if has_words(p):
            self.units.append(p); self._tags.append(tags); self._slots.append(slot)

    def apply(self, translated: list[str]) -> str:
        assert len(translated) == len(self.units)
        for tr, tags, (kind, i) in zip(translated, self._tags, self._slots):
            text = restore(tr.strip(), tags)
            if kind == "srt":
                self._blocks[i][1] = text
            else:
                prefix, parts = "Dialogue:", self._lines[i][len("Dialogue:"):].split(",", 9)
                parts[9] = text.replace("\n", "\\N")
                self._lines[i] = prefix + ",".join(parts)
        if self.fmt == "ass":
            return "\n".join(self._lines)
        out = []
        for n, (head, body) in enumerate(self._blocks, 1):
            head = list(head)
            if head and head[0].strip().isdigit():
                head[0] = str(n)
            out.append("\n".join(head + ([body] if body else [])))
        return "\n\n".join(out) + "\n"

    def sample_text(self, n=60) -> str:
        return "\n".join(PH_RE.sub("", re.sub(r"<[^>]+>", "", u)) for u in self.units[:n])
