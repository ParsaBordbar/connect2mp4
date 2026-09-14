"""HTTP download of recordings and slide sources, with optional TLS fallback for old servers."""
import os
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .console import RED, ask, color, is_tty
from .options import Options


class TLSError(RuntimeError):
    """Certificate problem the user did not allow us to ignore."""


def ssl_context(insecure: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        except Exception:
            pass
    return ctx


def recording_zip_url(recording_url: str) -> tuple[str, str, str]:
    """https://server/<id>/ -> (host, recording id, zip download url)."""
    u = urlparse(recording_url)
    segments = [p for p in u.path.split("/") if p]
    if u.scheme not in ("http", "https") or not u.netloc or not segments:
        raise RuntimeError(f"not a recording link: {recording_url}  (expected https://server/<id>/)")
    rec_id = segments[0]
    host = f"{u.scheme}://{u.netloc}"
    return host, rec_id, f"{host}/{rec_id}/output/{rec_id}.zip?download=zip"


def fetch(url: str, dest: str, opts: Options, expect_zip: bool = False) -> None:
    """Download url -> dest atomically (.part + rename).

    Raises TLSError on certificate problems unless opts.insecure. In interactive mode the user is
    asked once whether to continue without verification; a "yes" flips opts.insecure for the run.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    if opts.cookie:
        headers["Cookie"] = opts.cookie
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    while True:
        try:
            _download(url, part, headers, ssl_context(opts.insecure), expect_zip)
            break
        except (ssl.SSLError, urllib.error.URLError) as e:
            reason = getattr(e, "reason", e)
            if opts.insecure or not isinstance(reason, ssl.SSLError):
                raise
            if opts.interactive and is_tty():
                print(color(f"  TLS problem talking to the server: {reason}", RED))
                if ask("continue WITHOUT certificate verification? (y/N)", "n").lower().startswith("y"):
                    opts.insecure = True
                    continue
            raise TLSError(f"TLS certificate problem ({reason}). Re-run with --insecure to skip verification.")
    os.replace(part, dest)


def _download(url: str, part: str, headers: dict, ctx: ssl.SSLContext, expect_zip: bool) -> None:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r, open(part, "wb") as f:
            head = r.read(8)
            ctype = r.headers.get("Content-Type", "")
            if (expect_zip and not head.startswith(b"PK")) or "text/html" in ctype:
                raise RuntimeError("server returned HTML (login page?) instead of a file")
            f.write(head)
            total, done = int(r.headers.get("Content-Length") or 0), len(head)
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                print(f"\r  {done/1e6:8.1f} MB" + (f" / {total/1e6:.1f} MB" if total else ""), end="", flush=True)
            print()
            if total and done != total:
                raise RuntimeError(f"incomplete download ({done} of {total} bytes)")
    except BaseException:
        if os.path.exists(part):
            os.remove(part)
        raise
