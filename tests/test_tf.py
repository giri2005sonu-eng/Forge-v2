from core import tf

class Boom:
    """Fake client whose first fetch fails like a closed httpx client, then works."""
    def __init__(self): self.n = 0
    class fetch:
        pass

def test_call_retries_once_when_client_closed():
    tf._C = object()
    calls = []
    def fn():
        calls.append(1)
        if len(calls) == 1: raise RuntimeError("Cannot send a request, as the client has been closed.")
        return "ok"
    assert tf._call(fn) == "ok" and len(calls) == 2 and tf._C is None

def test_call_does_not_swallow_other_errors():
    import pytest
    with pytest.raises(RuntimeError): tf._call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
