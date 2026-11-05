#!/usr/bin/env python3
"""Rebuild the checked-in Windows ICO from the pinned upstream artwork.

Requires Pillow for regeneration only. Packaging uses the checked-in ICO and
does not need Pillow, Python image packages or an upstream checkout.
"""
import hashlib
from pathlib import Path

SOURCE_SHA256 = '757f00b34f506cc7419437f62951dad7419e7270ae99658f7b554ba3a39f9edd'
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main():
    from PIL import Image

    assets = Path(__file__).resolve().parents[1] / 'installer/windows/assets'
    source = assets / 'arcium-app-1024.png'
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise SystemExit('Upstream artwork digest differs; review its provenance before regenerating.')
    with Image.open(source) as original:
        if original.size != (1024, 1024):
            raise SystemExit('Expected the original 1024px Arcium artwork.')
        # Each representation is derived directly from the original artwork.
        # Explicit frames avoid chained resampling and preserve transparency.
        frames = [original.convert('RGBA').resize((n, n), Image.Resampling.LANCZOS) for n in SIZES]
        output = assets / 'Arcium.ico'
        frames[-1].save(output, format='ICO', sizes=[(n, n) for n in SIZES],
                        append_images=frames[:-1])
    print('Windows icon:', output)
    print('Sizes:', ', '.join(str(n) for n in SIZES))
    print('SHA256:', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
