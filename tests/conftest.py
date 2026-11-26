"""Shared test setup: the game modules live at the repo root, while the
tests live in tests/ (per game) — put the repo root on sys.path so
`import bot`, `import game_registry`, ... keep working."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
