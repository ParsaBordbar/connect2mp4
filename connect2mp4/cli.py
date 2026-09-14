"""Command-line entry point."""
import argparse
import os
import sys

from . import __version__
from .console import RED, color, is_tty, log
from .ffmpeg import require_tools
from .options import Options
from .pipeline import process_recording
from .util import natural_key, parse_size

USAGE = """\
Export an Adobe Connect recording to a single MP4 (slides + whiteboard + audio).

Examples:
    connect2mp4                                                     # no args -> interactive TUI
    connect2mp4 https://vc2.shirazu.ac.ir/pquxl04g15ys/              # recording link
    connect2mp4 ~/Downloads/last.zip                                # downloaded zip
    connect2mp4 ~/Downloads/zips/                                   # folder of zips
    connect2mp4 last.zip --slides "Learning Theory=~/Downloads/09- Learning Theory-2.pdf"
    connect2mp4 last.zip --slides p7v19xnp88eb=~/slides.pptx        # key = sco id or part of name

Requires: ffmpeg, ffprobe, Pillow; pdftoppm (poppler) for PDF; LibreOffice (soffice) for PPTX.
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="connect2mp4", description=USAGE,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", help="recording URL(s), zip file(s) or folder(s) of zips")
    ap.add_argument("-o", "--out", default="connect_out", metavar="DIR", help="output directory (default: ./connect_out)")
    ap.add_argument("--slides", action="append", default=[], metavar="KEY=FILE",
                    help="slide file for shared document KEY (part of its name, or its sco id). "
                         "FILE = .pdf, .pptx (needs LibreOffice) or a folder of PNGs. Repeatable. "
                         "Without it the source file is downloaded from the server, else numbered blank slides are drawn.")
    ap.add_argument("--host", metavar="URL", help="server base (e.g. https://vc2.shirazu.ac.ir) for slide download when input is a zip")
    ap.add_argument("--cookie", metavar="S", help="raw Cookie header (BREEZESESSION=...) if the server wants login")
    ap.add_argument("--insecure", action="store_true", help="skip TLS certificate verification (old university servers)")
    ap.add_argument("--camera", action="store_true", help="prefer webcam video over screen share")
    ap.add_argument("--size", default="1280x960", metavar="WxH", help="output size (default 1280x960, 4:3 like the share pod)")
    ap.add_argument("--fps", type=int, default=10, help="output frame rate (default 10)")
    ap.add_argument("--crf", type=int, default=26, help="x264 quality (default 26)")
    ap.add_argument("--keep", action="store_true", help="keep extracted files and rendered frames")
    ap.add_argument("--version", action="version", version=f"connect2mp4 {__version__}")
    return ap


def options_from_args(args: argparse.Namespace) -> Options:
    bad = [s for s in args.slides if "=" not in s]
    if bad:
        sys.exit(f"--slides expects KEY=FILE, got: {bad}")
    try:
        width, height = parse_size(args.size)
    except ValueError as e:
        sys.exit(str(e))
    return Options(
        targets=args.targets,
        out_dir=args.out,
        slides=[tuple(s.split("=", 1)) for s in args.slides],
        host=args.host.rstrip("/") if args.host else None,
        cookie=args.cookie,
        insecure=args.insecure,
        camera=args.camera,
        width=width,
        height=height,
        fps=args.fps,
        crf=args.crf,
        keep=args.keep,
    )


def expand_targets(targets: list[str]) -> list[str]:
    """Folders become the list of zips inside them; everything else is passed through."""
    expanded = []
    for t in targets:
        t = os.path.expanduser(t)
        if os.path.isdir(t):
            zips = [os.path.join(t, f) for f in sorted(os.listdir(t), key=natural_key) if f.lower().endswith(".zip")]
            if not zips:
                log("no .zip files in", t)
            expanded += zips
        else:
            expanded.append(t)
    return expanded


def run(opts: Options) -> None:
    require_tools()
    os.makedirs(opts.out_dir, exist_ok=True)
    failed = 0
    for target in expand_targets(opts.targets):
        try:
            process_recording(target, opts)
        except KeyboardInterrupt:
            print()
            return
        except Exception as e:
            failed += 1
            log(color("FAILED", RED), target, "->", e)
    if failed:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv and is_tty():
        from .tui import interactive_setup
        try:
            opts = interactive_setup()
        except KeyboardInterrupt:
            print()
            return
        if opts is None:
            return
    else:
        opts = options_from_args(build_parser().parse_args(argv))
    run(opts)
