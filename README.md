<img width="408" height="129" alt="image" src="https://github.com/user-attachments/assets/d884368e-385f-4a8b-8727-c476d39a9ed8" />

# connect2mp4

Turn an **Adobe Connect** class recording into a single, normal **MP4** you can watch anywhere,
scrub through, speed up, or keep offline.

Adobe Connect recordings are not video files. They are a zip of audio streams, an XML timeline,
and a log of what happened in the share pod (slide changes, pen strokes). connect2mp4 replays that
timeline and encodes it:

- **Slides + whiteboard + audio** when the teacher shared a PDF/PPTX and drew on it.
- **Screen share + audio** when the teacher shared their screen (no slides needed).

```
connect2mp4 https://vc2.shirazu.ac.ir/pquxl04g15ys/
# -> connect_out/pquxl04g15ys.mp4
```

---

## Table of contents

1. [Install](#install)
2. [Quick start](#quick-start)
3. [Interactive mode (recommended)](#interactive-mode-recommended)
4. [Command line mode](#command-line-mode)
5. [Slides: where they come from](#slides-where-they-come-from)
6. [Output files and settings](#output-files-and-settings)
7. [Troubleshooting](#troubleshooting)
8. [How it works](#how-it-works)
9. [Development](#development)

---

## Install

### 1. System tools

| Tool | Needed for | macOS | Debian / Ubuntu |
| --- | --- | --- | --- |
| Python 3.10+ | everything | `brew install python` | `sudo apt install python3` |
| `ffmpeg` + `ffprobe` | every export | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| `pdftoppm` (poppler) | PDF slides | `brew install poppler` | `sudo apt install poppler-utils` |
| LibreOffice (`soffice`) | **only** `.pptx` / `.ppt` slides | `brew install --cask libreoffice` | `sudo apt install libreoffice-impress` |

If you only ever pass PDF slides (or let the tool download them) you can skip LibreOffice.

### 2. The tool

```bash
git clone git@github.com:ParsaBordbar/connect2mp4.git
cd connect2mp4
pip install pillow          # the only Python dependency
```

Run it from the repo folder:

```bash
python3 run.py ...          # or: python3 -m connect2mp4 ...
```

The rest of this README writes `connect2mp4` for short; read it as `python3 run.py`.

---

## Quick start

**Step 0.** Install (above). Check with `python3 run.py --version`.

**Step 1.** Open the recording in your browser once and copy its link. It looks like
`https://<server>/<recording-id>/`, for example `https://vc2.shirazu.ac.ir/pquxl04g15ys/`.

**Step 2.** Run the tool with no arguments and follow the menus:

```bash
python3 run.py
```

**Step 3.** Wait. The MP4 lands in the output folder you picked, as `<recording-id>.mp4`.

That is the whole workflow. Everything below is detail.

---

## Interactive mode (recommended)

Running with **no arguments in a terminal** opens a small wizard with arrow-key menus
(`↑`/`↓` or `j`/`k` to move, `enter` to pick, `q` to quit).

```
╭──────────────────────────────────────╮
│ connect2mp4 · Adobe Connect → MP4    │
╰──────────────────────────────────────╯

What to convert?
 ❯ recording link        https://vc2.shirazu.ac.ir/xxxx/
   zip path or folder    type / drag a path
   last.zip              412 MB · next to script
 ↑/↓ move · enter select · q quit
```

The wizard asks, in order:

1. **What to convert**
   - *recording link*: paste the URL. The zip is downloaded for you.
   - *zip path or folder*: a recording zip you downloaded yourself, or a folder full of them
     (drag the file into the terminal to paste its path).
   - Any recording zip you dropped **next to the script** is listed directly as a menu entry.
2. **Server address** (only asked for zips): the base URL of your Connect server, used to fetch the
   original slide files. Press enter to skip if you will supply slides yourself.
3. **Output folder** (default `connect_out` next to the script).

Then, for **every document the teacher showed**, a slide picker appears:

```
  document shown in class: 09- Learning Theory
Slide file for this document:
 ❯ cached slides                    57 pages rendered earlier
   09- Learning Theory-2.pdf        ~/Downloads
   Learning_Theory.pptx             ~/Documents/UNI/Term2/ML
   type a path…                     pdf / pptx / folder of png
   download from server             https://vc2.shirazu.ac.ir
   no slides                        white pages + pen strokes only
```

- **cached slides**: pages already rendered by a previous run of this document.
- **File suggestions**: the tool searches `~/Downloads`, `~/Desktop`, `~/Documents`, the current
  folder, and any folder you picked a slide file from before, for PDF/PPTX files whose name
  resembles the document name. Best match first.
- **type a path…**: a `.pdf`, `.pptx`, or a folder of `.png`/`.jpg` pages.
- **download from server**: fetch the original file the teacher uploaded (needs the server to
  allow it; see [Troubleshooting](#troubleshooting)).
- **no slides**: numbered blank pages with the pen strokes on top. Better than nothing.

If the server has a broken/old TLS certificate the wizard asks once whether to continue without
verification.

Your last link, server, output folder and slide folders are remembered in `.connect2mp4.json`
(see [Output files and settings](#output-files-and-settings)).

---

## Command line mode

Pass one or more targets and the tool runs without asking anything. Good for scripts and batches.

```bash
connect2mp4 https://vc2.shirazu.ac.ir/pquxl04g15ys/           # one recording by link
connect2mp4 ~/Downloads/last.zip                              # a downloaded zip
connect2mp4 ~/Downloads/zips/                                 # every zip in a folder
connect2mp4 link1 link2 ~/one.zip                             # mix and match
connect2mp4 last.zip --host https://vc2.shirazu.ac.ir         # zip + let it download slides
connect2mp4 last.zip --slides "Learning Theory=~/09- Learning Theory-2.pdf"
connect2mp4 last.zip --slides p7v19xnp88eb=~/slides.pptx --slides Markov=~/markov.pdf
connect2mp4 last.zip --size 1920x1440 --fps 15 --crf 22       # bigger, smoother, higher quality
```

A **target** is a recording URL, a zip file, or a folder of zips. Folders expand to their zips
in natural order (`part1.zip`, `part2.zip`, `part10.zip`).

### Options

| Option | Meaning | Default |
| --- | --- | --- |
| `-o DIR`, `--out DIR` | output directory (also holds downloaded zips and the slide cache) | `./connect_out` |
| `--slides KEY=FILE` | slide file for shared document `KEY`. Repeatable, one per document. See [Slides](#slides-where-they-come-from). | download, else blank pages |
| `--host URL` | Connect server base, e.g. `https://vc2.shirazu.ac.ir`. Lets the tool download slide files when the input is a zip. Taken from the link automatically when the target is a URL. | none |
| `--cookie S` | raw `Cookie` header (`BREEZESESSION=...`) for servers that require login | none |
| `--insecure` | skip TLS certificate verification (old university servers) | off |
| `--camera` | prefer the webcam video over the screen share video | off |
| `--size WxH` | output size. The share pod is 4:3, so keep that ratio for slides. | `1280x960` |
| `--fps N` | frame rate. Slides barely move, so low is fine. | `10` |
| `--crf N` | x264 quality, lower = better and bigger (18 great, 28 small) | `26` |
| `--keep` | keep the extracted zip contents and rendered frames (temp dir path is printed) | off |
| `--version` | print version | |

`connect2mp4 --help` shows the same list.

---

## Slides: where they come from

This is the one part that needs your attention. **The slide images are not inside the recording
zip.** The zip only says *"document X was shown, page 7 at 12:34, pen stroke here"*. The actual
PDF/PPTX lives on the Connect server, or on your disk if you downloaded it from the course page.

For each document shown in class, connect2mp4 picks a source in this order:

1. **`--slides KEY=FILE`** on the command line (always wins).
2. **The interactive picker** (only in interactive mode).
3. **The cache** from an earlier run (`connect_out/slides_cache/<sco-id>/`), if it was completed
   at the same output width.
4. **Download from the server** (`--host`, or the link's server) at
   `https://<host>/<sco-id>/output/<name>?download=<name>`.
5. **Blank numbered pages.** The log tells you which key to pass next time.

### The `KEY` in `--slides KEY=FILE`

`KEY` can be either:

- **Part of the document name**, case-insensitive. The name is what the teacher uploaded, printed
  by the tool as `document shown: '09- Learning Theory' sco=p7v19xnp88eb / ...`.
  `--slides "learning theory=~/lt.pdf"` matches it.
- **The sco id** (`p7v19xnp88eb` above). Exact, so it is the safe choice when names are messy.

`FILE` can be a `.pdf`, a `.pptx`/`.ppt`/`.odp` (converted through LibreOffice), or a **folder of
`.png`/`.jpg`** files that sort into page order (`slide-01.png`, `slide-02.png`, ...).

Page count must match what the teacher showed, otherwise strokes land on the wrong page. Using
the exact file from the course page is best.

### Slide cache

Rendered pages are stored in `connect_out/slides_cache/<sco-id>/slide-NN.png` with a
`.complete` marker. Re-exporting the same recording (or another recording that uses the same
deck) reuses them. Delete the folder to force a re-render, or pass `--slides` which always
re-renders.

---

## Output files and settings

```
connect_out/
  pquxl04g15ys.zip        the downloaded recording (kept, so re-runs skip the download)
  pquxl04g15ys.mp4        the result: H.264 video, AAC mono audio
  slides_cache/           rendered slide pages, one folder per document
```

The MP4 is named after the recording id (last part of the link) or the zip file name.
Delete the zip if you no longer need it; the tool re-downloads on demand.

### `.connect2mp4.json`

Interactive mode stores a few preferences next to the script:

```json
{
  "last_url": "https://vc2.shirazu.ac.ir/plk7k8hox37l/",
  "host": "https://vc2.shirazu.ac.ir",
  "out": "/Users/me/connect2mp4/connect_out",
  "slide_dirs": ["/Users/me/Documents/UNI/ML"]
}
```

Set `CONNECT2MP4_HOME=/some/dir` to keep this file (and the "zips next to the script" menu) in
another folder. The file is git-ignored.

---

## Troubleshooting

**`ffmpeg not found`** – install it (see [Install](#install)) and make sure it is on your `PATH`.

**`download failed ... server returned HTML (login page?)`** – the server wants you logged in.
Either
- download the zip in your browser (the URL is printed, it ends in `output/<id>.zip?download=zip`)
  and run `connect2mp4 <zip> --host https://<server>`, or
- copy your browser's cookie and pass it: `--cookie "BREEZESESSION=abc123..."`
  (DevTools → Network → any request to the server → `Cookie` request header).

**`TLS certificate problem`** – many university servers run outdated TLS. Re-run with
`--insecure`. Interactive mode offers this automatically.

**`could not get slides for '...' from server`** – the slide file is not downloadable
anonymously. The log prints the exact URLs to try in a logged-in browser. Save the file and re-run
with `--slides '<sco-id>=/path/to/file'`.

**`pdftoppm missing`** – `brew install poppler` / `sudo apt install poppler-utils`.

**`... is not a PDF and LibreOffice is not installed`** – either install LibreOffice, or open the
`.pptx` in PowerPoint/Keynote/Google Slides, export it as PDF, and pass the PDF instead.

**Strokes appear on the wrong slide / off by one** – the file you passed has a different page
count than the deck shown in class. Use the file from the course page, or render the exact pages
into a folder of PNGs.

**Video is only white pages with pen strokes** – no slide source was found; see
[Slides](#slides-where-they-come-from).

**Got the screen share but wanted the slides** – if any `screenshare_*.flv` in the zip has video,
that is used and the slide timeline is ignored. There is no override for this yet; open an issue if
you hit a recording where both matter.

**Want the webcam instead of the screen share** – `--camera`.

**Something else went wrong** – run with `--keep`, the temp work dir is printed and contains the
extracted zip, the rendered `frames/` and `frames.txt` (the ffmpeg concat list) for inspection.

---

## How it works

```
recording link ──download──▶ <id>.zip
                                │ extract
                                ▼
                    mainstream.xml      cameraVoip_*.flv      screenshare_*.flv     ftcontent*.xml
                    (timeline)          (audio, webcam)       (screen video)        (share pod log)
                                │                                     │
             ┌──────────────────┴─────────────────┐                   │
             ▼                                    ▼                   │
     screen share has video?  ── yes ──▶  concat screen parts + mix audio ──▶ MP4
             │ no
             ▼
     replay share pod log: slide changes + whiteboard shapes
             │
             ▼
     locate slide pages (--slides / picker / cache / server / blank)
             │
             ▼
     render one PNG per visual state (Pillow) ──▶ ffmpeg concat + mixed audio ──▶ MP4
```

Details worth knowing:

- Audio parts are placed at the offsets `mainstream.xml` gives (fallback: the timestamp in the file
  name) and mixed, so gaps and reconnects during class stay in sync.
- Whiteboard coordinates in the log are normalized; they are scaled onto the slide bitmap.
  Freehand strokes, rectangles, ellipses and text boxes are supported.
- Frames are only re-rendered when the picture changes; strokes drawn within 150 ms are merged.
  A two-hour class with 300 state changes produces 300 PNGs, not 72 000.

### What is inside a Connect recording zip

| File | Content |
| --- | --- |
| `mainstream.xml` | timeline: audio streams added/removed (`cameraVoip_*`), documents shared |
| `cameraVoip_*.flv` | audio (Nellymoser) and webcam video, if any |
| `screenshare_*.flv` | screen share video (only when the teacher shared the screen) |
| `ftcontent*.xml` | share pod: slide changes and whiteboard strokes |

The slides themselves are **not** in the zip; they live on the server at
`/<sco>/output/<name>?download=<name>`.

---

## Development

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
tests/
  test_parsing.py   mainstream / ftcontent parsers on small XML fixtures
  test_units.py     CLI parsing, URL building, audio graph, frame rendering
```

Run the tests:

```bash
pip install pytest
python3 -m pytest
```

Pull requests welcome. Recordings from other Connect servers that fail to parse are the most
useful bug reports; run with `--keep` and attach `mainstream.xml` and `ftcontent*.xml`
(they contain no audio and no slides).

---

## License

Apache License 2.0. See [LICENSE](LICENSE). If you redistribute or build on this project, keep
the [NOTICE](NOTICE) file: it credits Parsa Bordbar as the original author, as Section 4(d) of the
license requires.
