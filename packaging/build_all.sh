#!/usr/bin/env bash
# =============================================================================
#  Arc Desk — the same one command as build_all.bat, for Linux / macOS / CI.
#
#      ./packaging/build_all.sh            -> dist/ArcDesk/{ArcDesk,ArcDeskVoice}
#                                             + dist/ArcDesk-<os>.tar.xz
#
#  What it does NOT do: produce a Windows Setup.exe. PyInstaller cannot
#  cross-compile, so the .exe only ever comes out of a Windows machine (or the
#  GitHub Actions workflow in .github/workflows/build-windows.yml, which runs on
#  one). What it DOES do: prove the spec, the data files, the hidden imports and
#  the frozen entry points are correct — the same spec, the same pre-flight.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python3}"

echo
echo "[1/6] python: $($PY --version)"
echo "[2/6] required packages ..."
$PY -c "import PySide6, psutil" 2>/dev/null || $PY -m pip install -r requirements.txt
$PY -c "import vosk, sherpa_onnx" 2>/dev/null || $PY -m pip install -r requirements-voice.txt
# The voice libraries are not optional here: a frozen build cannot pip install later,
# so a build made without them ships with a dead wake word and a dead voice lock.
$PY -c "import vosk, sherpa_onnx" || { echo "  voice libraries still missing"; exit 1; }
echo "  ok"

echo "[3/6] portable runtimes (ffmpeg + node) — cached, Windows payload only ..."
$PY packaging/fetch_runtime.py || echo "  WARNING: runtimes not fetched (offline?). The build continues; media tools will report ffmpeg missing honestly."

echo "[4/6] static pre-flight ..."
$PY tools/packaging.py

echo "[5/6] building the two executables ..."
rm -rf dist/ArcDesk packaging/work
$PY -m PyInstaller --noconfirm --clean --distpath dist --workpath packaging/work packaging/arcdesk.spec
$PY tools/sizecheck.py --dist dist/ArcDesk || true

echo "[6/6] measuring the finished bundle ..."
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
OUT="dist/ArcDesk-$OS.tar.xz"
rm -f "$OUT"
tar -C dist -cJf "$OUT" ArcDesk
RAW=$(du -sb dist/ArcDesk | cut -f1)
PACKED=$(stat -c %s "$OUT" 2>/dev/null || stat -f %z "$OUT")
mb() { awk -v b="$1" 'BEGIN { printf "%.1f", b/1048576 }'; }
echo
echo "  ============================================================"
echo "   folder : dist/ArcDesk        $(mb "$RAW") MB"
echo "   packed : $OUT   $(mb "$PACKED") MB"
echo "   ratio  : $(awk -v a="$RAW" -v b="$PACKED" 'BEGIN { printf "%.0f%%", 100*b/a }') of the folder"
echo "   run    : dist/ArcDesk/ArcDesk --doctor"
echo "   NOTE   : this is not the Windows installer. Setup.exe needs a Windows"
echo "            machine: packaging\\build_all.bat, or the CI workflow."
echo "  ============================================================"
