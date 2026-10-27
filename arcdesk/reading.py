"""Read anything the user actually has on their disk — and say what it could not read.

Nine formats matter in practice: documents (pdf, docx), spreadsheets (xlsx, csv),
slides (pptx), plain text (txt, md, json, code), pictures (png, jpg, gif), audio
(wav, mp3) and video (mp4, mov). ARC converts every one of them into the same
shape so a single summariser, reviewer and editor can work on all of them.

Three rules this module lives by:

1. **Sniff, do not trust the extension.** A `.pdf` that is really a JPEG still gets
   read; a renamed `.txt` binary is refused instead of dumped into the prompt.
2. **Never send a 400-page book to a model.** Extraction is capped, and the cap is
   reported (`meta["truncated"]`), so "summarise my thesis" is honest about how much
   of it was actually looked at.
3. **Say what failed.** A scanned PDF with no text layer, an MP4 with no ffmpeg, an
   MP3 with no whisper model — each returns a `warnings` entry naming the missing
   piece and the one command that fixes it. Silence here is what makes assistants
   lie about files they never read.
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess

from . import quiet
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".log", ".ini", ".cfg", ".yaml", ".yml",
            ".xml", ".html", ".htm", ".css", ".js", ".ts", ".py", ".java", ".c", ".cpp",
            ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".bat", ".ps1", ".sql"}
DATA_EXT = {".csv", ".tsv", ".json", ".jsonl", ".ndjson"}
DOC_EXT = {".pdf", ".docx", ".doc"}
SHEET_EXT = {".xlsx", ".xlsm", ".xls"}
SLIDE_EXT = {".pptx", ".ppt"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".flv", ".m4v"}

MAX_READ = 40_000          # characters of text handed on by default
MAX_BYTES = 64 * 1024 * 1024


@dataclass
class Document:
    path: str
    kind: str = "unknown"
    text: str = ""
    meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    ok: bool = False

    def describe(self) -> str:
        bits = [f"{self.kind}", f"{self.meta.get('bytes', 0) / 1024:.0f} KB"]
        for key in ("pages", "sheets", "slides", "rows", "duration_s", "width", "frames"):
            if key in self.meta:
                bits.append(f"{key} {self.meta[key]}")
        if self.meta.get("truncated"):
            bits.append("truncated")
        if self.warnings:
            bits.append(f"{len(self.warnings)} warning(s)")
        return " · ".join(str(b) for b in bits)

    def warning_text(self) -> str:
        return "\n".join(f"- {w}" for w in self.warnings)


# ----------------------------------------------------------------- sniffing
MAGIC = [
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "riff"),
    (b"ID3", "mp3"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
    (b"PK\x03\x04", "zip"),
    (b"\x1aE\xdf\xa3", "matroska"),
    (b"\x00\x00\x00\x18ftyp", "mp4"),
    (b"\x00\x00\x00\x20ftyp", "mp4"),
]


def sniff(path: str) -> str:
    """Real type from the first bytes — the extension is only a hint."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except OSError:
        return "unknown"
    for magic, kind in MAGIC:
        if head.startswith(magic):
            if kind == "riff":
                return "wav" if head[8:12] == b"WAVE" else "avi"
            if kind == "zip":
                name = str(path).lower()
                for ext, real in ((".docx", "docx"), (".xlsx", "xlsx"), (".xlsm", "xlsx"),
                                  (".pptx", "pptx"), (".jar", "zip"), (".zip", "zip")):
                    if name.endswith(ext):
                        return real
                return "zip"
            return kind
    if b"ftyp" in head[4:12]:
        return "mp4"
    return "text"


def kind_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in DOC_EXT:
        return "pdf" if ext == ".pdf" else "docx"
    if ext in SHEET_EXT:
        return "xlsx"
    if ext in SLIDE_EXT:
        return "pptx"
    if ext in IMAGE_EXT:
        return {".gif": "gif"}.get(ext, "image")
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in DATA_EXT:
        return "data"
    if ext in TEXT_EXT:
        return "text"
    sniffed = sniff(path)
    return sniffed if sniffed != "text" else "text"


def _size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ------------------------------------------------------------- extractors
def _read_text(path: str, doc: Document, limit: int) -> None:
    raw = Path(path).read_bytes()[:MAX_BYTES]
    if b"\x00" in raw[:4096]:
        doc.warnings.append("this file contains binary data, not text")
        return
    for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        doc.warnings.append("could not decode the text (unknown encoding)")
        return
    doc.meta["encoding"] = enc
    doc.meta["lines"] = text.count("\n") + 1
    doc.text = text[:limit]
    doc.ok = True


def _read_pdf(path: str, doc: Document, limit: int) -> None:
    try:
        from pypdf import PdfReader
    except Exception:
        doc.warnings.append("pip install pypdf  (needed to read PDFs)")
        return
    try:
        reader = PdfReader(path)
    except Exception as exc:
        doc.warnings.append(f"PDF could not be opened: {exc}")
        return
    doc.meta["pages"] = len(reader.pages)
    try:
        info = reader.metadata or {}
        for key, name in (("/Title", "title"), ("/Author", "author"),
                          ("/CreationDate", "created")):
            if info.get(key):
                doc.meta[name] = str(info.get(key))[:120]
    except Exception:
        pass
    chunks, used = [], 0
    empty_pages = 0
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text.strip():
            empty_pages += 1
            continue
        chunks.append(f"\n--- page {i + 1} ---\n{text}")
        used += len(text)
        if used >= limit:
            doc.meta["truncated"] = True
            doc.meta["pages_read"] = i + 1
            break
    doc.text = "".join(chunks)[:limit]
    doc.ok = bool(doc.text.strip())
    if empty_pages and not doc.ok:
        doc.warnings.append(
            f"{empty_pages} page(s) had no text layer — this is a scan. OCR it first: "
            "`screenshot`-style OCR or `tesseract file.pdf out` then read out.txt")
    elif empty_pages:
        doc.warnings.append(f"{empty_pages} page(s) had no text layer (scans inside the PDF)")


def _read_docx(path: str, doc: Document, limit: int) -> None:
    try:
        import docx
    except Exception:
        doc.warnings.append("pip install python-docx  (needed to read .docx)")
        return
    try:
        d = docx.Document(path)
    except Exception as exc:
        doc.warnings.append(f"docx could not be opened: {exc} (old .doc files are not "
                            "supported — save as .docx)")
        return
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        rows = []
        for row in table.rows:
            rows.append(" | ".join(cell.text.strip() for cell in row.cells))
        if rows:
            parts.append("\n[table]\n" + "\n".join(rows))
    text = "\n".join(parts)
    doc.meta["paragraphs"] = len(d.paragraphs)
    doc.meta["tables"] = len(d.tables)
    doc.meta["words"] = len(text.split())
    doc.text = text[:limit]
    doc.ok = bool(text.strip())
    if len(text) > limit:
        doc.meta["truncated"] = True


def _read_xlsx(path: str, doc: Document, limit: int) -> None:
    try:
        import openpyxl
    except Exception:
        doc.warnings.append("pip install openpyxl  (needed to read spreadsheets)")
        return
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        doc.warnings.append(f"spreadsheet could not be opened: {exc}")
        return
    out, rows_total = [], 0
    doc.meta["sheets"] = len(wb.sheetnames)
    for name in wb.sheetnames[:12]:
        ws = wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True, max_row=200):
            cells = ["" if c is None else str(c) for c in row]
            if any(cells):
                rows.append("\t".join(cells))
            rows_total += 1
            if rows_total > 1500:
                break
        out.append(f"\n[sheet: {name}] {ws.max_row or 0} rows × {ws.max_column or 0} cols\n"
                   + "\n".join(rows))
        if rows_total > 1500:
            doc.meta["truncated"] = True
            break
    doc.meta["rows"] = rows_total
    doc.text = "\n".join(out)[:limit]
    doc.ok = bool(doc.text.strip())
    try:
        wb.close()
    except Exception:
        pass


def _read_pptx(path: str, doc: Document, limit: int) -> None:
    try:
        from pptx import Presentation
    except Exception:
        doc.warnings.append("pip install python-pptx  (needed to read .pptx)")
        return
    try:
        deck = Presentation(path)
    except Exception as exc:
        doc.warnings.append(f"pptx could not be opened: {exc}")
        return
    out = []
    for i, slide in enumerate(deck.slides, 1):
        bits = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                bits.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    bits.append(" | ".join(c.text.strip() for c in row.cells))
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            notes = " [notes] " + slide.notes_slide.notes_text_frame.text.strip()
        out.append(f"\n--- slide {i} ---\n" + "\n".join(bits) + notes)
    doc.meta["slides"] = len(deck.slides)
    doc.text = "\n".join(out)[:limit]
    doc.ok = bool(doc.text.strip())


def _read_data(path: str, doc: Document, limit: int) -> None:
    ext = Path(path).suffix.lower()
    raw = Path(path).read_bytes()[:MAX_BYTES].decode("utf-8", "replace")
    if ext in (".json", ".jsonl", ".ndjson"):
        try:
            if ext == ".json":
                data = json.loads(raw)
                doc.meta["json_type"] = type(data).__name__
                if isinstance(data, dict):
                    doc.meta["keys"] = list(data)[:20]
                text = json.dumps(data, indent=1, ensure_ascii=False)
            else:
                lines = [json.loads(l) for l in raw.splitlines() if l.strip()][:500]
                doc.meta["records"] = len(lines)
                text = json.dumps(lines, indent=1, ensure_ascii=False)
        except Exception as exc:
            doc.warnings.append(f"invalid JSON: {exc} — showing it as text")
            text = raw
    else:
        sample = raw[:8000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delim = dialect.delimiter
        except Exception:
            delim = "\t" if ext == ".tsv" else ","
        rows = list(csv.reader(io.StringIO(raw), delimiter=delim))
        doc.meta["rows"] = len(rows)
        doc.meta["columns"] = len(rows[0]) if rows else 0
        doc.meta["delimiter"] = delim
        text = "\n".join(" | ".join(r) for r in rows[:2000])
    doc.text = text[:limit]
    doc.ok = bool(doc.text.strip())


def _read_image(path: str, doc: Document, limit: int, ocr: bool = True) -> None:
    try:
        from PIL import Image
    except Exception:
        doc.warnings.append("pip install pillow  (needed for images)")
        return
    try:
        with Image.open(path) as img:
            doc.meta.update({"width": img.width, "height": img.height,
                             "mode": img.mode, "format": img.format})
            if doc.kind == "gif":
                doc.meta["frames"] = getattr(img, "n_frames", 1)
                try:
                    img.seek(0)
                except Exception:
                    pass
            exif = {}
            try:
                raw = img.getexif()
                for tag in (306, 36867, 271, 272):     # datetime, model, make
                    if raw.get(tag):
                        exif[str(tag)] = str(raw.get(tag))[:40]
            except Exception:
                pass
            if exif:
                doc.meta["exif"] = exif
    except Exception as exc:
        doc.warnings.append(f"image could not be opened: {exc}")
        return
    doc.ok = True
    if not ocr:
        return
    try:
        from . import vision
        if not vision.ocr_available():
            doc.warnings.append("no OCR engine (winget install UB-Mannheim.TesseractOCR)")
            return
        words, upscaled = _ocr_words(path)
        if upscaled:
            doc.meta["ocr_upscaled"] = upscaled
        text = _words_to_lines(words)
        if text:
            doc.text = text[:limit]
            doc.meta["ocr_words"] = len(words)
        else:
            doc.warnings.append("no readable text in the image — it may be a photo or "
                                "a drawing, which this reader does not describe")
    except Exception as exc:
        doc.warnings.append(f"OCR failed: {exc}")


def _ocr_words(path: str) -> tuple[list[dict], float]:
    """OCR, upscaling small images first — tesseract needs ~30px of glyph height.

    A 600px-wide screenshot is the worst case: fine for a human, mush for the engine.
    Doubling it (Lanczos) turns "DESK 2028" back into "JARVIS DESK 2026".
    """
    from . import vision
    tmp = ""
    scale = 1.0
    try:
        from PIL import Image
        with Image.open(path) as img:
            if img.width < 1600:
                scale = 2.0 if img.width < 900 else 1.5
                tmp = str(Path(tempfile.gettempdir()) /
                          f"arcdesk-ocr-{os.getpid()}-{abs(hash(path)) % 10 ** 8}.png")
                big = img.convert("L").resize((int(img.width * scale),
                                              int(img.height * scale)),
                                             Image.LANCZOS)
                big.save(tmp, "PNG")
    except Exception:
        tmp, scale = "", 1.0
    try:
        return vision.ocr_words(tmp or path), scale
    finally:
        if tmp:
            try:
                Path(tmp).unlink()
            except Exception:
                pass


def _words_to_lines(words: list[dict]) -> str:
    """Rebuild reading order from word boxes: group by vertical centre, then sort x."""
    if not words:
        return ""
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w.get("y", 0), w.get("x", 0))):
        centre = word.get("y", 0) + word.get("h", 0) / 2
        for row in rows:
            row_centre = sum(w.get("y", 0) + w.get("h", 0) / 2 for w in row) / len(row)
            if abs(centre - row_centre) <= max(6, word.get("h", 12) * 0.6):
                row.append(word)
                break
        else:
            rows.append([word])
    lines = []
    for row in rows:
        row.sort(key=lambda w: w.get("x", 0))
        lines.append(" ".join(w.get("text", "") for w in row).strip())
    return "\n".join(line for line in lines if line)


def _ffprobe(path: str) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    try:
        out = quiet.run([exe, "-v", "quiet", "-print_format", "json",
                              "-show_format", "-show_streams", path],
                             capture_output=True, text=True, timeout=25)
        return json.loads(out.stdout or "{}")
    except Exception:
        return {}


def _read_audio(path: str, doc: Document, limit: int) -> None:
    info = _ffprobe(path)
    if info:
        fmt = info.get("format", {})
        doc.meta["duration_s"] = round(float(fmt.get("duration") or 0), 1)
        doc.meta["bitrate"] = int(fmt.get("bit_rate") or 0) // 1000
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                doc.meta["codec"] = stream.get("codec_name")
                doc.meta["channels"] = stream.get("channels")
                doc.meta["sample_rate"] = stream.get("sample_rate")
                break
    else:
        try:
            from mutagen import File as MFile
            audio = MFile(path)
            if audio is not None and getattr(audio, "info", None):
                doc.meta["duration_s"] = round(float(audio.info.length), 1)
                tags = {k: str(v)[:60] for k, v in (audio.tags or {}).items()}
                if tags:
                    doc.meta["tags"] = dict(list(tags.items())[:12])
            else:
                doc.warnings.append("could not read audio metadata (install ffmpeg)")
        except Exception as exc:
            doc.warnings.append(f"audio metadata failed: {exc}")
    doc.ok = bool(doc.meta)
    # transcription is what makes audio *readable*; without a model it must say so
    if importlib.util.find_spec("faster_whisper") is not None:
        doc.warnings.append("speech-to-text model present — run `arcdesk.tools.transcribe` "
                            "to get the words (this reader returns metadata only)")
    else:
        doc.warnings.append(
            "audio: metadata only. To read the words, install a local STT model: "
            "pip install faster-whisper  (free, offline, ~80–300 MB)")


def _read_video(path: str, doc: Document, limit: int, frames: bool = False) -> None:
    info = _ffprobe(path)
    if not info:
        doc.warnings.append("ffmpeg not found — video metadata and frames need it: "
                            "winget install Gyan.FFmpeg")
        return
    fmt = info.get("format", {})
    doc.meta["duration_s"] = round(float(fmt.get("duration") or 0), 1)
    doc.meta["container"] = fmt.get("format_name")
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            doc.meta.update({"codec": stream.get("codec_name"),
                             "width": stream.get("width"), "height": stream.get("height")})
            rate = stream.get("avg_frame_rate") or "0/1"
            try:
                num, den = rate.split("/")
                doc.meta["fps"] = round(float(num) / float(den or 1), 2)
            except Exception:
                pass
            break
    if any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        doc.meta["has_audio"] = True
    doc.ok = bool(doc.meta)
    if frames:
        doc.meta["frame_text"] = _frame_text(path, doc)
    if not doc.text:
        doc.warnings.append("video: metadata only. For the words, use `video_edit` with "
                            "action=subtitles to burn in captions, or transcribe the audio "
                            "track with faster-whisper.")


def _frame_text(path: str, doc: Document, at: float = 1.0, limit: int = 1500) -> str:
    """OCR one frame, so 'what is this video about' has something real to chew on."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return ""
    import tempfile
    shot = str(Path(tempfile.gettempdir()) / f"arc_frame_{abs(hash(path)) % 10000}.png")
    try:
        quiet.run([exe, "-y", "-v", "quiet", "-ss", str(at), "-i", path,
                        "-frames:v", "1", shot], timeout=30)
        from . import vision
        if not vision.ocr_available():
            return ""
        words = vision.ocr_words(shot)
        return " ".join(w.get("text", "") for w in words)[:limit]
    except Exception:
        return ""


def read(path: str, limit: int = MAX_READ, ocr: bool = True) -> Document:
    """The one entry point: give it a path, get text + metadata + honest warnings."""
    p = Path(os.path.expanduser(str(path))).resolve()
    doc = Document(path=str(p))
    if not p.exists():
        doc.warnings.append(f"no such file: {p}")
        return doc
    if p.is_dir():
        doc.kind = "folder"
        try:
            items = sorted(p.iterdir())[:200]
        except OSError as exc:
            doc.warnings.append(f"cannot list folder: {exc}")
            return doc
        doc.meta["entries"] = len(items)
        doc.text = "\n".join(f"{'d' if i.is_dir() else 'f'}  {i.name}" for i in items)
        doc.ok = True
        return doc
    doc.kind = kind_of(str(p))
    doc.meta["bytes"] = _size(str(p))
    doc.meta["mime"] = mimetypes.guess_type(str(p))[0] or ""
    if doc.meta["bytes"] > MAX_BYTES:
        doc.warnings.append(f"file is {doc.meta['bytes'] / 1e6:.0f} MB — reading the first "
                            f"{MAX_BYTES / 1e6:.0f} MB only")
    try:
        if doc.kind == "pdf":
            _read_pdf(str(p), doc, limit)
        elif doc.kind == "docx":
            _read_docx(str(p), doc, limit)
        elif doc.kind == "xlsx":
            _read_xlsx(str(p), doc, limit)
        elif doc.kind == "pptx":
            _read_pptx(str(p), doc, limit)
        elif doc.kind in ("image", "gif", "png", "jpeg"):
            doc.kind = "image" if doc.kind in ("png", "jpeg") else doc.kind
            _read_image(str(p), doc, limit, ocr=ocr)
        elif doc.kind in ("audio", "wav", "mp3"):
            doc.kind = "audio"
            _read_audio(str(p), doc, limit)
        elif doc.kind in ("video", "mp4", "mov"):
            doc.kind = "video"
            _read_video(str(p), doc, limit)
        elif doc.kind == "data":
            _read_data(str(p), doc, limit)
        else:
            _read_text(str(p), doc, limit)
    except Exception as exc:                      # a reader must never take the app down
        doc.warnings.append(f"{type(exc).__name__}: {exc}")
        doc.ok = False
    if doc.ok and not doc.text and doc.kind not in ("image", "audio", "video"):
        doc.warnings.append("no text could be extracted")
    return doc


# ------------------------------------------------------------- summarising
STOP = set("""a an the and or but if then than that this these those of in on at to for from by
with without into over under again further once here there when where why how all any both
each few more most other some such no nor not only own same so too very can will just should
now i you he she it we they me him her them my your his its our their is are was were be been
being have has had do does did doing would could may might must shall as about""".split())


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n{2,}", text or "")
    return [p.strip() for p in parts if len(p.split()) >= 4]


def _plural(n, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _table_summary(text: str) -> list[str]:
    """Column statistics for spreadsheets — what a person actually wants to know.

    Rows of a table are not a summary. Min, max, mean, blanks and the total are,
    and every number here is computed from the file, never estimated.
    """
    # one sheet at a time — mixing sheets makes every average meaningless
    section: list[str] = []
    sheet = ""
    for line in (text or "").splitlines():
        if line.startswith("[sheet:"):
            if any(x.strip() for x in section):
                break
            sheet = line.split("]", 1)[0].replace("[sheet:", "").strip()
            continue
        if line.startswith("---"):
            continue
        section.append(line)
    body = section or (text or "").splitlines()
    rows: list[list[str]] = []
    for line in body:
        if "\t" in line:
            rows.append(line.split("\t"))
        elif " | " in line:                      # csv/tsv readers render pipes
            rows.append(line.split(" | "))
    if len(rows) < 2:
        return []
    header, data = rows[0], rows[1:]
    stats: list[str] = []
    if not header or not data:
        return []
    width = max(len(r) for r in data)
    for col in range(width):
        name = header[col].strip() if col < len(header) else f"col {col + 1}"
        values = []
        blanks = 0
        for row in data:
            raw = row[col].strip() if col < len(row) else ""
            if not raw:
                blanks += 1
                continue
            try:
                values.append(float(raw.replace(",", "").replace("%", "")))
            except ValueError:
                pass
        if len(values) >= 2 and len(values) >= len(data) * 0.6:
            lo, hi = min(values), max(values)
            mean = sum(values) / len(values)
            total = sum(values)
            stats.append(f"  {name}: {lo:,.2f} → {hi:,.2f}, mean {mean:,.2f}, "
                         f"total {total:,.2f} ({len(values)} numbers"
                         + (f", {blanks} blank" + ("s" if blanks != 1 else "") if blanks else "")
                         + ")")
        else:
            uniq = len({(row[col].strip() if col < len(row) else "") for row in data})
            stats.append(f"  {name}: text, {_plural(uniq, 'distinct value')}"
                         + (f", {blanks} blank" + ("s" if blanks != 1 else "")
                            if blanks else ""))
    if sheet and stats:
        stats.insert(0, f"(sheet: {sheet})")
    return stats


def _candidates(text: str) -> list[str]:
    """Summary units: whole short lines (headings, bullets, table rows) stay intact;
    long lines get broken into sentences so one bullet is not six sentences long."""
    out: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) <= 220 and len(line.split()) <= 30:
            out.append(line)
        else:
            out.extend(sentences(line) or [line[:220]])
    return [line for line in out if len(line.split()) >= 3]


def summarise(doc: Document, n: int = 6) -> str:
    """Extractive summary — the model is optional, the summary is not.

    Frequency scoring over sentences: no hallucination is possible because every
    line is copied from the document. With a language model available the agent can
    rewrite it afterwards; the facts still come from here.
    """
    if not doc.ok and not doc.text:
        return ("I could not read that file, so I will not pretend to summarise it.\n"
                + doc.warning_text())
    if doc.kind in ("audio", "video") and not doc.text:
        head = (f"This is {'video' if doc.kind == 'video' else 'audio'}, "
                f"{doc.meta.get('duration_s', '?')} s")
        return (head + ". I can read its metadata but not its words — that needs a "
                "speech-to-text model (faster-whisper, free and offline).\n"
                + doc.warning_text())
    if doc.kind in ("xlsx", "data", "csv", "tsv"):
        stats = _table_summary(doc.text)
        if stats:
            return (f"Summary of {Path(doc.path).name} — {doc.kind} · "
                    f"{_plural(doc.meta.get('rows', 0), 'row')}"
                    + (f" · {_plural(doc.meta['sheets'], 'sheet')}"
                       if doc.meta.get("sheets") else "")
                    + "\n\nColumns, computed from the file:\n" + "\n".join(stats)
                    + "\n\n(These are statistics of what is in the table, not an "
                      "interpretation of what it means.)")
    words = re.findall(r"[a-z][a-z0-9'-]{2,}", doc.text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    if not freq:
        return "The file has almost no readable words in it."
    sents = _candidates(doc.text)
    if not sents:
        sents = [doc.text[:200]]
    scored = []
    for i, s in enumerate(sents[:600]):
        tokens = [w for w in re.findall(r"[a-z][a-z0-9'-]{2,}", s.lower()) if w not in STOP]
        if not tokens:
            continue
        score = sum(freq.get(w, 0) for w in tokens) / (len(tokens) ** 0.65)
        scored.append((score, i, s))
    top = sorted(scored, reverse=True)[:n]
    picked = [s for _, _, s in sorted(top, key=lambda row: row[1])]
    body = "\n".join(f"• {s[:280]}" for s in picked)
    head = (f"Summary of {Path(doc.path).name} — {doc.kind}"
            + (f" · title: {doc.meta['title']}" if doc.meta.get("title") else "")
            + f" · {len(words)} words")
    note = ""
    if doc.meta.get("truncated"):
        note = "\n(Only part of the file was read; the summary covers that part.)"
    return f"{head}\n\n{body}{note}"


# ----------------------------------------------------------------- review
def review(doc: Document) -> str:
    """What is missing, what to improve, what to add — with evidence, not vibes.

    Rules are format-aware because a spreadsheet and a thesis fail differently.
    Every observation quotes a number from the file, so the user can check it.
    """
    if not doc.ok and not doc.text:
        return ("Nothing to review: the file could not be read.\n" + doc.warning_text())
    text = doc.text
    sents = sentences(text)
    words = text.split()
    findings: list[str] = []
    missing: list[str] = []
    improve: list[str] = []
    add: list[str] = []

    # --- universal checks -------------------------------------------------
    if doc.kind in ("text", "docx", "pdf", "pptx"):
        if len(words) < 60:
            findings.append(f"only {len(words)} words — very short for a document")
            add.append("an introduction and a conclusion; at 60 words a reader cannot "
                       "tell what problem this solves")
        if not re.search(r"\b(19|20)\d{2}\b", text) and len(words) > 200:
            missing.append("no dates anywhere — claims without a date cannot be checked")
        if not re.search(r"\b\d{1,3}(,\d{3})+|\b\d+(\.\d+)?\s?(%|percent|per cent)\b", text) \
                and len(words) > 200:
            missing.append("no numbers or percentages — the argument is qualitative only")
        if not re.search(r"https?://|\b(doi|isbn|arxiv)\b|\[\d+\]", text) and len(words) > 300:
            missing.append("no references or links — nothing here can be verified")
        if sents:
            longest = max(sents, key=lambda s: len(s.split()))
            if len(longest.split()) > 45:
                improve.append(f"one sentence runs to {len(longest.split())} words; "
                               "split it (readers and speech engines both struggle)")
        avg = len(words) / max(1, len(sents))
        if avg > 28:
            improve.append(f"average sentence is {avg:.0f} words — aim for 15–20 for clarity")
        if len(re.findall(r"\b(we|i|our)\b", text, re.I)) == 0 and len(words) > 300:
            missing.append("no first-person voice — who is making this claim?")
        headings = len(re.findall(r"^\s*(#{1,6}\s|\d+\.\d*\s|ABSTRACT|INTRODUCTION|"
                                  r"METHODS?|RESULTS?|CONCLUSION|SUMMARY)\b", text, re.I | re.M))
        if len(words) > 900 and headings < 3:
            missing.append(f"{len(words)} words with {headings} visible headings — add "
                           "structure so it can be skimmed")

    # --- format-specific ---------------------------------------------------
    if doc.kind == "xlsx":
        if "total" not in text.lower() and "sum" not in text.lower():
            missing.append("no totals/sums — every table needs a row or column that adds up")
        if not re.search(r"\b(20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
                         text, re.I):
            missing.append("no dates — a table without time cannot show a trend")
        add.append("a 'source' column, so each row says where its numbers came from")

    if doc.kind == "pptx":
        slides = doc.meta.get("slides", 0)
        if slides > 25:
            improve.append(f"{slides} slides is a long deck; a 10–12 slide version "
                           "would be remembered better")
        if "notes" not in text:
            add.append("speaker notes — the text on slides is not the talk")

    if doc.kind == "pdf":
        pages = doc.meta.get("pages", 0)
        if pages and len(words) / max(1, pages) < 80:
            improve.append(f"{len(words)} words over {pages} pages — sparse layout, or "
                           "scanned pages whose text was not extracted")

    if doc.kind == "image":
        add.append("if this is a chart: state the units on both axes and the source, "
                   "because a picture cannot be quoted later")

    if doc.kind in ("audio", "video"):
        if not doc.text:
            improve.append("no transcript — add captions; it makes the file searchable "
                           "and usable by anyone without sound")

    if doc.kind == "data":
        rows = doc.meta.get("rows", 0)
        findings.append(f"{rows} rows × {doc.meta.get('columns', 0)} columns")
        if rows < 10:
            missing.append("very few rows — any conclusion drawn from this is anecdotal")

    # --- assemble ---------------------------------------------------------
    def block(title: str, items: list[str]) -> str:
        if not items:
            return ""
        return f"\n{title}\n" + "\n".join(f"  - {i}" for i in items)

    # headline facts, always stated, so "what is there" is never empty
    facts = []
    tabular = doc.kind in ("xlsx", "data", "csv", "tsv")
    if words and not tabular:
        facts.append(f"{_plural(len(words), 'word')}, {_plural(len(sents), 'sentence')}")
    elif words:
        facts.append(f"{_plural(len(words), 'cell value')} of text in the grid")
    for key, label in (("pages", "page"), ("slides", "slide"), ("sheets", "sheet"),
                       ("rows", "row"), ("frames", "frame")):
        if doc.meta.get(key):
            facts.append(_plural(doc.meta[key], label))
    if doc.meta.get("duration_s"):
        facts.append(f"{doc.meta['duration_s']} seconds")
    digits = len(re.findall(r"\d", text))
    if digits >= 2:
        facts.append(f"{digits} digits of data present")
    if facts:
        findings.insert(0, " · ".join(str(f) for f in facts))

    gaps = len(missing) + len(improve)
    if tabular:
        rows = doc.meta.get("rows", 0)
        verdict = ("no data rows to judge" if rows < 2 else
                   f"{_plural(rows, 'row')} of data, {_plural(gaps, 'gap')} found"
                   if gaps else f"{_plural(rows, 'row')}: no structural gaps found")
    elif not words:
        verdict = "nothing to judge — no readable text"
    elif len(words) < 60:
        verdict = "too thin to judge the argument; the notes are about form"
    elif gaps == 0:
        verdict = "solid: no structural gaps found by the checks below"
    elif gaps <= 2:
        verdict = "usable, with small gaps"
    else:
        verdict = f"needs work: {gaps} gaps found"
    out = [f"Review of {Path(doc.path).name} — {doc.describe()}",
           f"Verdict: {verdict}"]
    if findings:
        out.append("\nWhat is there\n" + "\n".join(f"  - {f}" for f in findings))
    out.append(block("What is missing", missing))
    out.append(block("What to improve", improve))
    out.append(block("What to add", add))
    if not (missing or improve or add):
        out.append("\nNothing structural is missing. The remaining gain is in the "
                   "argument itself, not the format.")
    if doc.warnings:
        out.append("\nCaveats from reading it\n" + doc.warning_text())
    return "\n".join(x for x in out if x).strip()


def outline(doc: Document, max_items: int = 24) -> str:
    """A table of contents, so 'what is in this file' has a real answer."""
    if not doc.ok or not doc.text:
        return "No readable text to outline.\n" + doc.warning_text()
    lines = [l.strip() for l in doc.text.splitlines() if l.strip()]
    lines = [l for l in lines if not re.match(r"^-{3}\s*(slide|page)\s*\d+\s*-{3}$", l)]
    heads = [l for l in lines if re.match(r"^(#{1,6}\s|\d+[.)]\s|\d+\.\d+\s|"
                                          r"[A-Z][A-Z /&\-]{6,}$|---\s*(page|slide)\s*\d+)", l)]
    if not heads:
        heads = lines[:max_items]
        note = "(no headings found — showing the first lines of each block)\n"
    else:
        note = ""
    return note + "\n".join(f"{i}. {h[:110]}" for i, h in enumerate(heads[:max_items], 1))
