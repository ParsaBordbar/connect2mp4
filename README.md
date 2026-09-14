# connect2mp4

Export an Adobe Connect recording to a single MP4 (slides + whiteboard strokes + audio,
or the screen-share video when the teacher shared their screen).

## Requirements

- Python 3.10+, Pillow (`pip install pillow`)
- `ffmpeg` and `ffprobe` (`brew install ffmpeg`)
- `pdftoppm` from poppler for PDF slides (`brew install poppler`)
- LibreOffice (`soffice`) only if you pass `.pptx` slides

## Usage

```
python3 -m connect2mp4                                        # no args -> interactive TUI
python3 -m connect2mp4 https://vc2.shirazu.ac.ir/pquxl04g15ys/ # recording link
python3 -m connect2mp4 ~/Downloads/last.zip                   # downloaded zip
python3 -m connect2mp4 ~/Downloads/zips/                      # folder of zips
python3 -m connect2mp4 last.zip --slides "Learning Theory=~/Downloads/09- Learning Theory-2.pdf"
python3 -m connect2mp4 last.zip --slides p7v19xnp88eb=~/slides.pptx   # key = sco id or part of name
```

`pip install -e .` also installs a `connect2mp4` command.

| Option | Meaning |
| --- | --- |
| `-o DIR` | output directory (default `./connect_out`) |
| `--slides K=F` | slide file for shared document K (part of its name, or its sco id). F = .pdf, .pptx or a folder of PNGs. Repeatable. Without it the source is downloaded from the server, else numbered blank slides are drawn. |
| `--host URL` | server base (e.g. `https://vc2.shirazu.ac.ir`) for slide download when the input is a zip |
| `--cookie S` | raw Cookie header (`BREEZESESSION=...`) if the server wants login |
| `--insecure` | skip TLS certificate verification (old university servers) |
| `--camera` | prefer webcam video over screen share |
| `--size WxH` | output size (default 1280x960) |
| `--fps N` | output frame rate (default 10) |
| `--crf N` | x264 quality (default 26) |
| `--keep` | keep extracted files and rendered frames |

The interactive mode remembers the last URL, server and output folder in `.connect2mp4.json`
next to the package (override the location with `CONNECT2MP4_HOME`). Recording zips dropped into
that folder are offered in the menu.

## What is inside a Connect recording zip

| File | Content |
| --- | --- |
| `mainstream.xml` | timeline: audio streams added/removed (`cameraVoip_*`), documents shared |
| `cameraVoip_*.flv` | audio (nellymoser) and webcam video if any |
| `screenshare_*.flv` | screen share video (only when the teacher shared the screen) |
| `ftcontent*.xml` | share pod: slide changes and whiteboard strokes (normalized 0..1 coords) |

The slides themselves are **not** in the zip. They live on the server at
`/<sco>/output/<name>?download=<name>`, which is what `--host` / the TUI download option uses.

## Code layout

```
connect2mp4/
  cli.py       argument parsing, target expansion, main()
  tui.py       interactive menus: start-up wizard and slide file picker
  pipeline.py  per-recording flow: obtain zip -> extract -> parse -> render/encode
  parsing.py   regex parsers for mainstream.xml and ftcontent*.xml
  slides.py    locate / download / rasterize slide files, slide cache
  render.py    replay share pod events into PNG frames (slides + whiteboard)
  ffmpeg.py    ffprobe and the two ffmpeg assembly graphs (slideshow, screen share)
  net.py       downloads with atomic writes and the TLS fallback
  model.py     dataclasses shared between stages
  options.py   Options: run-time settings from CLI or TUI
  config.py    persisted user preferences (.connect2mp4.json)
  console.py   colours, log(), banner, text prompt
  util.py      natural sort key, size parsing
```
