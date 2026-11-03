import contextlib
import io

from lib import Run


def make_run(**overrides):
    run = Run(repo="o/r", apply=True, codeowner="@o", **overrides)
    run.info = {"default_branch": "main", "visibility": "public"}
    return run


@contextlib.contextmanager
def quiet():
    """Swallow the step output the code prints, and hand it back for assertions."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer


class FakeApi:
    """Stands in for api_get/api_send. `get` maps a substring of the endpoint to a response."""

    def __init__(self, get=None, send_ok=True):
        self.get_map = get or {}
        self.send_ok = send_ok
        self.sent = []

    def api_get(self, endpoint):
        for needle, response in self.get_map.items():
            if needle in endpoint:
                return response
        return None

    def api_send(self, method, endpoint, body=None):
        self.sent.append((method, endpoint, body))
        return (True, "") if self.send_ok else (False, "boom")
