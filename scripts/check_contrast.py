"""Check the color tokens in src/styles/tokens.css, in both schemes.

Checks, per scheme:
  - WCAG 2.x contrast: 4.5:1 for text, 3:1 for graphics and large elements.
  - Color-vision deficiency: the two dependency colors (strong and weak) must
    stay apart after simulating protanopia, deuteranopia and tritanopia
    (Machado et al. 2009, severity 1.0): CIE76 dE >= 20 and L* difference >= 15.
  - The light scheme is written twice in tokens.css (media query and forced
    attribute); both copies must match.

Exit status is 1 if any check fails, 0 otherwise.
"""

import math
import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parent.parent / "src" / "styles" / "tokens.css"

# Pairs as (foreground, background, minimum ratio). Border is decorative and exempt.
TEXT = 4.5
GRAPHIC = 3.0
DARK_CHECKS = [
    ("text", "bg", TEXT),
    ("text", "surface", TEXT),
    ("text-muted", "bg", TEXT),
    ("text-muted", "surface", TEXT),
    ("accent-text", "bg", TEXT),
    ("accent-text", "surface", TEXT),
    ("link", "bg", TEXT),
    ("link", "surface", TEXT),
    ("link-hover", "bg", TEXT),
    ("on-accent", "accent", TEXT),
    ("on-brand", "surface-brand", TEXT),
    ("accent", "bg", GRAPHIC),
    ("border-strong", "bg", GRAPHIC),
    ("focus", "bg", GRAPHIC),
    ("focus", "surface", GRAPHIC),
    ("dep-strong", "bg", GRAPHIC),
    ("dep-weak", "bg", GRAPHIC),
    ("dep-strong", "surface", GRAPHIC),
    ("dep-weak", "surface", GRAPHIC),
]
# Rule: on dark, the accent sits only on bg; on surface, accent-text is used instead.
# On light the accent may also sit on surface.
LIGHT_CHECKS = DARK_CHECKS + [("accent", "surface", GRAPHIC)]

CVD_KINDS = ["protanopia", "deuteranopia", "tritanopia"]
MIN_DE76 = 20.0
MIN_DL = 15.0

# Machado et al. 2009, severity 1.0, applied in linear RGB.
CVD_MATRICES = {
    "protanopia": [[0.152286, 1.052583, -0.204868],
                   [0.114503, 0.786281, 0.099216],
                   [-0.003882, -0.048116, 1.051998]],
    "deuteranopia": [[0.367322, 0.860646, -0.227968],
                     [0.280085, 0.672501, 0.047413],
                     [-0.011820, 0.042940, 0.968881]],
    "tritanopia": [[1.255528, -0.076749, -0.178779],
                   [-0.078411, 0.930809, 0.147602],
                   [0.004733, 0.691367, 0.303900]],
}

# sRGB to XYZ (D65), and the white point used for CIELAB.
M_RGB2XYZ = [[0.41233895, 0.35762064, 0.18051042],
             [0.2126, 0.7152, 0.0722],
             [0.01932141, 0.11916382, 0.95034478]]
WHITE_POINT = [95.047, 100.0, 108.883]


def srgb_to_linear(channel):
    """Convert one sRGB channel (0-255) to linear light (0-1)."""
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_rgb(value):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def mat_mul(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def relative_luminance(value):
    return mat_mul(M_RGB2XYZ, [srgb_to_linear(c) for c in hex_to_rgb(value)])[1]


def wcag_contrast(a, b):
    lighter, darker = sorted([relative_luminance(a), relative_luminance(b)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def lab_f(t):
    epsilon = 216 / 24389
    kappa = 24389 / 27
    return t ** (1 / 3) if t > epsilon else (kappa * t + 16) / 116


def linear_to_lab(lin):
    """Convert linear sRGB (0-1 per channel) to CIELAB [L*, a*, b*]."""
    x, y, z = [100 * v for v in mat_mul(M_RGB2XYZ, lin)]
    fx, fy, fz = [lab_f(x / WHITE_POINT[0]), lab_f(y / WHITE_POINT[1]), lab_f(z / WHITE_POINT[2])]
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)]


def simulate(value, kind):
    """Return linear RGB of a hex color as seen with a color-vision deficiency."""
    lin = [srgb_to_linear(c) for c in hex_to_rgb(value)]
    return [max(0.0, min(1.0, v)) for v in mat_mul(CVD_MATRICES[kind], lin)]


def de76(lab_a, lab_b):
    return math.dist(lab_a, lab_b)


def parse_tokens(text):
    """Return (dark, light_media, light_forced) dicts of --color-* tokens.

    Only the three color blocks are read: the :root default, the light rule
    inside the prefers-color-scheme media query, and the data-theme="light" rule.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", text)
    dark, light_media, light_forced = {}, {}, {}
    for selector, body in blocks:
        selector = " ".join(selector.split())
        tokens = {
            name[len("--color-"):]: value.strip().lower()
            for name, value in re.findall(r"(--color-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", body)
        }
        if not tokens:
            continue
        if selector == ":root":
            dark = tokens
        elif selector == ':root:not([data-theme="dark"])':
            light_media = tokens
        elif selector == ':root[data-theme="light"]':
            light_forced = tokens
    return dark, light_media, light_forced


def check_scheme(name, tokens, checks):
    """Run contrast and CVD checks for one scheme. Return the number of failures."""
    failures = 0
    print(f"== {name}")
    for fg, bg, minimum in checks:
        fg_hex = tokens[fg]
        bg_hex = tokens[bg]
        ratio = wcag_contrast(fg_hex, bg_hex)
        ok = ratio >= minimum
        failures += 0 if ok else 1
        status = "OK" if ok else f"FAIL (< {minimum:.1f})"
        print(f"  contrast {fg:<14} on {bg:<14} {fg_hex} / {bg_hex}  {ratio:6.2f}:1  {status}")

    for kind in CVD_KINDS:
        strong = linear_to_lab(simulate(tokens["dep-strong"], kind))
        weak = linear_to_lab(simulate(tokens["dep-weak"], kind))
        de = de76(strong, weak)
        dl = abs(strong[0] - weak[0])
        ok = de >= MIN_DE76 and dl >= MIN_DL
        failures += 0 if ok else 1
        status = "OK" if ok else "FAIL"
        print(f"  cvd {kind:<13} dE76 {de:6.2f} (>= {MIN_DE76:.0f})  dL* {dl:6.2f} (>= {MIN_DL:.0f})  {status}")
    return failures


def main():
    dark, light_media, light_forced = parse_tokens(TOKENS.read_text(encoding="utf-8"))
    failures = 0

    if not dark or not light_media or not light_forced:
        print("FAIL: could not read the dark, light (media) and light (forced) blocks")
        return 1

    required = {fg for fg, _, _ in LIGHT_CHECKS} | {bg for _, bg, _ in LIGHT_CHECKS}
    required |= {"dep-strong", "dep-weak", "border-strong"}
    for label, tokens in (("dark", dark), ("light", light_forced)):
        missing = sorted(f"--color-{name}" for name in required if name not in tokens)
        if missing:
            print(f"FAIL: {label} scheme lacks tokens: {', '.join(missing)}")
            failures += 1

    if light_media != light_forced:
        print("FAIL: light scheme differs between the media query and data-theme=\"light\"")
        failures += 1

    failures += check_scheme("dark", dark, DARK_CHECKS)
    failures += check_scheme("light", light_forced, LIGHT_CHECKS)

    print(f"{'PASS' if failures == 0 else 'FAIL'}: {failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
