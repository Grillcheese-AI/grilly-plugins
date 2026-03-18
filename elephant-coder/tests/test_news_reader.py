import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from news_reader import parse_rss_xml, strip_html, truncate_text, deduplicate_articles, generate_briefing

SAMPLE_RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item>
<title>Article One</title>
<link>https://example.com/article-1</link>
<description>This is the first article summary.</description>
<pubDate>Mon, 17 Mar 2026 10:00:00 GMT</pubDate>
</item>
<item>
<title>Article Two</title>
<link>https://example.com/article-2</link>
<description>&lt;p&gt;HTML in description&lt;/p&gt;</description>
</item>
</channel>
</rss>'''

SAMPLE_ATOM = '''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Feed</title>
<entry>
<title>Atom Article</title>
<link href="https://example.com/atom-1"/>
<summary>Atom summary text.</summary>
</entry>
</feed>'''


def test_parse_rss():
    articles = parse_rss_xml(SAMPLE_RSS)
    assert len(articles) == 2
    assert articles[0]["title"] == "Article One"
    assert articles[0]["link"] == "https://example.com/article-1"
    assert "first article" in articles[0]["summary"]


def test_parse_atom():
    articles = parse_rss_xml(SAMPLE_ATOM)
    assert len(articles) >= 1
    assert articles[0]["title"] == "Atom Article"


def test_strip_html():
    html = "<p>Hello <b>world</b></p><script>evil()</script><style>.x{}</style>"
    text = strip_html(html)
    assert "Hello" in text
    assert "world" in text
    assert "evil" not in text
    assert ".x" not in text


def test_truncate_text():
    text = "word " * 1000  # 5000 chars
    result = truncate_text(text, max_chars=100)
    assert len(result) <= 103  # 100 + "..."
    assert result.endswith("...")


def test_deduplicate():
    articles = [
        {"title": "A", "link": "https://example.com/1"},
        {"title": "B", "link": "https://example.com/2"},
        {"title": "C", "link": "https://example.com/3"},
    ]
    existing = {"https://example.com/1", "https://example.com/3"}
    result = deduplicate_articles(articles, existing)
    assert len(result) == 1
    assert result[0]["title"] == "B"


def test_generate_briefing():
    articles = [
        {"title": "Test Article", "link": "https://example.com/1", "summary": "Something happened.", "source_feed": "Test"},
    ]
    briefing = generate_briefing(articles)
    assert "Test Article" in briefing
    assert "example.com" in briefing
