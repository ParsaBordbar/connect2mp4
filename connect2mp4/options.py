"""Run-time options, filled either from the command line or from the interactive setup."""
from dataclasses import dataclass, field


@dataclass
class Options:
    targets: list[str]
    out_dir: str = "connect_out"
    slides: list[tuple[str, str]] = field(default_factory=list)  # (document key, slide file)
    host: str | None = None          # server base URL, used to download slide sources
    cookie: str | None = None        # raw Cookie header for authenticated servers
    insecure: bool = False           # skip TLS verification (may be switched on interactively)
    camera: bool = False             # prefer webcam video over screen share
    width: int = 1280
    height: int = 960
    fps: int = 10
    crf: int = 26
    keep: bool = False               # keep the extracted work directory
    interactive: bool = False        # started from the TUI (allows prompts mid-run)
    config: dict = field(default_factory=dict)  # persisted user config (see config.py)

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height
