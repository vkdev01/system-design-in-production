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
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BUILDER = ROOT / "site_builder"
OUT = ROOT / "dist"

SITE = {
    "title": "System Design in Production",
    "tagline": "Nine production systems, rebuilt from first principles.",
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
                "title": "The 7-step method",
                "kicker": "Model 03",
                "blurb": "The shape every chapter follows, plus the timed structure of a 45-minute system design interview.",
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
                "blurb": "Nine condensed two-minute answers, the follow-up matrix, one break-it command per chapter, and a 45-minute mock.",
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

STATS = [
    ("09", "production systems"),
    ("18", "flow charts"),
    ("126", "files in the repo"),
    ("23k", "words of walkthrough"),
]

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
        ]
    },
    "pymdownx.arithmatex": {"generic": True},
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

    # pygments: a light palette and a dark one, scoped by selector prefix
    light = HtmlFormatter(style="friendly").get_style_defs(".highlight")
    dark = HtmlFormatter(style="monokai").get_style_defs('[data-theme="dark"] .highlight')
    (OUT / "assets" / "code.css").write_text(light + "\n" + dark)

    index_entries: list[dict] = []
    flat_pages: list[dict] = []

    # --- home ---
    home_src = (DOCS / "index.md").read_text()
    home_body, _, _ = convert(strip_title(home_src))
    home_body = rewrite_links(home_body, "index.md", SITE["base"])

    # --- pass 1: every page needs its url before any page renders (prev/next) ---
    for sec in SECTIONS:
        for i, page in enumerate(sec["pages"]):
            text = (DOCS / page["src"]).read_text()
            page["title"] = page.get("title") or title_of(text, page["src"])
            page["url"] = page["src"][:-3] + "/"
            page["section"] = sec["id"]
            page["section_label"] = sec["label"]
            page["prev"] = sec["pages"][i - 1] if i > 0 else None
            page["next"] = sec["pages"][i + 1] if i + 1 < len(sec["pages"]) else None

    # --- pass 2: render ---
    for sec in SECTIONS:
        for page in sec["pages"]:
            src = DOCS / page["src"]
            text = src.read_text()
            body, toc_html, tokens = convert(strip_title(text))
            body = rewrite_links(body, page["src"], SITE["base"])
            page["toc"] = flatten_toc(tokens)
            flat_pages.append(page)

            html_out = env.get_template("page.html").render(
                site=SITE,
                sections=SECTIONS,
                page=page,
                body=body,
                section=sec,
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

    home = env.get_template("home.html").render(
        site=SITE,
        sections=SECTIONS,
        stats=STATS,
        body=home_body,
    )
    (OUT / "index.html").write_text(home)

    # --- 404 ---
    (OUT / "404.html").write_text(
        env.get_template("404.html").render(site=SITE, sections=SECTIONS)
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
