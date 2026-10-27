#!/usr/bin/env bash
# Provision the *verification* toolchain without root, in one command.
#
#     source tools/sandbox_env.sh          # provision + export, then run tests
#     source tools/sandbox_env.sh quiet    # provision silently
#
# Why this file exists: this build sandbox has no root and wipes anything installed
# outside /home/user between sessions. ffmpeg, Tesseract and the Qt shared libraries
# therefore disappear, and the test suite starts failing for reasons that have
# nothing to do with the code — a red board that lies is worse than no board.
#
# Strategy: `apt-get download` the .deb files (that needs no privileges), unpack them
# with `dpkg -x` into /tmp/arcenv, and put them on PATH / LD_LIBRARY_PATH for the
# current shell only. Nothing on the system is modified, nothing needs sudo, and a
# reboot simply means running this file again.
#
# On the user's real Windows machine none of this is needed: `winget install`
# (or the installer) provides everything. This is a sandbox convenience, not a
# shipping dependency — ARC itself only ever calls the binaries, wherever they are.
set -u

ROOT="${ARCENV_ROOT:-/tmp/arcenv}"
QUIET="${1:-}"
say() { [ "$QUIET" = "quiet" ] || echo "$@"; }

if [ ! -d "$ROOT/bin" ]; then
  say "provisioning $ROOT (no root needed, nothing installed system-wide)…"
  mkdir -p "$ROOT/debs" "$ROOT/pkg"
  cd "$ROOT/debs" || return 1

  # ffmpeg + the tesseract engine + the Qt runtime libraries PySide6 needs when
  # there is no display. Package names are Debian 13 (trixie).
  PKGS="
        libasound2t64 libaom3 libva2 libva-drm2 libva-x11-2 libvdpau1 libvpl2 ocl-icd-libopencl1
        libavutil59 libcodec2-1.2 libgsm1 libhwy1t64 libjxl0.11 libmp3lame0 libopus0 librav1e0.7
        libshine3 libsnappy1v5 libspeex1 libsvtav1enc2 libsoxr0 libswresample5 libtheoradec1 libogg0
        libtheoraenc1 libtwolame0 libvorbis0a libvorbisenc2 libvpx9 libx264-164 libnuma1 libx265-215
        libxvidcore4 libzvbi-common libzvbi0t64 libavcodec61 libraw1394-11 libavc1394-0 libunibreak6 libass9
        libudfread0 libbluray2 libchromaprint1 libdvdread8t64 libdvdnav4 libgme0 libmpg123-0t64 libvorbisfile3
        libopenmpt0t64 librabbitmq4 libcjson1 libmbedcrypto16 librist4 libsrt1.5-gnutls libssh-4 libnorm1t64
        libpgm-5.3-0t64 libsodium23 libzmq5 libavformat61 libbs2b0 libflite1 libserd-0-0 libzix-0-0
        libsord-0-0 libsratom-0-0 liblilv-0-0 libmysofa1 libplacebo349 libasyncns0 libflac14 libsndfile1
        libpulse0 libsphinxbase3t64 libpocketsphinx3 libpostproc58 libsamplerate0 librubberband2 libswscale8 libvidstab1.1
        libzimg2 libavfilter10 libslang2 libcaca0 libcdio19t64 libcdio-cdda2t64 libcdio-paranoia2t64 libusb-1.0-0
        libdc1394-25 libiec61883-0 libjack-jackd2-0 libopenal-data libopenal1 libdecor-0-0 libwayland-cursor0 libwayland-egl1
        libxkbcommon0 libsdl2-2.0-0 libavdevice61 ffmpeg libigdgmm12 libaacs0 libatk1.0-0t64 libatk-bridge2.0-0t64
        libavahi-common-data libavahi-common3 libavahi-client3 libbdplus0 libcloudproviders0 libcolord2 libepoxy0 libxdamage1
        libtesseract5 libleptonica6 tesseract-ocr tesseract-ocr-eng libarchive13t64
        libcurl4t64 libxkbcommon-x11-0 libgif7 libjpeg62-turbo libopenjp2-7 libtiff6 libwebp7 libwebpmux3"
  # two attempts: the mirror occasionally drops one package, and a silently missing
  # .deb turns into "error while loading shared libraries" twenty minutes later.
  for pkg in $PKGS; do
    apt-get download "$pkg" >/dev/null 2>&1 || apt-get download "$pkg" >/dev/null 2>&1 || true
  done
  [ "$QUIET" = "quiet" ] || echo "  downloaded $(ls ./*.deb 2>/dev/null | wc -l) packages"
  for deb in ./*.deb; do dpkg -x "$deb" "$ROOT/pkg" 2>/dev/null || true; done
  mkdir -p "$ROOT/bin"
  ln -sf "$ROOT/pkg/usr/bin/ffmpeg" "$ROOT/bin/ffmpeg" 2>/dev/null
  ln -sf "$ROOT/pkg/usr/bin/ffprobe" "$ROOT/bin/ffprobe" 2>/dev/null
  ln -sf "$ROOT/pkg/usr/bin/ffplay" "$ROOT/bin/ffplay" 2>/dev/null
  ln -sf "$ROOT/pkg/usr/bin/tesseract" "$ROOT/bin/tesseract" 2>/dev/null
  echo "$ROOT" >/dev/null
fi

export PATH="$ROOT/bin:$PATH"
export LD_LIBRARY_PATH="$ROOT/pkg/usr/lib/x86_64-linux-gnu:$ROOT/pkg/usr/lib/x86_64-linux-gnu/pulseaudio:${LD_LIBRARY_PATH:-}"
TESSDIR="$(ls -d "$ROOT"/pkg/usr/share/tesseract-ocr/*/tessdata 2>/dev/null | head -1)"
[ -n "${TESSDIR:-}" ] && export TESSDATA_PREFIX="$TESSDIR"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-dummy}"

# PySide6 (if pip can reach the index). Skipped silently when it is already there.
python3 -c "import PySide6" >/dev/null 2>&1 || pip install -q PySide6-Essentials >/dev/null 2>&1 || true
# `uvx` — the MCP presets run their Python servers through it. One test asserts that
# enable_all() actually enabled them, so this is a test dependency, not a runtime one.
command -v uvx >/dev/null 2>&1 || pip install -q uv >/dev/null 2>&1 || true

# A binary that exists but cannot load is worse than a missing one — say so here.
broken=""
for bin in ffmpeg ffprobe ffplay tesseract; do
  [ -e "$ROOT/bin/$bin" ] || continue
  "$ROOT/bin/$bin" -version >/dev/null 2>&1 || "$ROOT/bin/$bin" --version >/dev/null 2>&1 \
    || broken="$broken $bin"
done
[ -n "$broken" ] && say "WARNING: cannot start:$broken — delete $ROOT and re-run this file"

say ""
say "ready:"
for bin in ffmpeg ffprobe ffplay tesseract; do
  if command -v "$bin" >/dev/null 2>&1; then say "  $bin  $(command -v "$bin")"; fi
done
python3 -c "import PySide6; print('  PySide6', PySide6.__version__)" 2>/dev/null \
  || say "  PySide6  (not installed — Qt tests will skip)"
say ""
