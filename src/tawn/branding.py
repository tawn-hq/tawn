"""Branded terminal identity (brand/README.md: Cairn × Sandstone & Lapis).

The cairn: three stones, lapis capstone. The wordmark lettering follows
the drawn monoline mark — rounded, lowercase, final n in lapis.
Colors are the brand tokens; Rich truecolor degrades gracefully.
"""

from rich.columns import Columns
from rich.console import Group
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

# brand tokens (brand/tokens.css) — dark-ground values; terminals are
# usually dark, and both lapis values pass on light too.
LAPIS = "#4A7BC8"
BONE = "#EFE9DC"
MUTED = "#ADA28C"

_CAIRN = [
    ("   ▄██▄   ", LAPIS),
    ("   ▀██▀   ", LAPIS),
    ("  ▄████▄  ", BONE),
    ("  ▀████▀  ", BONE),
    (" ▄██████▄ ", BONE),
    (" ▀██████▀ ", BONE),
]

# monoline block lettering — t a w in bone, n in lapis (the letter that
# makes it *own*), matching the wordmark rule in brand/README.md
_LETTERS = [
    ("▄█▄  ▄▀▀▄  █   █  ", "█▀▀▄"),
    (" █   █▄▄█  █ ▄ █  ", "█  █"),
    (" ▀▄  █  █  ▀▄▀▄▀  ", "█  █"),
]


def cairn() -> Text:
    art = Text()
    for i, (line, color) in enumerate(_CAIRN):
        art.append(line, style=color)
        if i < len(_CAIRN) - 1:
            art.append("\n")
    return art


def wordmark() -> Text:
    art = Text()
    for i, (taw, n) in enumerate(_LETTERS):
        art.append(taw, style=f"bold {BONE}")
        art.append(n, style=f"bold {LAPIS}")
        if i < len(_LETTERS) - 1:
            art.append("\n")
    return art


def banner(version: str) -> Group:
    lockup = Columns([cairn(), Padding(wordmark(), (1, 0, 0, 2))], padding=(0, 2))
    tag = Text()
    tag.append("the twin you own", style=f"italic {MUTED}")
    tag.append(f"  ·  v{version}", style=MUTED)
    return Group(lockup, Padding(tag, (0, 0, 0, 1)))


def status_table(rows: list[tuple[str, bool, str]]) -> Table:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style=MUTED)
    t.add_column()
    t.add_column(style=MUTED)
    for name, ok, detail in rows:
        mark = Text("●", style="green" if ok else "red")
        t.add_row(name, mark, detail)
    return t


def commands_table(commands: list[tuple[str, str]]) -> Table:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style=f"bold {LAPIS}")
    t.add_column(style=MUTED)
    for cmd, desc in commands:
        t.add_row(cmd, desc)
    return t
