"""Guard: the offline pipeline must never import any google package.

(agent.py is the only module that imports google.adk, and it is deliberately
excluded here — it requires the [agent] extra.)
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]

CHECK = """
import sys
import opportunity_radar.brief
import opportunity_radar.cli
import opportunity_radar.radar
import opportunity_radar.scoring
import opportunity_radar.sources
import opportunity_radar.state
import opportunity_radar.tools
bad = [m for m in sys.modules if m == "google" or m.startswith("google.")]
assert not bad, f"offline modules pulled in google packages: {bad}"
print("clean")
"""


def test_offline_modules_import_no_google():
    proc = subprocess.run(
        [sys.executable, "-c", CHECK], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert proc.returncode == 0, proc.stderr
    assert "clean" in proc.stdout
