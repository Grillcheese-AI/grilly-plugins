from broker.indexer.regex_extract import index_ts_source, index_c_source
from broker.indexer.structured import index_markdown, index_toml


def test_ts_functions_and_classes():
    src = '''
export function verify(token: string): boolean { return true; }
export class AuthClient {
  connect() {}
}
'''
    entries = index_ts_source(src, "auth.ts", 0.0)
    syms = {e.symbol for e in entries}
    assert "verify" in syms
    assert "AuthClient" in syms


def test_c_functions():
    src = '''
int add(int a, int b) { return a + b; }
static void helper(void) { }
'''
    entries = index_c_source(src, "a.c", 0.0)
    syms = {e.symbol for e in entries}
    assert "add" in syms
    assert "helper" in syms


def test_markdown_headings():
    md = "# Title\n\nIntro.\n\n## Section A\n\nContent A\n\n## Section B\n\nContent B\n"
    entries = index_markdown(md, "x.md", 0.0)
    syms = [e.symbol for e in entries]
    assert "Title" in syms
    assert "Section A" in syms
    assert "Section B" in syms


def test_toml_tables():
    t = "[project]\nname = 'x'\n[tool.pytest]\nstrict = true\n"
    entries = index_toml(t, "pyproject.toml", 0.0)
    syms = {e.symbol for e in entries}
    assert "project" in syms
    assert "tool.pytest" in syms
