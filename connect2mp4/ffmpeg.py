"""Everything that shells out to ffmpeg / ffprobe."""
import json
import os
import shutil
import subprocess
import sys

from .console import log
from .model import MediaPart, ProbeInfo, Segment
from .options import Options


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            hint = "brew install ffmpeg" if sys.platform == "darwin" else "sudo apt install -y ffmpeg"
            sys.exit(f"{tool} not found. Install: {hint}")


def probe(path: str) -> ProbeInfo:
    """One ffprobe call -> duration and stream presence."""
    info = ProbeInfo()
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                              "-show_streams", path], capture_output=True, text=True).stdout
        data = json.loads(out or "{}")
        info.duration = float(data.get("format", {}).get("duration") or 0)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                info.has_audio = True
            elif stream.get("codec_type") == "video":
                info.has_video = True
                info.width = max(info.width, int(stream.get("width") or 0))
                info.height = max(info.height, int(stream.get("height") or 0))
    except Exception as e:
        log(f"ffprobe failed on {os.path.basename(path)}: {e}")
    return info


def _audio_graph(audio_parts: list[MediaPart], total_s: float, first_index: int) -> tuple[list[str], list[str]]:
    """Inputs + filter steps that mix all audio parts at their offsets into [aout]."""
    inputs, filters, labels = [], [], []
    for i, part in enumerate(audio_parts):
        inputs += ["-i", part.path]
        ms = int(part.offset_s * 1000)
        filters.append(f"[{first_index + i}:a]aresample=async=1:first_pts=0,"
                       f"aformat=sample_rates=44100:channel_layouts=mono,adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    if not labels:
        filters.append(f"anullsrc=r=44100:cl=mono:d={total_s:.3f}[aout]")
    elif len(labels) == 1:
        filters.append(f"{labels[0]}apad=whole_dur={total_s:.3f}[aout]")
    else:
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
                       f"apad=whole_dur={total_s:.3f}[aout]")
    return inputs, filters


def _encode(video_inputs: list[str], video_filters: list[str], audio_parts: list[MediaPart],
            total_s: float, out_path: str, opts: Options) -> None:
    n_video_inputs = video_inputs.count("-i")
    audio_inputs, audio_filters = _audio_graph(audio_parts, total_s, n_video_inputs)
    cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "warning", "-stats",
           *video_inputs, *audio_inputs,
           "-filter_complex", ";".join(video_filters + audio_filters), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(opts.crf), "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "64k", "-t", f"{total_s:.3f}", "-movflags", "+faststart", out_path]
    log("ffmpeg encoding ...")
    subprocess.run(cmd, check=True)


def encode_slideshow(segments: list[Segment], audio_parts: list[MediaPart], total_s: float,
                     list_path: str, out_path: str, opts: Options) -> None:
    """Rendered frames (concat demuxer) + audio -> mp4."""
    with open(list_path, "w") as f:
        for seg in segments:
            f.write(f"file '{seg.png}'\nduration {seg.duration_s:.3f}\n")
        f.write(f"file '{segments[-1].png}'\n")  # concat demuxer needs the last file repeated
    inputs = ["-f", "concat", "-safe", "0", "-i", list_path]
    filters = [f"[0:v]fps={opts.fps},format=yuv420p[vout]"]
    _encode(inputs, filters, audio_parts, total_s, out_path, opts)


def encode_screenshare(video_parts: list[MediaPart], audio_parts: list[MediaPart], total_s: float,
                       out_path: str, opts: Options) -> None:
    """Screen share / webcam FLVs overlaid on a black canvas at their offsets + audio -> mp4."""
    W = max(p.info.width for p in video_parts)
    H = max(p.info.height for p in video_parts)
    if not W or not H:
        W, H = opts.size
    scale = min(1.0, 1280 / W, 960 / H)
    W, H = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
    inputs: list[str] = []
    filters = [f"color=c=black:s={W}x{H}:r={opts.fps}:d={total_s:.3f}[base]"]
    last = "[base]"
    for i, part in enumerate(video_parts):
        inputs += ["-i", part.path]
        filters.append(f"[{i}:v]fps={opts.fps},scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuva420p,"
                       f"tpad=start_duration={part.offset_s:.3f}:color=black@0.0,setpts=PTS-STARTPTS[v{i}]")
        filters.append(f"{last}[v{i}]overlay=eof_action=pass:shortest=0[o{i}]")
        last = f"[o{i}]"
    filters.append(f"{last}format=yuv420p[vout]")
    _encode(inputs, filters, audio_parts, total_s, out_path, opts)
