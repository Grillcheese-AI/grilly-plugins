from broker.indexer.python_ast import index_python_source


def test_extracts_functions_and_classes():
    src = '''
def foo(x, y):
    """Add two numbers."""
    return x + y

class Bar:
    """A bar."""
    def baz(self):
        return 1
'''
    entries = index_python_source(src, file_path="demo.py", file_mtime=0.0)
    kinds = {(e.symbol, e.kind) for e in entries}
    assert ("foo", "function") in kinds
    assert ("Bar", "class") in kinds
    assert ("Bar.baz", "method") in kinds


def test_summary_uses_docstring():
    src = 'def foo():\n    """hello world"""\n    return 1\n'
    entries = index_python_source(src, file_path="x.py", file_mtime=0.0)
    foo = next(e for e in entries if e.symbol == "foo")
    assert "hello world" in foo.summary


def test_keywords_include_name_tokens():
    src = 'def verify_token(jwt):\n    return True\n'
    entries = index_python_source(src, file_path="x.py", file_mtime=0.0)
    foo = next(e for e in entries if e.symbol == "verify_token")
    assert "verify" in foo.keywords
    assert "token" in foo.keywords
