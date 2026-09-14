"""Small helpers shared by several modules."""
import re


def natural_key(s: str) -> list:
    """Sort key so that 'slide-2' comes before 'slide-10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def parse_size(size: str) -> tuple[int, int]:
    """'1280x960' -> (1280, 960); both dimensions rounded down to even numbers (x264 needs that)."""
    m = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", size)
    if not m:
        raise ValueError(f"--size must look like 1280x960, got {size!r}")
    return int(m.group(1)) // 2 * 2, int(m.group(2)) // 2 * 2
