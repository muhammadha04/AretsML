"""Evidence: for each step, the exact words on the source chart that it rests on.

Native format is `<chart>.evidence.json`. The hand-made `<chart>.verify.md`
sheets are also read, so the existing charts can be checked the same way.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CHART = "_chart"  # key for chart-level text: title, caption, notes
# "arrow from Set Down for Trial: within 60 days" -> "within 60 days"
ANNOTATION = re.compile(r"^[^:]{0,40}\b(?:arrow|line|label|bracket)\b[^:]{0,60}:\s*", re.I)


@dataclass
class Evidence:
    quotes: dict[str, list[str]] = field(default_factory=dict)   # step_id -> quotes
    source_text: str = ""       # text of the source document, if we have one
    source_kind: str = ""       # text_layer | ocr | model_transcript | ""

    def for_step(self, step_id: str) -> list[str]:
        return self.quotes.get(step_id, [])

    def chart_level(self) -> list[str]:
        return self.quotes.get(CHART, [])

    def to_json(self) -> str:
        return json.dumps({"source_kind": self.source_kind, "quotes": self.quotes}, indent=2, ensure_ascii=False)


def clean_quote(q: str) -> str:
    q = re.sub(r"\[[^\]]*\]", "", q)          # [dashed box]
    return ANNOTATION.sub("", q.strip()).strip()


def load_evidence(path: str | Path) -> Evidence:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        return Evidence(data.get("quotes", {}), source_kind=data.get("source_kind", ""))
    return _from_verify_md(text)


def _from_verify_md(text: str) -> Evidence:
    quotes: dict[str, list[str]] = {CHART: []}
    for line in text.splitlines():
        if line.startswith("# "):
            quotes[CHART].append(line[2:].split(" - ", 1)[-1].strip())
        m = re.match(r'- Chart (?:caption|text): "(.*)"\s*$', line)
        if m:
            quotes[CHART].append(m.group(1))
    col = None
    for line in text.splitlines():
        if not line.startswith("|"):
            col = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == "step_id":
            col = cells.index("exact source text") if "exact source text" in cells else None
            continue
        if col is None or set(cells[0]) <= set("-: ") or len(cells) <= col:
            continue
        parts = [clean_quote(p) for p in cells[col].split(" / ")]
        quotes[cells[0]] = [p for p in parts if p]
    return Evidence(quotes)


def find_evidence_file(csv_path: Path) -> Path | None:
    for suffix in (".evidence.json", ".verify.md"):
        p = csv_path.with_name(csv_path.stem + suffix)
        if p.exists():
            return p
    return None
