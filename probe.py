"""Run the SolidWorks API probe: ``python probe.py`` on Windows, beside SolidWorks.

From WSL use ``./probe.sh``; from a Windows shell ``probe.bat``. Both land here.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from gear_generator.probe.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
