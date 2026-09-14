"""Turn the share pod timeline into PNG frames (slide bitmap + whiteboard strokes)."""
import functools
import os

from PIL import Image, ImageDraw, ImageFont

from .console import log
from .model import Content, ContentEvent, Event, Segment, Shape, ShapeAdded, ShapeRemoved, SlideEvent

MIN_FRAME_GAP_MS = 150  # merge state changes closer than this (strokes drawn quickly)
FONT_PATHS = ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


@functools.lru_cache(maxsize=None)
def load_font(size: int):
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_shapes(img: Image.Image, shapes: dict[str, Shape], W: int, H: int, content_w: float, content_h: float) -> None:
    """Composite whiteboard shapes (content px coordinates) onto img (W x H px)."""
    if not shapes:
        return
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    sx, sy = W / content_w, H / content_h
    for shape in shapes.values():
        bx, by, bw, bh = shape.box
        pts = [((bx + x * bw) * sx, (by + y * bh) * sy) for x, y in shape.points]
        if not pts:
            continue
        rgb = shape.color
        col = ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, int(255 * shape.alpha))
        lw = max(1, int(round(shape.weight * sx)))
        kind = shape.kind.lower()
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        if kind in ("rect", "rectangle", "square"):
            d.rectangle(bbox, outline=col, width=lw)
        elif kind in ("ellipse", "circle", "oval"):
            d.ellipse(bbox, outline=col, width=lw)
        elif kind in ("text", "textbox"):
            d.text(pts[0], shape.text, fill=col, font=load_font(max(12, int(H / 30))))
        elif len(pts) == 1:
            x, y = pts[0]
            d.ellipse([x - lw, y - lw, x + lw, y + lw], fill=col)
        else:
            d.line(pts, fill=col, width=lw, joint="curve")
    img.alpha_composite(overlay)


class SlideImages:
    """Base slide bitmaps scaled to the output size, cached per file; one instance per recording."""

    def __init__(self, W: int, H: int):
        self.W, self.H = W, H
        self._cache: dict = {}

    def get(self, pngs: list[str], index: int, label: str) -> Image.Image:
        W, H = self.W, self.H
        key = pngs[index] if pngs and 0 <= index < len(pngs) else ("placeholder", label, index)
        if key not in self._cache:
            base = Image.new("RGBA", (W, H), (255, 255, 255, 255))
            if isinstance(key, str):
                im = Image.open(key).convert("RGBA")
                im.thumbnail((W, H))
                base.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
            else:
                ImageDraw.Draw(base).text((W * 0.04, H * 0.04), f"{label}\nslide {index + 1}  (slide file not available)",
                                          fill=(120, 120, 120, 255), font=load_font(int(H / 28)))
            self._cache[key] = base
        return self._cache[key].copy()


class _PodState:
    """Mutable state of the share pod while replaying events."""

    def __init__(self):
        self.ct_id: str | None = None
        self.slide = 0
        self.boards: dict[tuple[str | None, int], dict[str, Shape]] = {}  # (ct_id, page) -> shapes

    def apply(self, event: Event) -> None:
        if isinstance(event, ContentEvent):
            self.ct_id, self.slide = event.ct_id, 0
        elif isinstance(event, SlideEvent):
            self.slide = event.index
        elif isinstance(event, ShapeAdded):
            self.boards.setdefault((self.ct_id, event.page), {})[event.shape_id] = event.shape
        elif isinstance(event, ShapeRemoved):
            self.boards.get((self.ct_id, event.page), {}).pop(event.shape_id, None)

    @property
    def shapes(self) -> dict[str, Shape]:
        return self.boards.get((self.ct_id, self.slide), {})


def render_frames(events: list[Event], contents: dict[str, Content], slides: dict[str, list[str]],
                  total_ms: int, W: int, H: int, frames_dir: str) -> list[Segment]:
    """Replay events, write one PNG per distinct visual state, return the frame sequence."""
    os.makedirs(frames_dir, exist_ok=True)
    images = SlideImages(W, H)
    state = _PodState()
    frame_count = 0

    def snapshot() -> str:
        nonlocal frame_count
        content = contents.get(state.ct_id) or Content(ct_id=state.ct_id or "", name="share pod")
        img = images.get(slides.get(state.ct_id) or [], state.slide, content.name or "share pod")
        draw_shapes(img, state.shapes, W, H, content.width or 960.0, content.height or 720.0)
        path = os.path.join(frames_dir, f"f{frame_count:05d}.png")
        img.convert("RGB").save(path, compress_level=1)
        frame_count += 1
        return path

    sequence: list[Segment] = []
    t_prev, t_snap = 0, -10**9
    dirty, current_png = True, None
    for event in [*events, None]:  # None = end of timeline
        t = total_ms if event is None else event.time_ms
        # re-render when the state changed and either a pause happened or MIN_FRAME_GAP_MS passed
        if dirty and (current_png is None or event is None
                      or t - t_prev >= MIN_FRAME_GAP_MS or t - t_snap >= MIN_FRAME_GAP_MS):
            current_png, t_snap, dirty = snapshot(), t, False
        if t > t_prev:
            sequence.append(Segment(current_png, (t - t_prev) / 1000.0))
            t_prev = t
        if event is not None:
            state.apply(event)
            dirty = True
    if not sequence:  # nothing happened at all: one still frame
        sequence = [Segment(current_png or snapshot(), max(total_ms, 1000) / 1000.0)]
    merged: list[Segment] = []  # collapse consecutive identical frames
    for seg in sequence:
        if merged and merged[-1].png == seg.png:
            merged[-1].duration_s += seg.duration_s
        else:
            merged.append(Segment(seg.png, seg.duration_s))
    log(f"rendered {frame_count} frames, {len(merged)} segments")
    return merged
