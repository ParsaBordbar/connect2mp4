"""Plain data types passed between the parsing, rendering and encoding stages."""
from dataclasses import dataclass, field


@dataclass
class Stream:
    """An audio/video stream announced in mainstream.xml (cameraVoip_* / screenshare_*)."""
    name: str
    type: str
    start_ms: int
    end_ms: int | None = None


@dataclass
class Content:
    """A document shown in the share pod."""
    ct_id: str
    name: str = ""
    share_type: str = ""
    the_type: str = ""
    sco_id: str = ""
    width: float = 0.0     # content pixel size the whiteboard coordinates refer to
    height: float = 0.0
    sco: str = ""          # sco id from playbackFileName* (where the slide source lives on the server)
    sco_src: str = ""      # sco id from theUrl

    @property
    def sco_ids(self) -> list[str]:
        return [s for s in (self.sco, self.sco_src) if s]


@dataclass
class Shape:
    """One whiteboard stroke/shape. Points are 0..1 inside `box`, box is in content pixels."""
    kind: str
    points: list[tuple[float, float]]
    box: tuple[float, float, float, float]  # x, y, width, height
    color: int                              # 0xRRGGBB
    weight: float
    alpha: float
    text: str = ""


# --- share pod timeline events (from ftcontent*.xml) -------------------------------------------
@dataclass
class ContentEvent:
    """The share pod switched to another document."""
    time_ms: int
    ct_id: str


@dataclass
class SlideEvent:
    """The current document jumped to slide/page `index`."""
    time_ms: int
    index: int


@dataclass
class ShapeAdded:
    time_ms: int
    page: int
    shape_id: str
    shape: Shape


@dataclass
class ShapeRemoved:
    time_ms: int
    page: int
    shape_id: str


Event = ContentEvent | SlideEvent | ShapeAdded | ShapeRemoved


# --- media ----------------------------------------------------------------------------------------
@dataclass
class ProbeInfo:
    duration: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    width: int = 0
    height: int = 0


@dataclass
class MediaPart:
    """An FLV from the recording together with its offset on the timeline."""
    path: str
    offset_s: float
    info: ProbeInfo = field(default_factory=ProbeInfo)

    @property
    def end_s(self) -> float:
        return self.offset_s + self.info.duration


@dataclass
class Segment:
    """A rendered frame shown for `duration_s` seconds."""
    png: str
    duration_s: float
