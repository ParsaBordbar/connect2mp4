"""Parse the XML logs inside a Connect recording zip.

The files are huge but very regular, so plain regexes are used instead of an XML parser.

    mainstream.xml   timeline: audio streams added/removed, documents shared (setContentSo)
    ftcontent*.xml   share pod: document switches, slide changes and whiteboard strokes
"""
import functools
import html
import re
from collections.abc import Iterator

from .model import Content, ContentEvent, Event, Shape, ShapeAdded, ShapeRemoved, SlideEvent, Stream

_MESSAGE_RE = re.compile(r'<Message time="(\d+)"[^>]*>(.*?)</Message>', re.S)
_EVENT_NAME_RE = re.compile(r"</Object>\s*<String><!\[CDATA\[(.*?)\]\]></String>", re.S)
_NEW_VALUE_RE = re.compile(r"<newValue>(.*?)</newValue>", re.S)
_SCO_IN_PATH_RE = re.compile(r"/_?a?\d*/?(p[0-9a-z]+)/")
_POINT_RE = re.compile(r"<x><!\[CDATA\[([-\d.eE]+)\]\]></x>\s*<y><!\[CDATA\[([-\d.eE]+)\]\]></y>")
_PTS_RE = re.compile(r"<pts>(.*?)</pts>", re.S)
_WB_OBJECT_RE = re.compile(
    r"<Object>\s*<code><!\[CDATA\[(\w+)\]\]></code>\s*<name><!\[CDATA\[(.*?)\]\]></name>\s*"
    r"(?:<newValue>(.*?)</newValue>|<newValue><!\[CDATA\[(.*?)\]\]></newValue>)", re.S)


@functools.lru_cache(maxsize=None)
def cdata(tag: str) -> re.Pattern:
    """Regex matching <tag><![CDATA[...]]></tag>."""
    return re.compile(r"<%s><!\[CDATA\[(.*?)\]\]></%s>" % (tag, tag), re.S)


def _named_value(tag_name: str, body: str) -> str | None:
    """Value of <name><![CDATA[tag_name]]></name><newValue><![CDATA[123..."""
    m = re.search(r"<name><!\[CDATA\[%s\]\]></name>\s*<newValue><!\[CDATA\[(\d+)" % tag_name, body)
    return m.group(1) if m else None


def iter_messages(xml_path: str) -> Iterator[tuple[int, str, str]]:
    """Yield (time_ms, event_name, body) for every <Message> in a Connect stream xml."""
    with open(xml_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    for m in _MESSAGE_RE.finditer(text):
        time_ms, body = int(m.group(1)), m.group(2)
        ev = _EVENT_NAME_RE.search(body)
        yield time_ms, (ev.group(1) if ev else ""), body


# ---------------------------------------------------------------- mainstream.xml
def parse_mainstream(path: str) -> tuple[list[Stream], dict[str, Content], int]:
    """Returns (streams, contents by ctID, last timestamp in ms)."""
    streams: dict[str, Stream] = {}
    contents: dict[str, Content] = {}
    last_ms = 0
    for time_ms, event, body in iter_messages(path):
        last_ms = max(last_ms, time_ms)
        if event in ("streamAdded", "streamRemoved"):
            _update_streams(streams, event, body, time_ms)
        elif event == "setContentSo":
            for obj in _NEW_VALUE_RE.findall(body):
                _update_content(contents, obj)
    return list(streams.values()), contents, last_ms


def _update_streams(streams: dict[str, Stream], event: str, body: str, time_ms: int) -> None:
    for name, stype in zip(cdata("streamName").findall(body), cdata("streamType").findall(body)):
        name = name.strip("/")
        stream = streams.setdefault(name, Stream(name=name, type=stype, start_ms=time_ms))
        if event == "streamRemoved":
            stream.end_ms = time_ms


def _first(tag: str, obj: str) -> str:
    values = cdata(tag).findall(obj)
    return values[0] if values and values[0] else ""


def _update_content(contents: dict[str, Content], obj: str) -> None:
    ct_id = _first("ctID", obj)
    if not ct_id:
        return
    content = contents.setdefault(ct_id, Content(ct_id=ct_id))
    for tag, attr in (("theName", "name"), ("shareType", "share_type"), ("theType", "the_type"),
                      ("scoID", "sco_id")):
        if value := _first(tag, obj):
            setattr(content, attr, value)
    for tag, attr in (("contentW", "width"), ("contentH", "height")):
        if value := _first(tag, obj):
            try:
                setattr(content, attr, float(value))
            except ValueError:
                pass
    for tag, attr in (("playbackFileName", "sco"), ("playbackFileNameHTMLClient", "sco"), ("theUrl", "sco_src")):
        value = _first(tag, obj)
        m = _SCO_IN_PATH_RE.search(value) if value else None
        if m and not getattr(content, attr):
            setattr(content, attr, m.group(1))


# ---------------------------------------------------------------- ftcontent*.xml
def parse_ftcontent(path: str) -> list[Event]:
    """Share pod log -> events sorted by time (document switch, slide change, shape add/remove)."""
    events: list[Event] = []
    for time_ms, event, body in iter_messages(path):
        if event == "setContentSo":
            if (ct_id := _named_value("ctID", body)) is not None:
                events.append(ContentEvent(time_ms, ct_id))
        elif event == "setPptLoaderSo":
            if (index := _named_value("slideIndex", body)) is not None:
                events.append(SlideEvent(time_ms, int(index)))
        elif event == "setWBSo":  # pdf / whiteboard-only pods
            if (page := _named_value("currentPage", body)) is not None:
                events.append(SlideEvent(time_ms, int(page)))
        elif event.startswith("set_WB_So_"):
            page = int(event.rsplit("_", 1)[1])
            events.extend(_whiteboard_events(time_ms, page, body))
    events.sort(key=lambda e: e.time_ms)
    return events


def _whiteboard_events(time_ms: int, page: int, body: str) -> Iterator[Event]:
    for m in _WB_OBJECT_RE.finditer(body):
        code, name, new_value = m.group(1), m.group(2), m.group(3)
        if not name.isdigit():
            continue  # tID, lastDepthOnPage ...
        if code == "delete":
            yield ShapeRemoved(time_ms, page, name)
        elif code == "change" and new_value and "<pts>" in new_value:
            yield ShapeAdded(time_ms, page, name, _parse_shape(new_value))


def _parse_shape(xml: str) -> Shape:
    inner = _PTS_RE.search(xml).group(1)
    points = [(float(x), float(y)) for x, y in _POINT_RE.findall(inner)]
    outer = _PTS_RE.sub("", xml)

    def prop(tag: str, default: str) -> str:
        return (cdata(tag).findall(outer) or [default])[0]

    return Shape(
        kind=prop("type", "pencil"),
        points=points,
        box=(float(prop("x", "0")), float(prop("y", "0")), float(prop("width", "0")), float(prop("height", "0"))),
        color=int(float(prop("strokeCol", "0"))),
        weight=float(prop("strokeWeight", "2")),
        alpha=float(prop("alpha", "1")),
        text=html.unescape(re.sub("<[^>]+>", "", prop("htmlText", ""))),
    )
