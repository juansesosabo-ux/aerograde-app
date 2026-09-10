"""
Video color-grading engine for drone footage, using the same philosophy as
enhance_photo.py: gentle contrast, restrained/protected saturation via
vibrance, subtle warm-highlight/cool-shadow split tone, light denoise,
and mild sharpening. Implemented as an FFmpeg filter chain.

Uses CRF-based encoding with a bitrate cap instead of forcing a fixed
average bitrate - lighter on CPU/RAM, which matters on smaller hosting
plans, while still preserving visual quality.

intensity: 0-200, 100 = the default look approved by the user.
warmth: -50..50, 0 = neutral.
"""

import subprocess


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

    cmd = [
        "ffmpeg", "-y",
        "-i", path_in,
        "-vf", filter_chain,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-maxrate", "12000000",
        "-bufsize", "24000000",
        "-threads", "2",
        "-c:a", "copy",
        path_out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (code {result.returncode}): {result.stderr[-1500:]}")
    return path_out
