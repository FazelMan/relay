"""Dashboard CLI wiring tests (no network server started)."""
from __future__ import annotations

import unittest
from unittest import mock

from relay.cli import main


class DashboardCliTests(unittest.TestCase):
    def test_dashboard_uses_localhost_defaults(self) -> None:
        with mock.patch("relay.cli.serve_dashboard") as serve:
            code = main(["dashboard"])
        self.assertEqual(code, 0)
        serve.assert_called_once_with(".", host="127.0.0.1", port=8765)

    def test_dashboard_passes_workspace_host_and_port(self) -> None:
        with mock.patch("relay.cli.serve_dashboard") as serve:
            code = main(["dashboard", "--workspace", "/tmp/project", "--host", "127.0.0.1", "--port", "8766"])
        self.assertEqual(code, 0)
        serve.assert_called_once_with("/tmp/project", host="127.0.0.1", port=8766)


if __name__ == "__main__":
    unittest.main()
