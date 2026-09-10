"""Prompt loader. Prompts are versioned as plain-text files (doc §13.3:
'app/prompts/  Router, SQL, Analyst, Narrator (versioned)') so they can be
diffed and rolled back independently of application code.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """name is the file stem, e.g. 'router', 'sql_generator', 'analyst',
    'narrator', 'disambiguation'.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt template named '{name}' in {_PROMPTS_DIR}")
    return path.read_text()
