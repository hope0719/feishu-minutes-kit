"""Audio file discovery and ffmpeg helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

AUDIO_EXTENSIONS = (".ogg", ".m4a", ".mp3", ".wav", ".aac", ".mp4")
_MEAN_DB_RE = re.compile(r"mean_volume:\s*(-?[\d.]+) dB")


def find_audio(directory: Path) -> Path | None:
    """Return the first non-empty audio file in *directory*, if any."""

    if not directory.is_dir():
        return None
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS and path.stat().st_size > 0:
            return path
    return None


def mean_volume(path: Path, *, ffmpeg: str = "ffmpeg") -> float:
    """Return the mean volume in dB, or ``0.0`` when ffmpeg cannot report it."""

    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    match = _MEAN_DB_RE.search(completed.stderr)
    return float(match.group(1)) if match else 0.0


def extract_pcm(
    audio: Path,
    start: int,
    duration: int,
    dest: Path,
    *,
    ffmpeg: str = "ffmpeg",
) -> bool:
    """Cut a 16 kHz mono s16le PCM slice and return whether it succeeded."""

    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(audio),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "s16le",
            str(dest),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return completed.returncode == 0 and dest.is_file() and dest.stat().st_size > 0
