"""Per-recording flow: obtain zip -> extract -> parse -> render/encode -> mp4."""
import os
import re
import shutil
import tempfile
import zipfile

from .console import BOLD, GREEN, color, log
from .ffmpeg import encode_screenshare, encode_slideshow, probe
from .model import Content, Event, MediaPart, Stream
from .net import fetch, recording_zip_url
from .options import Options
from .parsing import parse_ftcontent, parse_mainstream
from .render import render_frames
from .slides import resolve_slides

STREAM_FILE_RE = re.compile(r"^(cameraVoip|screenshare)_(\d+)_(\d+)\.flv$", re.I)
FTCONTENT_RE = re.compile(r"ftcontent\d*\.xml$")


def obtain_zip(target: str, opts: Options) -> tuple[str, str, str | None]:
    """URL or local zip -> (zip path, recording id, host). Downloads once, reuses on re-runs."""
    if target.startswith(("http://", "https://")):
        host, rec_id, zip_url = recording_zip_url(target)
        zip_path = os.path.join(opts.out_dir, rec_id + ".zip")
        if os.path.isfile(zip_path) and zipfile.is_zipfile(zip_path):
            log("zip already present:", zip_path)
        else:
            log("downloading", zip_url)
            try:
                fetch(zip_url, zip_path, opts, expect_zip=True)
            except Exception as e:
                raise RuntimeError(f"download failed: {e}\n  open {zip_url} in your browser, save the zip, "
                                   f"then run: connect2mp4 <zip> --host {host}")
        return zip_path, rec_id, host
    if not os.path.isfile(target):
        raise RuntimeError(f"file not found: {target}")
    if not zipfile.is_zipfile(target):
        raise RuntimeError(f"not a zip file: {target}")
    return target, os.path.splitext(os.path.basename(target))[0], opts.host


def scan_media(work: str, streams: list[Stream]) -> dict[str, list[MediaPart]]:
    """Probe every cameraVoip_*/screenshare_* FLV. Offsets come from mainstream.xml, falling back
    to the timestamp in the file name."""
    parts: dict[str, list[MediaPart]] = {"cameraVoip": [], "screenshare": []}
    by_name = {s.name: s for s in streams}
    for f in os.listdir(work):
        m = STREAM_FILE_RE.match(f)
        if not m:
            continue
        path = os.path.join(work, f)
        info = probe(path)
        if info.duration <= 0:
            log(f"warning: skipping {f} (unreadable or empty)")
            continue
        stream = by_name.get(f[:-4])
        offset_s = stream.start_ms / 1000.0 if stream else int(m.group(3)) / 1000.0
        kind = "cameraVoip" if m.group(1).lower() == "cameravoip" else "screenshare"
        parts[kind].append(MediaPart(path=path, offset_s=offset_s, info=info))
    for kind in parts:
        parts[kind].sort(key=lambda p: p.offset_s)
    return parts


def load_share_pod_events(work: str) -> list[Event]:
    events: list[Event] = []
    for f in sorted(os.listdir(work)):
        if FTCONTENT_RE.match(f):
            events += parse_ftcontent(os.path.join(work, f))
    events.sort(key=lambda e: e.time_ms)
    return events


def build_from_slides(work: str, contents: dict[str, Content], audio_parts: list[MediaPart],
                      total_ms: int, out_path: str, opts: Options, host: str | None) -> None:
    events = load_share_pod_events(work)
    if events:
        total_ms = max(total_ms, events[-1].time_ms + 1000)  # share-pod log may outlast mainstream
    cache_dir = os.path.join(opts.out_dir, "slides_cache")
    slides: dict[str, list[str]] = {}
    shown = sorted({e.ct_id for e in events if hasattr(e, "ct_id")})
    for ct_id in shown:
        content = contents.get(ct_id) or Content(ct_id=ct_id)
        log(f"document shown: '{content.name or '?'}'  sco={content.sco or '?'} / {content.sco_src or '?'}")
        slides[ct_id] = resolve_slides(content, opts, host, cache_dir)
    segments = render_frames(events, contents, slides, total_ms, opts.width, opts.height,
                             os.path.join(work, "frames"))
    encode_slideshow(segments, audio_parts, total_ms / 1000.0, os.path.join(work, "frames.txt"), out_path, opts)


def process_recording(target: str, opts: Options) -> None:
    zip_path, rec_id, host = obtain_zip(target, opts)
    out_mp4 = os.path.join(opts.out_dir, rec_id + ".mp4")
    work = tempfile.mkdtemp(prefix="connect2mp4_")
    try:
        log("extracting", zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(work)
        mainstream = os.path.join(work, "mainstream.xml")
        if os.path.exists(mainstream):
            streams, contents, last_ms = parse_mainstream(mainstream)
        else:
            log("warning: no mainstream.xml in zip, is this an Adobe Connect recording?")
            streams, contents, last_ms = [], {}, 0

        parts = scan_media(work, streams)
        audio_parts = [p for p in parts["cameraVoip"] if p.info.has_audio]
        video_parts = [p for p in parts["screenshare"] if p.info.has_video]
        if opts.camera:
            video_parts = [p for p in parts["cameraVoip"] if p.info.has_video] or video_parts
        total_ms = max([last_ms] + [int(p.end_s * 1000) for p in audio_parts + video_parts])
        log(f"audio parts: {len(audio_parts)}, screen/cam video parts: {len(video_parts)}, "
            f"length {total_ms/60000:.1f} min")

        if video_parts:
            encode_screenshare(video_parts, audio_parts, total_ms / 1000.0, out_mp4, opts)
        else:
            build_from_slides(work, contents, audio_parts, total_ms, out_mp4, opts, host)
        log(color("done ->", GREEN, BOLD), out_mp4)
    finally:
        if opts.keep:
            log("kept work dir", work)
        else:
            shutil.rmtree(work, ignore_errors=True)
