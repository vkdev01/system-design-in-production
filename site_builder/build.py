#!/usr/bin/env python3
"""Static site builder for System Design in Production.

Replaces the MkDocs/Material build with a hand-rolled generator and a bespoke
layout: top navigation, card-grid landing page, centred reading column with a
floating contents rail, dark code panels, no theme framework at all.

    python site_builder/build.py          # writes dist/
    python site_builder/build.py --serve  # writes dist/ then serves on :8000
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BUILDER = ROOT / "site_builder"
OUT = ROOT / "dist"

SITE = {
    "title": "System Design in Production",
    "tagline": "Thirteen production systems, rebuilt from first principles.",
    "repo": "https://github.com/vkdev01/system-design-in-production",
    "url": "https://vkdev01.github.io/system-design-in-production",
    # Project pages live under /<repo>/, so every template link needs the prefix.
    # Empty for local preview:  SITE_BASE= python site_builder/build.py
    "base": os.environ.get("SITE_BASE", ""),
}

# --------------------------------------------------------------------------
# The navigation model. This is the only place page order lives.
# --------------------------------------------------------------------------
SECTIONS = [
    {
        "id": "foundations",
        "label": "Foundations",
        "blurb": "Read these three first. Everything else is a variation.",
        "pages": [
            {
                "src": "foundations/mental-models.md",
                "title": "The 9 mental models",
                "kicker": "Model 01",
                "blurb": "Bounded queues, tail latency, hot partitions, idempotency as a state machine. The nine ideas every chapter is derived from.",
            },
            {
                "src": "foundations/numbers.md",
                "title": "Numbers you must know",
                "kicker": "Model 02",
                "blurb": "Unit conversions, latency figures, the soft ceilings of Postgres, ScyllaDB, Redis and FCM, and two worked sizing examples.",
            },
            {
                "src": "foundations/method.md",
                "title": "The 9-step method",
                "kicker": "Model 03",
                "blurb": "The nine steps every chapter follows, plus the timed structure of a 45-minute system design interview.",
            },
        ],
    },
    {
        "id": "chapters",
        "label": "Chapters",
        "blurb": "Nine systems, nine published post-mortems, nine build-alongs.",
        "pages": [
            {
                "src": "chapters/01-chat-message-storage.md",
                "title": "Chat message storage",
                "kicker": "01",
                "meta": "Discord",
                "blurb": "Partition keys that survive skew, a coalescing data service, and an online migration of trillions of rows.",
            },
            {
                "src": "chapters/02-sharding-postgres.md",
                "title": "Sharding Postgres",
                "kicker": "02",
                "meta": "Notion",
                "blurb": "480 logical shards over 32 databases, chosen for divisibility, and an online backfill with a five-minute cutover.",
            },
            {
                "src": "chapters/03-scaling-postgres-figma.md",
                "title": "Scaling Postgres without rewriting the app",
                "kicker": "03",
                "meta": "Figma",
                "blurb": "Vertical partitioning, a query routing proxy, and logical sharding before physical sharding.",
            },
            {
                "src": "chapters/04-idempotent-payment-api.md",
                "title": "Idempotent payment APIs",
                "kicker": "04",
                "meta": "Stripe",
                "blurb": "A key store that is a state machine: fingerprint, lease, replay, 409, and a reaper that keeps it from eating the primary.",
            },
            {
                "src": "chapters/05-double-payment-prevention.md",
                "title": "Stopping double payments",
                "kicker": "05",
                "meta": "Airbnb",
                "blurb": "Pre-RPC, RPC, post-RPC, a transactional outbox and the repair job that makes exactly-once real.",
            },
            {
                "src": "chapters/06-rate-limiting.md",
                "title": "Rate limiting and load shedding",
                "kicker": "06",
                "meta": "Stripe",
                "blurb": "Four limiters in order of cost, a token bucket in Lua, and the fail-open rule that keeps the limiter from becoming the outage.",
            },
            {
                "src": "chapters/07-realtime-messaging.md",
                "title": "Realtime messaging",
                "kicker": "07",
                "meta": "Slack",
                "blurb": "Channel servers own conversations by consistent hash, gateways own sockets by region, and a node loss costs 20 seconds.",
            },
            {
                "src": "chapters/08-geospatial-matching.md",
                "title": "Geospatial matching",
                "kicker": "08",
                "meta": "Uber H3",
                "blurb": "Turn geography into a 64-bit key: hexagon resolutions, ring expansion, and an offer lock that must be atomic.",
            },
            {
                "src": "chapters/09-notification-fanout.md",
                "title": "Notification fan-out",
                "kicker": "09",
                "meta": "Discord",
                "blurb": "A million pushes a minute against a provider that allows 100 in flight: bounded buffers, backpressure, shedding.",
            },
        ],
    },
    {
        "id": "ai",
        "label": "AI systems",
        "blurb": "Inference, retrieval, agents and evals: the same discipline applied to models.",
        "pages": [
            {
                "src": "chapters/10-llm-inference-serving.md",
                "title": "LLM inference serving",
                "kicker": "10",
                "meta": "vLLM",
                "blurb": "Paged KV cache, continuous batching, chunked prefill: an operating system for GPU memory.",
            },
            {
                "src": "chapters/11-retrieval-augmented-generation.md",
                "title": "Retrieval-augmented generation",
                "kicker": "11",
                "meta": "Anthropic",
                "blurb": "Contextual chunks, hybrid retrieval, reranking: 5.7% to 1.9% retrieval failure, and how to measure it.",
            },
            {
                "src": "chapters/12-agent-runtime.md",
                "title": "The agent runtime",
                "kicker": "12",
                "meta": "Durable execution",
                "blurb": "A forty-minute model-driven loop that survives a pod restart, with idempotent tools and budgets.",
            },
            {
                "src": "chapters/13-evals.md",
                "title": "Evals as a production system",
                "kicker": "13",
                "meta": "Statistics",
                "blurb": "Sample sizes, calibrated judges, slices and a gate: regression testing for non-deterministic systems.",
            },
        ],
    },
    {
        "id": "appendices",
        "label": "Appendices",
        "blurb": "The cross-chapter reference material.",
        "pages": [
            {
                "src": "appendices/k8s-aws-patterns.md",
                "title": "Kubernetes and AWS patterns",
                "kicker": "A",
                "blurb": "Workload objects, autoscaling, probes, PDBs, Postgres, IRSA, Envoy, observability, cost, and a golden manifest.",
            },
            {
                "src": "appendices/drills.md",
                "title": "Failure drills and interview scripts",
                "kicker": "B",
                "blurb": "Thirteen condensed two-minute answers, the follow-up matrix, one break-it command per chapter, and a 45-minute mock.",
            },
            {
                "src": "appendices/sources.md",
                "title": "Sources",
                "kicker": "C",
                "blurb": "The nine write-ups this manual is built on, plus the secondary reading worth your time.",
            },
        ],
    },
]

THEMES = [
    {"id": "atlas", "label": "Violet", "swatch": "#6d28d9"},
    {"id": "ink", "label": "Navy", "swatch": "#1f4e79"},
    {"id": "moss", "label": "Moss", "swatch": "#3f6212"},
    {"id": "cobalt", "label": "Cobalt", "swatch": "#1d4ed8"},
    {"id": "rose", "label": "Rose", "swatch": "#a61e4d"},
    {"id": "bronze", "label": "Bronze", "swatch": "#8a5a00"},
    {"id": "wine", "label": "Wine", "swatch": "#9d2f3d"},
]

# Stats are computed at build time so they cannot drift from the content.
def repo_file_count() -> int:
    skip = {"dist", ".git", "__pycache__", "node_modules", ".venv"}
    return sum(
        1 for p in ROOT.rglob("*")
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & skip)
    )

# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
EXTENSIONS = [
    "tables",
    "attr_list",
    "md_in_html",
    "footnotes",
    "admonition",
    "toc",
    "pymdownx.superfences",
    "pymdownx.details",
    "pymdownx.inlinehilite",
    "pymdownx.highlight",
    "pymdownx.arithmatex",
    "pymdownx.snippets",
    "pymdownx.magiclink",
    "pymdownx.tasklist",
    "pymdownx.caret",
    "pymdownx.tilde",
]

def _mermaid_fence(source, language, class_name, options, md, **kwargs):
    """pymdownx calls custom fences with five positional args. Escape the source:
    Mermaid reads textContent, so entities decode back to the original text."""
    return f'<pre class="mermaid">{html.escape(source)}</pre>'


def _pseudo_fence(source, language, class_name, options, md, **kwargs):
    """A pseudocode block: escaped, no syntax colouring, labelled as such."""
    return (
        '<div class="code"><div class="code-head"><span class="code-lang">pseudocode</span></div>'
        f"<pre><code>{html.escape(source)}</code></pre>"
        '<button class="code-copy" type="button">Copy</button></div>'
    )


EXT_CONFIGS = {
    "toc": {"permalink": "", "toc_depth": "2-3", "anchorlink": False},
    "pymdownx.highlight": {
        "use_pygments": True,
        "css_class": "highlight",
        "linenums": False,
        "anchor_linenums": False,
        "pygments_lang_class": True,
    },
    "pymdownx.superfences": {
        "custom_fences": [
            {"name": "mermaid", "class": "mermaid", "format": _mermaid_fence},
            {"name": "pseudo", "class": "pseudo", "format": _pseudo_fence},
        ]
    },
    # inline math uses \( \) only: a single $ is a currency symbol in this
    # manual, and "$3 ... $4" was being parsed as an equation.
    "pymdownx.arithmatex": {
        "generic": True,
        "inline_syntax": ["round"],
        "block_syntax": ["dollar", "square", "begin"],
    },
    "pymdownx.tasklist": {"custom_checkbox": True},
}


def convert(text: str) -> tuple[str, str, list[dict]]:
    """Markdown -> (html, toc_html, toc_tokens)."""
    md = markdown.Markdown(extensions=EXTENSIONS, extension_configs=EXT_CONFIGS)
    body = md.convert(text)
    return body, md.toc, md.toc_tokens


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def strip_title(text: str) -> str:
    """Drop the leading H1: the template renders the title itself."""
    return re.sub(r"^#\s+.+?\n", "", text, count=1, flags=re.MULTILINE)


def rewrite_links(body: str, src_rel: str, base: str) -> str:
    """Resolve every relative link against the *source* file, then emit an
    absolute URL.

    Directory-style output (/chapters/01-x/) sits one level deeper than the
    source file (chapters/01-x.md), so a relative link copied verbatim would
    resolve one directory too shallow. Absolute URLs sidestep that entirely.
    """
    src_dir = (DOCS / src_rel).parent

    def sub(m: re.Match) -> str:
        target, frag = m.group(1), m.group(2) or ""
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return m.group(0)
        if target.startswith("/"):
            return m.group(0)

        resolved = (src_dir / target).resolve()
        try:
            rel = resolved.relative_to(DOCS.resolve()).as_posix()
        except ValueError:
            return m.group(0)

        if rel.endswith(".md"):
            rel = rel[:-3]
        if rel.endswith("index"):
            rel = rel[: -len("index")]
        url = f"{base}/{rel}/".replace("//", "/")
        return f'href="{url}{frag}"'

    return re.sub(r'href="([^"]+\.md)(#[^"]*)?"', sub, body)


def flatten_toc(tokens: list[dict], depth: int = 2) -> list[dict]:
    out = []
    for t in tokens:
        if t["level"] <= depth + 1:
            out.append({"id": t["id"], "name": re.sub(r"<[^>]+>", "", t["name"]), "level": t["level"]})
        out.extend(flatten_toc(t.get("children", []), depth))
    return out


DIAGRAM_KINDS = [
    ("sequencediagram", "sequence"),
    ("statediagram", "state machine"),
    ("erdiagram", "entity relationships"),
    ("gantt", "schedule"),
    ("classdiagram", "class diagram"),
    ("pie", "breakdown"),
    ("flowchart", "flow chart"),
    ("graph", "flow chart"),
]


def diagram_kind(src: str) -> str:
    head = src.strip().split("\n", 1)[0].lower().replace(" ", "")
    for key, label in DIAGRAM_KINDS:
        if head.startswith(key):
            return label
    return "diagram"


def find_div_end(s: str, start: int) -> int:
    """Index just past the </div> that closes the <div> at `start`, or -1."""
    i = start + 4
    depth = 1
    while depth > 0:
        nxt_open = s.find("<div", i)
        nxt_close = s.find("</div>", i)
        if nxt_close == -1:
            return -1
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 4
        else:
            depth -= 1
            i = nxt_close + 6
    return i


# The theme styles the card on `.ann`; a variant class only sets the colour
# variables, so both are required -- `class="ann ann-warn"`, never `ann-warn`.
ADMON_CLASSES = {
    "note": "ann", "info": "ann", "abstract": "ann", "summary": "ann", "tldr": "ann",
    "tip": "ann ann-tip", "hint": "ann ann-tip", "success": "ann ann-tip", "check": "ann ann-tip",
    "warning": "ann ann-warn", "caution": "ann ann-warn", "attention": "ann ann-warn",
    "danger": "ann ann-warn", "error": "ann ann-warn", "failure": "ann ann-warn",
    "bug": "ann ann-warn",
    "example": "ann ann-example",
    "quote": "ann ann-key", "cite": "ann ann-key", "question": "ann ann-key",
}


def restyle_admonitions(body: str) -> str:
    """pymdownx admonition markup -> the reference site's .ann callout cards."""
    out, i = [], 0
    while True:
        j = body.find('<div class="admonition ', i)
        if j == -1:
            out.append(body[i:])
            break
        out.append(body[i:j])
        m = re.match(r'<div class="admonition ([a-z]+)">', body[j:])
        kind = m.group(1)
        tag = m.group(0)
        end = find_div_end(body, j)
        if end == -1:
            out.append(body[j:])
            break
        inner = body[j + len(tag):end - 6]
        title = ""
        tm = re.match(r'\s*<p class="admonition-title">(.*?)</p>', inner, re.S)
        if tm:
            title = tm.group(1)
            inner = inner[tm.end():]
        cls = ADMON_CLASSES.get(kind, "ann")
        label = f"<b>{title}</b>" if title else ""
        out.append(f'<div class="{cls}">{label}<div class="md">{inner.strip()}</div></div>')
        i = end
    return "".join(out)


def wrap_code(pre: str, lang: str) -> str:
    label = lang or "output"
    return (
        f'<div class="code"><div class="code-head"><span class="code-lang">{label}</span></div>'
        f'{pre}<button class="code-copy" type="button">Copy</button></div>'
    )


def restyle_code(body: str) -> str:
    body = re.sub(
        r'<div class="language-([\w+#-]+) highlight">(<pre>.*?</pre>)</div>',
        lambda m: wrap_code(m.group(2), m.group(1)),
        body, flags=re.S,
    )
    body = re.sub(
        r'<div class="highlight">(<pre>.*?</pre>)</div>',
        lambda m: wrap_code(m.group(1), ""),
        body, flags=re.S,
    )
    return body


def wrap_tables(body: str) -> str:
    return body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


def add_figures(body: str) -> tuple[str, int]:
    """Wrap every diagram in the reference site's .fig card, numbered per page."""
    counter = iter(range(1, 1000))

    def sub(m: re.Match) -> str:
        inner = m.group(1)
        n = next(counter)
        kind = diagram_kind(html.unescape(inner))
        return (
            f'<figure class="fig mermaid-fig"><div class="mermaid-out">{m.group(0)}</div>'
            f"<figcaption><span>Fig. {n}</span> <em>{kind}</em></figcaption></figure>"
        )

    body = re.sub(r'<pre class="mermaid">(.*?)</pre>', sub, body, flags=re.S)
    return body, next(counter) - 1


def decorate(body: str) -> tuple[str, int]:
    body, figs = add_figures(body)
    body = restyle_admonitions(body)
    body = restyle_code(body)
    body = wrap_tables(body)
    return body, figs


def plain_text(body_html: str) -> str:
    txt = re.sub(r"<pre.*?</pre>", " ", body_html, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", html.unescape(txt)).strip()


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    env = Environment(
        loader=FileSystemLoader(str(BUILDER / "templates")),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # static assets
    shutil.copytree(BUILDER / "assets", OUT / "assets")

    index_entries: list[dict] = []
    flat_pages: list[dict] = []

    # --- home ---
    home_src = (DOCS / "index.md").read_text()
    home_body, _, _ = convert(strip_title(home_src))
    home_body, _ = decorate(rewrite_links(home_body, "index.md", SITE["base"]))

    # --- pass 1: every page needs its url before any page renders (prev/next) ---
    for sec in SECTIONS:
        for i, page in enumerate(sec["pages"]):
            text = (DOCS / page["src"]).read_text()
            page["title"] = page.get("title") or title_of(text, page["src"])
            page["url"] = page["src"][:-3] + "/"
            page["section"] = sec["id"]
            # the sidebar number column is 26px wide: chapters 01-09, foundations
            # 01-03, appendices A-C. The card kicker can stay descriptive.
            page["num"] = re.sub(r"^(Model|Plate)\s+", "", page.get("kicker", ""))
            page["section_label"] = sec["label"]
            page["prev"] = sec["pages"][i - 1] if i > 0 else None
            page["next"] = sec["pages"][i + 1] if i + 1 < len(sec["pages"]) else None

    # --- pass 2: render ---
    for sec in SECTIONS:
        for page in sec["pages"]:
            src = DOCS / page["src"]
            text = src.read_text()
            body, toc_html, tokens = convert(strip_title(text))
            body, figs = decorate(rewrite_links(body, page["src"], SITE["base"]))
            page["figs"] = figs
            page["words"] = len(re.findall(r"\w+", plain_text(body)))
            page["toc"] = flatten_toc(tokens)
            page["h2s"] = sum(1 for t in page["toc"] if t["level"] == 2)
            flat_pages.append(page)

            html_out = env.get_template("page.html").render(
                site=SITE,
                sections=SECTIONS,
                page=page,
                body=body,
                section=sec,
                themes=THEMES,
            )
            dest = OUT / page["url"] / "index.html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html_out)

            index_entries.append(
                {
                    "u": "/" + page["url"],
                    "t": page["title"],
                    "s": page["section_label"],
                    "k": page.get("meta", page.get("kicker", "")),
                    "b": plain_text(body)[:600],
                    "h": [t["name"] for t in page["toc"]],
                }
            )

    total_figs = sum(p.get("figs", 0) for p in flat_pages)
    # count the source markdown, so the number includes code and configs
    total_words = sum(
        len(re.findall(r"\w+", f.read_text())) for f in DOCS.rglob("*.md")
    )
    stats = [
        (f"{len(flat_pages):02d}", "chapters and appendices"),
        (str(total_figs), "numbered figures"),
        (str(repo_file_count()), "files in the repo"),
        (f"{round(total_words / 1000)}k", "words of walkthrough"),
    ]

    def pages_of(section_id: str) -> list[dict]:
        return next((sec["pages"] for sec in SECTIONS if sec["id"] == section_id), [])

    home = env.get_template("home.html").render(
        site=SITE,
        sections=SECTIONS,
        stats=stats,
        body=home_body,
        themes=THEMES,
        chapter_pages=pages_of("chapters"),
        ai_pages=pages_of("ai"),
        foundation_pages=pages_of("foundations"),
        appendix_pages=pages_of("appendices"),
    )
    (OUT / "index.html").write_text(home)

    # --- 404 ---
    (OUT / "404.html").write_text(
        env.get_template("404.html").render(site=SITE, sections=SECTIONS, themes=THEMES)
    )

    # --- search index ---
    (OUT / "search-index.json").write_text(json.dumps(index_entries, ensure_ascii=False))

    # --- sitemap ---
    urls = [SITE["url"] + "/"] + [SITE["url"] + "/" + p["url"] for p in flat_pages]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
        + "\n</urlset>\n"
    )

    # --- robots ---
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE['url']}/sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")

    print(f"built {len(flat_pages)} pages + home -> {OUT}")
    for p in flat_pages:
        print(f"  /{p['url']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    args = ap.parse_args()
    build()
    if args.serve:
        import functools
        import http.server
        import socketserver

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        with socketserver.TCPServer(("127.0.0.1", 8000), handler) as httpd:
            print("serving http://127.0.0.1:8000")
            httpd.serve_forever()
