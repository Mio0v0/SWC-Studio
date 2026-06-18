from __future__ import annotations

import unittest

from swcstudio.core.install_check import check_installation


class InstallationCheckTests(unittest.TestCase):
    def test_full_installation_check_loads_every_production_model(self) -> None:
        report = check_installation(load_models=True)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["gui"]["ok"])
        self.assertTrue(all(row["ok"] for row in report["dependencies"]))
        self.assertTrue(all(row["ok"] for row in report["configs"]))
        self.assertTrue(all(row["loaded"] is True for row in report["models"]))


if __name__ == "__main__":
    unittest.main()
