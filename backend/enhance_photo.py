"""
Photo color-grading engine for drone stills.

Philosophy (validated with the user against colorist/photographer best
practices): protect already-saturated colors (sky, foliage) instead of
boosting them, use vibrance instead of blanket saturation, keep contrast
gentle, and sharpen only real edges (never flat sky) to avoid halos and
banding. `intensity` scales all of this together; `warmth` only shifts
the highlight/shadow split-tone.

intensity: 0-200, 100 = the default look approved by the user.
warmth: -50..50, 0 = neutral. Positive = warmer highlights, negative = cooler.
"""

import cv2
import numpy as np
from PIL import Image


def auto_white_balance(img, clip_percent=0.4):
    result = np.zeros_like(img, dtype=np.float32)
    for c in range(3):
        channel = img[:, :, c].astype(np.float32)
        low, high = np.percentile(channel, [clip_percent, 100 - clip_percent])
        if high - low < 1e-5:
            result[:, :, c] = channel
            continue
        channel = np.clip((channel - low) / (high - low) * 255.0, 0, 255)
        result[:, :, c] = channel
    return result.astype(np.uint8)


def gentle_local_contrast(img, clip_limit=1.15, tile=8):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    l2 = clahe.apply(l)
    lab2 = cv2.merge((l2, a, b))
    return cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)


def vibrance(img, intensity=0.14):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    protect_weight = 1.0 - (s / 255.0)
    s_new = s + intensity * 255.0 * protect_weight * (s / 255.0 + 0.15)
    s_new = np.clip(s_new, 0, 255)
    hsv2 = cv2.merge((h, s_new, v)).astype(np.uint8)
    return cv2.cvtColor(hsv2, cv2.COLOR_HSV2BGR)


def restrain_sky_and_greens(img, sky_reduction=0.08, green_reduction=0.06):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    sky_mask = np.clip((h - 85) / 15, 0, 1) * np.clip((150 - h) / 15, 0, 1)
    green_mask = np.clip((h - 30) / 10, 0, 1) * np.clip((95 - h) / 10, 0, 1)
    s = s * (1 - sky_mask * sky_reduction)
    s = s * (1 - green_mask * green_reduction)
    s = np.clip(s, 0, 255)
    hsv2 = cv2.merge((h, s, v)).astype(np.uint8)
    return cv2.cvtColor(hsv2, cv2.COLOR_HSV2BGR)


def warm_highlights_cool_shadows(img, warm_amt=4, cool_amt=3):
    img_f = img.astype(np.float32)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    highlight_w = np.clip((gray - 0.55) / 0.45, 0, 1)[:, :, None]
    shadow_w = np.clip((0.45 - gray) / 0.45, 0, 1)[:, :, None]
    img_f[:, :, 2] += (highlight_w[:, :, 0] * warm_amt)
    img_f[:, :, 0] -= (highlight_w[:, :, 0] * warm_amt * 0.5)
    img_f[:, :, 0] += (shadow_w[:, :, 0] * cool_amt)
    img_f[:, :, 2] -= (shadow_w[:, :, 0] * cool_amt * 0.5)
    return np.clip(img_f, 0, 255).astype(np.uint8)


def gentle_s_curve(img, strength=0.045):
    img_f = img.astype(np.float32) / 255.0
    img_f = img_f + strength * (img_f - 0.5) * (1 - np.abs(2 * img_f - 1))
    return np.clip(img_f * 255, 0, 255).astype(np.uint8)


def edge_aware_sharpen(img, amount=0.35, radius=1.6, threshold=2.5):
    img_f = img.astype(np.float32)
    blurred = cv2.GaussianBlur(img_f, (0, 0), radius)
    diff = img_f - blurred
    edge_strength = np.mean(np.abs(diff), axis=2, keepdims=True)
    mask = np.clip((edge_strength - threshold) / (threshold * 2), 0, 1)
    sharpened = img_f + amount * diff * mask
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def denoise(img, strength=2.5):
    return cv2.fastNlMeansDenoisingColored(img, None, strength, strength, 7, 21)


def enhance_image(path_in: str, path_out: str, intensity: float = 100, warmth: float = 0):
    """
    intensity: 0-200 (100 = approved default strength)
    warmth: -50..50 (0 = neutral split tone)
    """
    k = max(0.0, intensity) / 100.0  # 1.0 = default
    warm_shift = warmth / 50.0       # -1..1

    img = cv2.imread(path_in)
    if img is None:
        raise ValueError(f"Could not read {path_in}")

    out = auto_white_balance(img, clip_percent=0.4)
    out = gentle_local_contrast(out, clip_limit=1.0 + 0.15 * k, tile=8)
    out = denoise(out, strength=2.5)
    out = restrain_sky_and_greens(out, sky_reduction=0.08 * k, green_reduction=0.06 * k)
    out = vibrance(out, intensity=0.14 * k)

    base_warm, base_cool = 4, 3
    out = warm_highlights_cool_shadows(
        out,
        warm_amt=max(0, base_warm * k + base_warm * warm_shift),
        cool_amt=max(0, base_cool * k - base_cool * warm_shift),
    )
    out = gentle_s_curve(out, strength=0.045 * k)
    out = edge_aware_sharpen(out, amount=0.35 * min(k, 1.3), radius=1.6, threshold=2.5)

    cv2.imwrite(path_out, out, [cv2.IMWRITE_JPEG_QUALITY, 97])

    try:
        original = Image.open(path_in)
        exif_bytes = original.info.get("exif")
        if exif_bytes:
            result = Image.open(path_out)
            result.save(path_out, quality=97, exif=exif_bytes, subsampling=0)
    except Exception:
        pass

    return path_out
