"""
Video color-grading engine for drone footage, using the same philosophy as
enhance_photo.py: gentle contrast, restrained/protected saturation via
vibrance, subtle warm-highlight/cool-shadow split tone, light denoise,
and mild sharpening. Implemented as an FFmpeg filter chain so it scales to
any resolution/frame rate without decoding frames in Python.

intensity: 0-200, 100 = the default look approved by the user.
warmth: -50..50, 0 = neutral.
"""

import subprocess
import shlex


def _probe_bitrate(path_in: str) -> int:
    """Return the source video bitrate in bits/s, so the output encode can
    match it instead of using a fixed value (a fixed low bitrate is what
    caused visible quality loss during testing)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path_in,
    ]
    try:
        out = subprocess.check_output(cmd).decode().strip()
        return int(out)
    except Exception:
        return 12_000_000  # sane fallback: ~12 Mbps


def build_filter_chain(intensity: float = 100, warmth: float = 0) -> str:
    k = max(0.0, intensity) / 100.0
    warm_shift = warmth / 50.0  # -1..1

    contrast = 1 + 0.02 * k
    gamma = 1 + 0.06 * k
    brightness = 0.01 * k
    vibrance_amt = 0.14 * k
    rh = 0.015 * k + 0.01 * warm_shift
    bh = -0.01 * k - 0.008 * warm_shift
    bs = 0.015 * k - 0.008 * warm_shift
    rs = -0.01 * k + 0.008 * warm_shift
    sharpen_amt = 0.15 * min(k, 1.3)

    filters = [
        "hqdn3d=1:0.8:1.5:1.5",
        f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}:gamma={gamma:.4f}:saturation=1.0",
        f"vibrance=intensity={vibrance_amt:.4f}",
        f"colorbalance=rh={rh:.4f}:bh={bh:.4f}:bs={bs:.4f}:rs={rs:.4f}",
        f"unsharp=5:5:{sharpen_amt:.4f}:5:5:0.0",
    ]
    return ",".join(filters)


def enhance_video(path_in: str, path_out: str, intensity: float = 100, warmth: float = 0):
    filter_chain = build_filter_chain(intensity, warmth)
    source_bitrate = _probe_bitrate(path_in)
    target_bitrate = max(8_000_000, min(source_bitrate, 40_000_000))

    cmd = [
        "ffmpeg", "-y",
        "-i", path_in,
        "-vf", filter_chain,
        "-c:v", "libx264",
        "-preset", "fast",
        "-b:v", str(target_bitrate),
        "-maxrate", str(int(target_bitrate * 1.5)),
        "-bufsize", str(int(target_bitrate * 2)),
        "-c:a", "copy",
        path_out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")
    return path_out
