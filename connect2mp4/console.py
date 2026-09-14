"""Terminal output: colours, logging, banner and the basic text prompt."""
import os
import sys

CORAL = "\033[38;2;215;119;87m"
GREEN = "\033[38;2;126;186;125m"
RED = "\033[38;2;224;108;117m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def color(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes when stdout is a terminal, otherwise return it unchanged."""
    return "".join(codes) + text + RESET if sys.stdout.isatty() else text


def log(*parts) -> None:
    print("[connect2mp4]", *parts, flush=True)


def banner() -> None:
    if not sys.stdout.isatty():
        return
    inner = 38
    line = "─" * inner
    plain = "connect2mp4 · Adobe Connect → MP4"
    title = f"{BOLD}connect2mp4{RESET}{CORAL} · Adobe Connect → MP4"
    print(color(f"╭{line}╮", CORAL))
    print(color("│ ", CORAL) + title + color(" " * (inner - 1 - len(plain)) + "│", CORAL))
    print(color(f"╰{line}╯", CORAL))
    print()


def ask(prompt: str, default: str = "") -> str:
    """Prompt for a line of text. Strips quotes and escaped spaces (drag-and-drop paths), expands ~."""
    hint = color(f" [{default}]", DIM) if default else ""
    try:
        value = input(color("? ", CORAL, BOLD) + prompt + hint + ": ").strip()
    except EOFError:
        value = ""
    value = value.strip("'\"").replace("\\ ", " ")
    return os.path.expanduser(value) if value else default
