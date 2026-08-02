"""
Thin launcher for the Financial Strategy Tracker.

PyInstaller targets this file as the entry point.  It invokes Streamlit's
CLI programmatically so the bundled app can be started without a separate
`streamlit` command on the PATH.
"""

import sys
import os
import traceback


def main():
    try:
        from streamlit.web import cli as stcli

        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")

        if not os.path.exists(app_path):
            print(f"ERROR: Cannot find app.py at: {app_path}")
            input("Press Enter to exit...")
            sys.exit(1)

        sys.argv = [
            "streamlit",
            "run",
            app_path,
            "--server.headless=false",
            "--browser.gatherUsageStats=false",
        ]
        stcli.main()
    except Exception:
        traceback.print_exc()
        print("\n--- Application failed to start ---")
        input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
