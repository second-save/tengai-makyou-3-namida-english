# Fonts

Every font or glyph sheet the build reads ends up inside the released patch, so its licence must allow that. One row
per file; a font with no known licence doesn't go into a release.

| File | Source (URL, version) | Licence | Redistributable in a patch | Used for | Changes made |
|---|---|---|---|---|---|
| fonts/PT_Serif-Web-Regular.ttf | https://github.com/google/fonts/tree/main/ofl/ptserif (fetched 2026-11-19) | OFL 1.1 (fonts/PT_Serif_OFL.txt) | yes, as rendered glyphs | English VWF glyphs, ASCII codes 0x00-0x5E (tools/vwf.py, 19 px) | none |
| fonts/PT_Serif-Web-Bold.ttf | same | OFL 1.1 | yes | not used yet (titles?) | none |
