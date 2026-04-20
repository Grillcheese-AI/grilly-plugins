import time
import pytest
from broker.server import BrokerServer
from broker.client import BrokerClient
from broker.protocol import Request


@pytest.fixture
def broker(tmp_path, monkeypatch):
    monkeypatch.setenv("EC2_HOME", str(tmp_path))
    handlers = {
        "ping": lambda args: {"pong": True, "echo": args.get("x")},
        "boom": lambda args: (_ for _ in ()).throw(RuntimeError("nope")),
    }
    srv = BrokerServer(handlers=handlers, host="127.0.0.1", port=0)
    srv.start()
    for _ in range(50):
        if srv.port:
            break
        time.sleep(0.02)
    yield srv
    srv.stop()


def test_ping(broker):
    client = BrokerClient(port=broker.port)
    rsp = client.call(Request(op="ping", args={"x": 42}))
    assert rsp.ok is True
    assert rsp.data["pong"] is True
    assert rsp.data["echo"] == 42


def test_unknown_op(broker):
    client = BrokerClient(port=broker.port)
    rsp = client.call(Request(op="doesnotexist"))
    assert rsp.ok is False
    assert "unknown op" in rsp.error.lower()


def test_handler_exception_returns_error(broker):
    client = BrokerClient(port=broker.port)
    rsp = client.call(Request(op="boom"))
    assert rsp.ok is False
    assert "nope" in rsp.error


def test_port_file_written(broker, tmp_path):
    port_file = tmp_path / "broker.port"
    assert port_file.exists()
    assert int(port_file.read_text().strip()) == broker.port
