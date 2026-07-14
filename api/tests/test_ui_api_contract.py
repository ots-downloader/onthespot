import re
import unittest
from pathlib import Path

from _support import TEST_ROOT  # noqa: F401

from onthespot.main import app  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_CLIENT_PATH = REPOSITORY_ROOT / "ui" / "src" / "lib" / "api.ts"
NOTIFICATIONS_PATH = REPOSITORY_ROOT / "ui" / "src" / "lib" / "notifications.tsx"


def _client_paths() -> set[str]:
    source = API_CLIENT_PATH.read_text(encoding="utf-8")
    matches = re.finditer(
        r'(?:request|getEndpoint)\(\s*(?:`([^`]+)`|"([^"]+)")',
        source,
    )
    paths = set()
    for match in matches:
        path = next(group for group in match.groups() if group is not None)
        path = path.split("?", 1)[0]
        path = re.sub(r"\$\{(?:qParam|suffix)\}$", "", path)
        path = re.sub(r"\$\{[^}]+\}", "{value}", path)
        paths.add(path)

    notification_source = NOTIFICATIONS_PATH.read_text(encoding="utf-8")
    if "/api/sse/${userId}" in notification_source:
        paths.add("/api/sse/{value}")
    return paths


def _route_pattern(path: str) -> re.Pattern[str]:
    escaped = re.escape(path)
    escaped = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{escaped}$")


class UiApiContractTests(unittest.TestCase):
    def test_every_frontend_api_path_exists_in_fastapi(self):
        server_patterns = [
            _route_pattern(route.path)
            for route in app.routes
            if getattr(route, "path", None)
        ]
        unmatched = sorted(
            path
            for path in _client_paths()
            if not any(pattern.fullmatch(path) for pattern in server_patterns)
        )
        self.assertEqual(unmatched, [], f"Frontend paths missing from FastAPI: {unmatched}")


if __name__ == "__main__":
    unittest.main()
