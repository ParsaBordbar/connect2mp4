"""Locate and rasterize the slide files shown in the share pod (pdf / pptx / folder of png)."""
import os
import re
import shutil
import subprocess
import urllib.parse

from .console import log
from .model import Content
from .net import TLSError, fetch
from .options import Options
from .util import natural_key

SLIDE_PNG_RE = re.compile(r"^slide.*\.png$")
OFFICE_EXTENSIONS = (".ppt", ".pptx", ".odp", ".doc", ".docx", ".key")
SOFFICE_PATHS = ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/lib/libreoffice/program/soffice")

# choices returned by the interactive picker besides a real path
CHOICE_CACHED = "__cached__"
CHOICE_DOWNLOAD = "__download__"
CHOICE_NONE = ""


def find_tool(*names: str) -> str | None:
    for name in names:
        if path := shutil.which(name):
            return path
    if "soffice" in names:
        for path in SOFFICE_PATHS:
            if os.path.exists(path):
                return path
    return None


def list_slide_pngs(folder: str) -> list[str]:
    return sorted((os.path.join(folder, f) for f in os.listdir(folder) if SLIDE_PNG_RE.match(f)), key=natural_key)


def rasterize(src: str, out_dir: str, width: int) -> list[str]:
    """pdf / pptx / folder of png -> list of png paths in page order.

    out_dir is rebuilt from scratch and gets a .complete marker (holding the width) so that a
    half-finished render is never mistaken for a full one.
    """
    src = os.path.expanduser(src)
    if os.path.isdir(src):
        pngs = sorted((os.path.join(src, f) for f in os.listdir(src)
                       if f.lower().endswith((".png", ".jpg", ".jpeg"))), key=natural_key)
        if not pngs:
            raise RuntimeError("no png/jpg files in " + src)
        return pngs
    if not os.path.isfile(src):
        raise RuntimeError("slide file not found: " + src)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    pdf = _to_pdf(src, out_dir)
    pdftoppm = find_tool("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm missing: brew install poppler")
    subprocess.run([pdftoppm, "-png", "-scale-to-x", str(width), "-scale-to-y", "-1", pdf,
                    os.path.join(out_dir, "slide")], check=True)
    pngs = list_slide_pngs(out_dir)
    if not pngs:
        raise RuntimeError("pdftoppm produced no pages from " + src)
    with open(os.path.join(out_dir, ".complete"), "w") as f:
        f.write(str(width))
    return pngs


def _to_pdf(src: str, out_dir: str) -> str:
    ext = os.path.splitext(src)[1].lower()
    if ext == ".pdf":
        return src
    if ext not in OFFICE_EXTENSIONS:
        raise RuntimeError("unsupported slide file " + src)
    soffice = find_tool("soffice", "libreoffice")
    if not soffice:
        raise RuntimeError(f"{os.path.basename(src)} is not a PDF and LibreOffice is not installed. "
                           "Either 'brew install --cask libreoffice' or export it to PDF and pass that.")
    log("converting to pdf with LibreOffice ...")
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, src],
                   check=True, capture_output=True)
    return os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf")


def _cached_pngs(out_dir: str, width: int) -> list[str]:
    marker = os.path.join(out_dir, ".complete")
    if not os.path.isfile(marker):
        return []
    with open(marker) as f:
        if f.read().strip() != str(width):
            return []
    return list_slide_pngs(out_dir)


def resolve_slides(content: Content, opts: Options, host: str | None, cache_dir: str) -> list[str]:
    """Returns the PNG pages for a document, or [] if unavailable.

    Priority: explicit --slides > interactive picker > complete cache > download from server > none.
    """
    name = content.name
    sco_ids = content.sco_ids
    sco = sco_ids[0] if sco_ids else ""
    width = opts.width
    out_dir = os.path.join(cache_dir, sco or re.sub(r"\W+", "_", name) or "unnamed")
    cached = _cached_pngs(out_dir, width)

    for key, path in opts.slides:                                   # 1. explicit
        if key.lower() in name.lower() or key in sco_ids or key == content.ct_id:
            log(f"slides for '{name}': {path}")
            return rasterize(path, out_dir, width)
    if opts.interactive:                                            # 2. ask
        from .tui import pick_slides
        choice = pick_slides(content, opts.config, host if sco_ids else None, len(cached))
        if choice == CHOICE_CACHED:
            return cached
        if choice == CHOICE_NONE:
            return []
        if choice != CHOICE_DOWNLOAD:
            return rasterize(choice, out_dir, width)
    elif cached:                                                    # 3. cache
        log(f"using cached slides for '{name}' ({len(cached)} pages) from {out_dir}")
        return cached
    if host and sco_ids and name:                                   # 4. server
        if pngs := _download_slides(content, opts, host, cache_dir, out_dir):
            return pngs
    else:
        log(f"no slides for '{name}' (pass --slides '{sco or name}=file.pdf' or --host https://server)")
    return []


def _download_slides(content: Content, opts: Options, host: str, cache_dir: str, out_dir: str) -> list[str]:
    name = content.name
    dest = os.path.join(cache_dir, name)
    quoted = urllib.parse.quote(name)
    urls = [f"{host}/{s}/output/{quoted}?download={quoted}" for s in content.sco_ids]
    for url in urls:
        try:
            log("downloading slides", url)
            fetch(url, dest, opts)
            return rasterize(dest, out_dir, opts.width)
        except TLSError as e:
            log(f"  failed: {e}")
            break
        except Exception as e:
            log(f"  failed: {e}")
    log(f"could not get slides for '{name}' from server. Try these in your browser (logged in):")
    for url in urls:
        log("   ", url)
    log(f"  then rerun with:  --slides '{content.sco_ids[0]}=/path/to/downloaded/file'")
    return []
