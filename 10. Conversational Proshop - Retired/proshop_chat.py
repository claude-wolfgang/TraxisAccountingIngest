#!/usr/bin/env python3
"""
ProShop Chat - Convenience launcher for the conversational interface.
Run from the project root: python proshop_chat.py
"""

import sys
import os

# Add src directory to path
src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, src_dir)

from cli import main, single_query

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] not in ["--debug", "-d"]:
        # Single query mode
        query = " ".join(arg for arg in sys.argv[1:] if arg not in ["--debug", "-d"])
        debug = "--debug" in sys.argv or "-d" in sys.argv
        print(single_query(query, debug=debug))
    else:
        # Interactive mode
        main()
