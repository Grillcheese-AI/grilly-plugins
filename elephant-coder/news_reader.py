"""RSS/Atom feed reader with HTML extraction and deduplication. Stdlib + httpx only."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

_NS_ATOM = "http://www.w3.org/2005/Atom"


def _tag(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_rss_xml(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 or Atom XML into list of {title, link, summary, published}."""
    root = ET.fromstring(xml_text)
    tag = root.tag.lower()

    # Atom feed
    if "atom" in tag or root.tag == _tag(_NS_ATOM, "feed"):
        return _parse_atom(root)

    # RSS 2.0 — root is <rss> or <rdf:RDF>; channel items live under <channel>
    channel_found = root.find("channel")
    channel = channel_found if channel_found is not None else root
    return _parse_rss_items(channel)


def _parse_rss_items(channel: ET.Element) -> list[dict]:
    articles = []
    for item in channel.findall("item"):
        link_el = item.find("link")
        # <link> may be text node or CDATA
        link = _text(link_el)
        # Some feeds use <link> with no text but a tail
        if not link and link_el is not None:
            link = (link_el.tail or "").strip()
        desc = _text(item.find("description"))
        articles.append({
            "title": _text(item.find("title")),
            "link": link,
            "summary": strip_html(desc),
            "published": _text(item.find("pubDate")),
        })
    return articles


def _parse_atom(root: ET.Element) -> list[dict]:
    ns = _NS_ATOM
    articles = []
    for entry in root.findall(_tag(ns, "entry")):
        link_el = entry.find(_tag(ns, "link"))
        link = ""
        if link_el is not None:
            link = link_el.get("href", "") or _text(link_el)
        summary_el = entry.find(_tag(ns, "summary"))
        if summary_el is None:
            summary_el = entry.find(_tag(ns, "content"))
        published_el = entry.find(_tag(ns, "published")) or entry.find(_tag(ns, "updated"))
        articles.append({
            "title": _text(entry.find(_tag(ns, "title"))),
            "link": link,
            "summary": strip_html(_text(summary_el)),
            "published": _text(published_el),
        })
    return articles


# ---------------------------------------------------------------------------
# HTML utilities
# ---------------------------------------------------------------------------

_BLOCK_TAG_RE = re.compile(
    r"<(script|style|nav|header|footer|noscript)[\s>].*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(html: str) -> str:
    """Remove block tags + content, strip remaining tags, collapse whitespace."""
    text = _BLOCK_TAG_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def truncate_text(text: str, max_chars: int = 2000) -> str:
    """Truncate at word boundary, appending '...' if truncated."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated + "..."


# ---------------------------------------------------------------------------
# HTTP fetching
# ---------------------------------------------------------------------------

def fetch_feed(url: str, timeout: int = 10) -> str:
    """GET url, return response text."""
    import httpx
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "grilly-news-reader/1.0"})
        resp.raise_for_status()
        return resp.text


def fetch_full_article(url: str, timeout: int = 15) -> str:
    """GET article, extract text from <article>/<main>/<body>, strip HTML, truncate."""
    import httpx
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "grilly-news-reader/1.0"})
        resp.raise_for_status()
        html = resp.text

    # Try to find best content container
    for tag in ("article", "main", "body"):
        m = re.search(rf"<{tag}[\s>].*?</{tag}>", html, re.IGNORECASE | re.DOTALL)
        if m:
            return truncate_text(strip_html(m.group()), 2000)
    return truncate_text(strip_html(html), 2000)


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

def fetch_feeds(urls: list[str], max_per_feed: int = 5) -> list[dict]:
    """Fetch and parse multiple feeds, tagging each article with source_feed."""
    articles: list[dict] = []
    for url in urls:
        try:
            xml_text = fetch_feed(url)
            items = parse_rss_xml(xml_text)[:max_per_feed]
            for item in items:
                item.setdefault("source_feed", url)
            articles.extend(items)
        except Exception:
            pass
    return articles


def deduplicate_articles(articles: list[dict], existing_urls: set[str]) -> list[dict]:
    """Filter articles whose link appears in existing_urls."""
    seen: set[str] = set(existing_urls)
    result = []
    for art in articles:
        link = art.get("link", "")
        if link and link not in seen:
            seen.add(link)
            result.append(art)
    return result


def generate_briefing(articles: list[dict], max_articles: int = 20) -> str:
    """Format articles as a plain-text news briefing."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"News Briefing — {now}", "=" * 60, ""]
    for i, art in enumerate(articles[:max_articles], 1):
        title = art.get("title", "(no title)")
        link = art.get("link", "")
        summary = art.get("summary", "")
        source = art.get("source_feed", "")
        published = art.get("published", "")

        lines.append(f"{i}. {title}")
        if link:
            lines.append(f"   {link}")
        if source and source != link:
            lines.append(f"   Source: {source}")
        if published:
            lines.append(f"   Published: {published}")
        if summary:
            lines.append(f"   {truncate_text(summary, 300)}")
        lines.append("")
    return "\n".join(lines)
