"""Interactive terminal front-end: arrow-key menus, slide file picker and the start-up wizard."""
import difflib
import glob
import os
import re
import sys
import zipfile
from urllib.parse import urlparse

from .config import APP_DIR, load_config, save_config
from .console import BOLD, CORAL, DIM, HIDE_CURSOR, RED, SHOW_CURSOR, ask, banner, color, is_tty
from .model import Content
from .options import Options
from .slides import CHOICE_CACHED, CHOICE_DOWNLOAD, CHOICE_NONE

DEFAULT_HOST = "https://vc2.shirazu.ac.ir"
SEARCH_DIRS = ("~/Downloads", "~/Desktop", "~/Documents")
IGNORED_TOKENS = {"pdf", "pptx", "ppt", "v2", "v1"}


def select(title: str, options: list[tuple[str, str]], default: int = 0) -> int:
    """Arrow-key menu. options: list of (label, description). Returns the chosen index.

    Up/down or j/k move, enter selects, q raises KeyboardInterrupt. Falls back to `default`
    when not attached to a terminal.
    """
    import termios
    import tty

    if not is_tty() or not options:
        return default
    idx = max(0, min(default, len(options) - 1))
    label_w = min(60, max(len(o[0]) for o in options))
    total_lines = len(options) + 2

    def render(first: bool) -> None:
        if not first:
            sys.stdout.write(f"\033[{total_lines}A")
        lines = [color(title, BOLD)]
        for i, (label, desc) in enumerate(options):
            label = label if len(label) <= 60 else "…" + label[-59:]
            if i == idx:
                row = color("❯ ", CORAL, BOLD) + color(f"{label:<{label_w}}", CORAL, BOLD) + color(f"  {desc}", DIM)
            else:
                row = "  " + f"{label:<{label_w}}" + color(f"  {desc}", DIM)
            lines.append(f" {row}")
        lines.append(color("↑/↓ move · enter select · q quit", DIM))
        sys.stdout.write("".join(f"\r{ln}\033[K\r\n" for ln in lines))
        sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    sys.stdout.write(HIDE_CURSOR)
    try:
        tty.setraw(fd)
        first = True
        while True:
            render(first)
            first = False
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    idx = (idx - 1) % len(options)
                elif seq == "[B":
                    idx = (idx + 1) % len(options)
            elif ch in ("\r", "\n"):
                break
            elif ch in ("q", "\x03"):
                raise KeyboardInterrupt
            elif ch == "k":
                idx = (idx - 1) % len(options)
            elif ch == "j":
                idx = (idx + 1) % len(options)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(SHOW_CURSOR)
    print()
    return idx


# ---------------------------------------------------------------- slide picker
def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t and t not in IGNORED_TOKENS}


def _similarity(doc_name: str, file_base: str) -> float:
    a, b = _tokens(doc_name), _tokens(file_base)
    token_score = len(a & b) / max(1, len(a))
    text_score = difflib.SequenceMatcher(None, doc_name.lower(), file_base.lower()).ratio()
    return token_score * 0.7 + text_score * 0.3


def candidate_slide_files(doc_name: str, extra_dirs=(), limit: int = 8) -> list[str]:
    """Search likely folders for pdf/pptx whose name resembles the document; best match first."""
    dirs = [os.getcwd(), *(os.path.expanduser(d) for d in SEARCH_DIRS), *extra_dirs]
    seen, found = set(), []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for depth in ("*", "*/*", "*/*/*", "*/*/*/*", "*/*/*/*/*"):
            for ext in ("pdf", "pptx", "ppt"):
                for f in glob.glob(os.path.join(d, depth + "." + ext)):
                    if f in seen or "/." in f or "node_modules" in f or "slides_cache" in f:
                        continue
                    seen.add(f)
                    score = _similarity(doc_name, os.path.splitext(os.path.basename(f))[0])
                    if score >= 0.35:
                        found.append((score, f))
    found.sort(key=lambda x: -x[0])
    return [f for _, f in found[:limit]]


def _remember_slide_dir(cfg: dict, path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    dirs = cfg.setdefault("slide_dirs", [])
    if d not in dirs:
        dirs.insert(0, d)
        save_config(cfg)


def pick_slides(content: Content, cfg: dict, host: str | None = None, cached: int = 0) -> str:
    """Ask which slide file to use. Returns a path, CHOICE_CACHED, CHOICE_DOWNLOAD or CHOICE_NONE."""
    name = content.name or "document"
    print(color("  document shown in class: ", DIM) + color(name, BOLD))
    candidates = candidate_slide_files(name, cfg.get("slide_dirs", []))
    home = os.path.expanduser("~")
    options: list[tuple[str, str]] = []
    if cached:
        options.append(("cached slides", f"{cached} pages rendered earlier"))
    options += [(os.path.basename(f), os.path.dirname(f).replace(home, "~")) for f in candidates]
    options.append(("type a path…", "pdf / pptx / folder of png"))
    if host:
        options.append(("download from server", host))
    options.append(("no slides", "white pages + pen strokes only"))

    i = select("Slide file for this document:", options, 0)
    label = options[i][0]
    if label == "cached slides":
        return CHOICE_CACHED
    if label == "download from server":
        return CHOICE_DOWNLOAD
    if label == "no slides":
        return CHOICE_NONE
    if label == "type a path…":
        path = ask("path to pdf/pptx")
        while path and not os.path.exists(path):
            print(color("  not found: " + path, RED))
            path = ask("path to pdf/pptx")
    else:
        path = candidates[i - (1 if cached else 0)]
    if path:
        _remember_slide_dir(cfg, path)
    return path


# ---------------------------------------------------------------- start-up wizard
def _is_recording_zip(path: str) -> bool:
    try:
        return os.path.getsize(path) > 0 and "mainstream.xml" in zipfile.ZipFile(path).namelist()
    except Exception:
        return False


def _local_recording_zips(limit: int = 8) -> list[str]:
    """Recording zips dropped into the app directory, newest first."""
    zips = [os.path.join(APP_DIR, f) for f in os.listdir(APP_DIR) if f.lower().endswith(".zip")]
    zips = sorted(zips, key=lambda p: -os.path.getmtime(p))[:30]
    return [z for z in zips if _is_recording_zip(z)][:limit]


def interactive_setup() -> Options | None:
    """Ask what to convert and where to put it. Returns None if the user quits."""
    banner()
    cfg = load_config()
    zips = _local_recording_zips()
    options = [("recording link", f"{DEFAULT_HOST}/xxxx/"), ("zip path or folder", "type / drag a path")]
    options += [(os.path.basename(z), f"{os.path.getsize(z)/1e6:.0f} MB · next to script") for z in zips]
    i = select("What to convert?", options, 0)

    host = cfg.get("host") or ""
    if i >= 2:
        targets = [zips[i - 2]]
    elif i == 0:
        url = ask("recording link", cfg.get("last_url", ""))
        if not url:
            return None
        targets = [url]
        cfg["last_url"] = url
        host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    else:
        path = ask("zip file or folder")
        if not path or not os.path.exists(path):
            print(color("  not found: " + str(path), RED))
            return None
        targets = [path]

    if not host and not targets[0].startswith("http"):
        host = ask("server address (for slide download, enter to skip)", DEFAULT_HOST)
    if host and not host.startswith("http"):
        print(color("  ignoring server address (must start with http): " + host, DIM))
        host = ""
    cfg["host"] = host
    out_dir = ask("output folder", cfg.get("out", os.path.join(APP_DIR, "connect_out")))
    cfg["out"] = out_dir
    save_config(cfg)
    print()
    return Options(targets=targets, out_dir=out_dir, host=host.rstrip("/") or None, interactive=True, config=cfg)
