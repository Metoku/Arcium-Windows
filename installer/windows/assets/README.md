# Arcium Windows icon

`arcium-app-1024.png` is the unmodified application artwork from
[dr-baker/Arcium](https://github.com/dr-baker/Arcium/blob/4e8f8e2bd3cdcab014ae9663907db93e915cb850/resources/branding/app_icon/raw.png),
the shared Arcium/Helium browser source. The upstream repository distributes
it under GPL-3.0; retain its attribution and the project LICENSE when distributing.
The pinned revision, Git blob and SHA256 are recorded in `source.json`.

`Arcium.ico` contains 16, 20, 24, 32, 40, 48, 64, 128 and 256px RGBA
representations, each resized directly from the original 1024px source.
No representation is enlarged from an extracted executable icon.

Packaging uses this ICO directly for setup, the launcher, shortcuts, Default
Apps and the uninstall entry. Its installed filename includes the icon digest
so Windows can distinguish it from an earlier cached icon.

To regenerate after installing Pillow, run:

```text
python scripts/generate_windows_icon.py
```

Pillow is a maintainer-only regeneration dependency. Normal installer builds
use the checked-in ICO without an image-processing dependency.
