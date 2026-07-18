import unittest

from _support import API_ROOT


REPOSITORY_ROOT = API_ROOT.parent


class DeploymentContractTests(unittest.TestCase):
    def test_compose_uses_portable_single_process_layout(self):
        compose = (REPOSITORY_ROOT / "compose.yml").read_text(encoding="utf-8")

        self.assertIn('${ONTHESPOT_WEB_PORT:-6767}:6767', compose)
        self.assertIn("/root/.config/onthespot", compose)
        self.assertIn("ONTHESPOTCACHEDIR: /root/.config/onthespot/cache", compose)
        self.assertNotIn("network_mode: host", compose)

    def test_image_builds_ui_and_serves_it_from_fastapi(self):
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM node:22-alpine AS ui-builder", dockerfile)
        self.assertIn("RUN npm install --no-audit --no-fund", dockerfile)
        self.assertIn("RUN npm run build", dockerfile)
        self.assertIn("uv sync --no-install-project --no-dev", dockerfile)
        self.assertIn("COPY --from=ui-builder /ui/dist /app/ui/dist", dockerfile)
        self.assertIn("ONTHESPOT_WEBUI_DIST=/app/ui/dist", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn(
            'CMD ["/app/.venv/bin/python", "-m", "uvicorn", "onthespot.main:app", "--app-dir", "/app/app", '
            '"--host", "0.0.0.0", "--port", "6767"]',
            dockerfile,
        )

    def test_private_runtime_data_is_excluded_from_image_context(self):
        dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")

        ignored_entries = set(dockerignore.splitlines())
        self.assertIn(".env", ignored_entries)
        self.assertIn("otsdata", ignored_entries)
        self.assertIn("**/.venv", ignored_entries)
        self.assertNotIn("api/uv.lock", ignored_entries)
        self.assertNotIn("ui/package-lock.json", ignored_entries)


if __name__ == "__main__":
    unittest.main()
