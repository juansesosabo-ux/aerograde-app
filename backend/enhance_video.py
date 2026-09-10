"""
Video color-grading engine for drone footage.

Downscales to a max of 1080p before grading - DJI 4K/10-bit HEVC footage is
too heavy to decode+encode on small hosting plans (causes OOM kills). 1080p
is indistinguishable from 4K on a phone screen and cuts memory/CPU cost
dramatically.
"""

import subprocess


def build_filter_chain(intensity: float = 100, warmth: float = 0) -> str:
    k = max(0.0, intensity) / 100.0
    warm_shift = warmth / 50.0

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
        "scale='min(1920,iw)':-2:flags=fast_bilinear",
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
        "-map", "0:v:0",
        "-vf", filter_chain,
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "20",
        "-maxrate", "10000000",
        "-bufsize", "20000000",
        "-threads", "2",
        "-an",
        path_out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (code {result.returncode}): {result.stderr[-1500:]}")
    return path_out
