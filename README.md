# PrintMosaic

A desktop app (Python + Tkinter) for laying out and printing photos at album
sizes — several to a page, with borders and cut guides for easy trimming.

## Setup

Needs Python 3.8+ and Pillow (Tkinter ships with most Python installs).

```
pip install pillow
python printmosaic.py
```

On some Linux distros Tkinter is separate: `sudo apt install python3-tk`.

## Features

- **Sizes in cm or inches** — 5×5, 6×6, **9×9**, 9×13, 10×10, 10×15, 13×13,
  13×18, 15×20 cm and inch equivalents, or a Custom size. Landscape toggle.
- **Per-photo editing** — drag to pan and scroll to zoom in the preview;
  rotate; adjust brightness, contrast, saturation, or switch to black & white.
- **Smart page packing** — Letter, A4, Legal, Tabloid, A3, portrait or
  landscape, at 150 / 300 / 600 DPI, with adjustable borders and margins.
- **Cut guides** — thin lines, corner crop marks, or none; optional filename
  caption under each photo.
- **Copies & fill** — per-photo copies, "to all", or "fill page" to pack a
  whole sheet with one photo. Live readout of photos-per-page and sheet count.
- **Choose what prints** — each photo has a print on/off toggle (click the ✓
  column or press Space); skipped photos stay in the list but are left off the
  sheets. Include All / Exclude All in the Edit menu.
- **Thumbnail list** with multi-select, reorder (up/down), and remove
  (Ctrl/Shift-click for several, then Remove or Delete).
- **Dark mode** — toggle a light or dark interface under the View menu.
- **Projects** — save/open your layout, theme, and edits (`.pmproj`) to reprint
  later.
- **Output** — preview the composed pages, export a print-ready PDF, save PNG
  pages, or open a **print dialog** (set whole-set copies, then send to the
  default printer or open in your viewer to pick a printer).

## Menus & shortcuts

File (Add Photos/Folder, Open/Save Project, Export PDF, Save Images, Print),
Edit (rotate, reset, apply-to-all, fill page, reorder, remove), View (preview
page), Help (User Guide, Shortcuts, Print Tips, About).

```
Ctrl+O Add photos   Ctrl+S Save project   Ctrl+E Export PDF
Ctrl+P Print        Ctrl+R Preview page   Ctrl+[ / ] Rotate
Del Remove          F1 User guide
Preview: drag = move, scroll = zoom
```

## Notes

- Renders at