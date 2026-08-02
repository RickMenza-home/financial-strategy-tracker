"""
Thin launcher for the Financial Strategy Tracker.

PyInstaller targets this file as the entry point.  It invokes Streamlit's
CLI programmatically so the bundled app can be started without a separate
`streamlit` command on the PATH.
"""

import os
import sys

from streamlit.web import cli as stcli

if __name__ == "__main__":
    app_path = os.path.join(os.path.dirname(__file__), "app.py")
    sys.argv = ["streamlit", "run", app_path, "--server.headless=true"]
    sys.exit(stcli.main())
