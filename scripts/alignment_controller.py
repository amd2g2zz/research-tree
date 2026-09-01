#!/usr/bin/env python3
"""Source-checkout entry point for the SQLite alignment graph controller."""

from research_tree.alignment_graph import *  # noqa: F403
from research_tree.alignment_graph import main

if __name__ == "__main__":
    raise SystemExit(main())
