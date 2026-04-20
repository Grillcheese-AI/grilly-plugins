from broker.protocol import Request, Response, encode, decode


def test_request_roundtrip():
    req = Request(op="recall", args={"query": "hello", "limit": 5})
    wire = encode(req)
    assert isinstance(wire, bytes)
    assert wire.endswith(b"\n")
    back = decode(wire)
    assert isinstance(back, Request)
    assert back.op == "recall"
    assert back.args == {"query": "hello", "limit": 5}


def test_response_ok_roundtrip():
    r = Response(ok=True, data={"items": [1, 2, 3]})
    back = decode(encode(r))
    assert back.ok is True
    assert back.data["items"] == [1, 2, 3]


def test_response_err_roundtrip():
    r = Response(ok=False, error="boom")
    back = decode(encode(r))
    assert back.ok is False
    assert back.error == "boom"
