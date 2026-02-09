# pipeline/block_analyze.py
"""Compatibility wrapper.

This project previously had two divergent copies of the block analyzer:
- block_analyze.py (project root)
- pipeline/block_analyze.py

The canonical implementation is now the root-level `block_analyze.py`.
"""

from block_analyze import *  # noqa: F401,F403
