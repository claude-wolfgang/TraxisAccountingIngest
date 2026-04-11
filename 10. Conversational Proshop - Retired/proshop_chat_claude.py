#!/usr/bin/env python3
"""
ProShop Conversational Interface - Claude-Powered Edition
Launch script. Run this from the project root.

Usage:
    python proshop_chat_claude.py                          # Interactive mode
    python proshop_chat_claude.py "status of 25-0001"      # Single query
    python proshop_chat_claude.py --debug "status of 25-0001"  # Debug mode
"""

import sys
import os

# Fix Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# Load API key from sibling project .env if not set
if not os.environ.get("ANTHROPIC_API_KEY"):
    env_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "11. Proshop Mobile App", "proshop-mobile-backend", ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]
                    break

from cli_claude import main, single_query

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a not in ["--debug", "-d"]]
    debug = "--debug" in sys.argv or "-d" in sys.argv

    if args:
        query = " ".join(args)
        print(single_query(query, debug=debug))
    else:
        main()
