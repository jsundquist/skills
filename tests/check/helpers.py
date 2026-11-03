from lib import Repo


class FakeRepo(Repo):
    """The real Repo with only the network replaced: files and API answers come from dicts."""

    def __init__(self, files=None, api_data=None, info=None):
        super().__init__("o/r")
        self._files = dict(files or {})
        self.info = {"default_branch": "main", **(info or {})}
        self.tree = sorted(self._files)
        self.api_data = api_data or {}

    def api(self, path, *flags):
        return self.api_data.get(path)

    def api_ok(self, path):
        return self.api_data.get(path) is not None


def messages(results, status=None):
    results = results if isinstance(results, list) else [results]  # a check may return one Result or a list
    return [r.message for r in results if status is None or r.status == status]
