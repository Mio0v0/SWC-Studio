from __future__ import annotations

import unittest
from unittest.mock import patch

from swcstudio.core.install_check import check_installation, format_installation_report


class InstallationCheckTests(unittest.TestCase):
    def test_full_installation_check_loads_every_production_model(self) -> None:
        report = check_installation(load_models=True)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["gui"]["ok"])
        self.assertTrue(all(row["ok"] for row in report["dependencies"]))
        self.assertTrue(all(row["ok"] for row in report["configs"]))
        self.assertTrue(all(row["loaded"] is True for row in report["models"]))

    def test_repair_command_uses_checked_python_executable(self) -> None:
        with patch(
            "swcstudio.core.install_check.check_installation",
        ):
            report = {
                "ok": False,
                "swcstudio_version": "0.2.0",
                "python": "3.12.0",
                "supported_python": ">=3.10,<3.13",
                "python_ok": True,
                "platform": "test",
                "executable": "/tmp/swc env/bin/python",
                "dependencies": [],
                "configs": [],
                "models": [],
                "gui": {"ok": True, "error": None},
            }
            text = format_installation_report(report)
        self.assertIn('"/tmp/swc env/bin/python" -m pip install', text)


if __name__ == "__main__":
    unittest.main()
