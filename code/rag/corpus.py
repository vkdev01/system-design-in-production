"""Chapter 11: a tiny corpus that reproduces the context-loss failure.

Eight filings, each split into chunks that say "the company" or "revenue"
without naming the entity -- exactly the situation Anthropic describes. With
contextualisation, each chunk gets its document identity prepended before it is
indexed, and retrieval on entity-bearing questions improves.
"""

from __future__ import annotations

import dataclasses
import re

COMPANIES = ["ACME", "Borealis", "Cobalt", "Dunmore", "Everest", "Fulcrum", "Garnet", "Halcyon"]
QUARTERS = ["Q1 2023", "Q2 2023", "Q3 2023", "Q4 2023"]
TOPICS = [
    "revenue grew by {pct}% over the previous quarter",
    "gross margin expanded to {pct}% on lower input costs",
    "operating expenses rose {pct}% after the acquisition",
    "headcount increased {pct}% year over year",
    "the board approved a buyback worth {pct}% of market capitalisation",
]

FILLER = (
    "Management discussed the outlook at length and reiterated prior guidance, "
    "noting that demand remained resilient across the segment."
)


@dataclasses.dataclass
class Chunk:
    cid: str
    doc: str
    text: str
    context: str = ""

    @property
    def indexed_text(self) -> str:
        return (self.context + "\n" + self.text).strip() if self.context else self.text


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def build(contextualised: bool = False) -> list[Chunk]:
    chunks: list[Chunk] = []
    for d, company in enumerate(COMPANIES):
        for q, quarter in enumerate(QUARTERS):
            for t, topic in enumerate(TOPICS):
                pct = 3 + (d + q + t) % 17
                body = f"The company's {topic.format(pct=pct)}. {FILLER}"
                cid = f"c{d:02d}{q}{t}"
                doc = f"{company} {quarter} filing"
                ctx = f"This chunk is from {company}'s {quarter} filing." if contextualised else ""
                chunks.append(Chunk(cid=cid, doc=doc, text=body, context=ctx))
    return chunks


def golden(chunks: list[Chunk]) -> list[dict]:
    """Two question families, because they fail differently.

    * entity questions -- need the company and quarter, which only exist in the
      document, so they need contextualisation
    * identifier questions -- quote an exact figure, which BM25 can match
      without any context at all
    """
    out = []
    for c in chunks:
        if not c.cid.endswith("0"):          # revenue topic only
            continue
        company = c.doc.split(" ")[0]
        quarter = " ".join(c.doc.split(" ")[1:3])
        pct = re.search(r"grew by (\d+)%", c.text).group(1)
        out.append({
            "q": f"What was the revenue growth for {company} in {quarter}?",
            "gold": c.cid,
            "kind": "entity",
        })

    # identifier questions: an exact number in the query, no entity needed
    for c in chunks[:8]:
        pct = re.search(r"(\d+)%", c.text)
        if pct:
            out.append({
                "q": f"Which filing mentions {pct.group(1)}%?",
                "gold": c.cid,
                "kind": "identifier",
            })
    return out
