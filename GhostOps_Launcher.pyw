"""Double click to open the Ghost Ops launcher (no console window). Errors are written to %APPDATA%\GhostOps\launcher.log."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))

import gui_launcher  # noqa: E402

if __name__ == '__main__':
    sys.exit(gui_launcher.main())
