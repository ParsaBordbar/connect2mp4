import os

import pytest

from connect2mp4.cli import build_parser, options_from_args
from connect2mp4.model import Content, ContentEvent, MediaPart, ProbeInfo, Shape, ShapeAdded, SlideEvent
from connect2mp4.ffmpeg import _audio_graph
from connect2mp4.net import recording_zip_url
from connect2mp4.render import render_frames
from connect2mp4.util import natural_key, parse_size


def test_parse_size():
    assert parse_size("1280x960") == (1280, 960)
    assert parse_size(" 641X481 ") == (640, 480)
    with pytest.raises(ValueError):
        parse_size("big")


def test_natural_key():
    names = ["slide-10.png", "slide-2.png", "slide-1.png"]
    assert sorted(names, key=natural_key) == ["slide-1.png", "slide-2.png", "slide-10.png"]


def test_recording_zip_url():
    host, rec, url = recording_zip_url("https://vc2.example.edu/pabc123/?launcher=false")
    assert host == "https://vc2.example.edu"
    assert rec == "pabc123"
    assert url == "https://vc2.example.edu/pabc123/output/pabc123.zip?download=zip"
    with pytest.raises(RuntimeError):
        recording_zip_url("ftp://x/y")


def test_options_from_args():
    ns = build_parser().parse_args(["a.zip", "--slides", "ML=~/ml.pdf", "--host", "https://h/", "--size", "640x480"])
    opts = options_from_args(ns)
    assert opts.slides == [("ML", "~/ml.pdf")]
    assert opts.host == "https://h"
    assert opts.size == (640, 480)
    assert opts.interactive is False


def test_audio_graph_mix():
    parts = [MediaPart("a.flv", 0.0, ProbeInfo(duration=5, has_audio=True)),
             MediaPart("b.flv", 1.5, ProbeInfo(duration=5, has_audio=True))]
    inputs, filters = _audio_graph(parts, 10.0, 1)
    assert inputs == ["-i", "a.flv", "-i", "b.flv"]
    assert "adelay=1500|1500[a1]" in filters[1]
    assert filters[-1].startswith("[a0][a1]amix=inputs=2")
    assert _audio_graph([], 3.0, 0)[1] == ["anullsrc=r=44100:cl=mono:d=3.000[aout]"]


def test_render_frames(tmp_path):
    shape = Shape(kind="pencil", points=[(0, 0), (1, 1)], box=(0, 0, 100, 100), color=0x00FF00, weight=2, alpha=1)
    events = [ContentEvent(0, "7"), SlideEvent(1000, 1), ShapeAdded(2000, 1, "5", shape)]
    contents = {"7": Content(ct_id="7", name="Doc", width=960, height=720)}
    segments = render_frames(events, contents, {"7": []}, 4000, 320, 240, str(tmp_path))
    assert [round(s.duration_s, 3) for s in segments] == [1.0, 1.0, 2.0]
    assert len({s.png for s in segments}) == 3
    assert all(os.path.exists(s.png) for s in segments)
