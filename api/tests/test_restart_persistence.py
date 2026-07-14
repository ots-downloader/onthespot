import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from _support import SRC_ROOT


class RestartPersistenceTests(unittest.TestCase):
    def _run_process(self, source: str, root: Path) -> dict:
        environment = os.environ.copy()
        environment.update(
            {
                "ONTHESPOTDIR": str(root / "config"),
                "ONTHESPOTCACHEDIR": str(root / "cache"),
                "HOME": str(root / "home"),
                "USERPROFILE": str(root / "home"),
                "PYTHONPATH": str(SRC_ROOT),
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_settings_and_playlist_automation_survive_a_new_process(self):
        with tempfile.TemporaryDirectory(prefix="onthespot-restart-test-") as directory:
            root = Path(directory)
            export_directory = root / "exports"

            written = self._run_process(
                f"""
                import json
                from onthespot.otsconfig import config
                from onthespot.playlist_automation import playlist_automation

                config.set("language", "fr_FR")
                config.set("export_folder_path", {str(export_directory)!r})
                config.save()
                playlist_automation.save_config({{
                    "id": "restart-config",
                    "name": "Restart probe",
                    "target_playlist_id": "target",
                    "source_playlist_ids": ["source"],
                }}, "restart-config")
                playlist_automation.save_schedule({{
                    "id": "restart-schedule",
                    "config_id": "restart-config",
                    "cron_expression": "0 5 * * *",
                    "enabled": True,
                }})
                playlist_automation.ignore({{
                    "track_id": "restart-track",
                    "name": "Restart Track",
                    "artist": "OnTheSpot",
                }})
                print(json.dumps({{"saved": True}}))
                """,
                root,
            )
            self.assertTrue(written["saved"])

            restored = self._run_process(
                """
                import json
                from pathlib import Path
                from onthespot.otsconfig import config
                from onthespot.playlist_automation import playlist_automation

                print(json.dumps({
                    "language": config.get("language"),
                    "export_folder_path": config.get("export_folder_path"),
                    "config_ids": [row.get("id") for row in playlist_automation.configs()],
                    "schedule_ids": [row.get("id") for row in playlist_automation.schedules()],
                    "ignored_track_ids": [row.get("track_id") for row in playlist_automation.ignored()],
                    "config_file": Path(config._Config__cfg_path).is_file(),
                    "automation_state_file": Path(playlist_automation._state_path).is_file(),
                }))
                """,
                root,
            )

            self.assertEqual(restored["language"], "fr_FR")
            self.assertEqual(restored["export_folder_path"], str(export_directory))
            self.assertIn("restart-config", restored["config_ids"])
            self.assertIn("restart-schedule", restored["schedule_ids"])
            self.assertIn("restart-track", restored["ignored_track_ids"])
            self.assertTrue(restored["config_file"])
            self.assertTrue(restored["automation_state_file"])


if __name__ == "__main__":
    unittest.main()
