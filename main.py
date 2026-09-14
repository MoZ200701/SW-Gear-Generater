"""Entry point for PyInstaller and for double-clicking this file directly."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from gear_generator.gui import main

if __name__ == "__main__":
    main()
