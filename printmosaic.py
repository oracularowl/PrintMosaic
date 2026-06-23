#!/usr/bin/env python3
"""
PrintMosaic
===========
A desktop app for laying out and printing photos at standard album sizes,
several to a page, with white borders and cut guides for easy trimming.

Highlights
----------
* Sizes in CM or INCHES (9x9, 5x7, 10x15 cm, ... or custom).
* Per-photo crop (drag to pan, scroll to zoom), rotate, and image
  adjustments (brightness / contrast / saturation / black & white).
* Choose which photos to print (per-photo print on/off), multi-select
  remove, reorder, and per-photo copies.
* Smart page packing onto Letter / A4 / Legal / Tabloid / A3, portrait
  or landscape, with adjustable borders, margins, cut lines or crop marks,
  and optional filename captions.
* Light or dark interface.
* Save / open projects, export print-ready PDF, save PNG pages, or print
  through a print dialog (copies + printer choice).

Requires: Python 3.8+, Pillow  (pip install pillow)
Author: built with Claude.  License: MIT.
"""

import os
import sys
import json
import tempfile
import platform
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import (Image, ImageTk, ImageDraw, ImageOps,
                     ImageEnhance, ImageFont)
except ImportError:
    print("This app needs Pillow.  Install it with:  pip install pillow")
    sys.exit(1)

# Optional HEIC / HEIF support (e.g. iPhone photos).
# Enabled automatically when the pillow-heif plugin is installed:
#     pip install pillow-heif
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except Exception:
    HEIC_OK = False


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
APP_NAME = "PrintMosaic"
APP_VERSION = "2.2"
CM_PER_IN = 2.54
PROJECT_EXT = ".pmproj"

PHOTO_SIZES_CM = {
    "5 x 5 cm": (5.0, 5.0),
    "6 x 6 cm": (6.0, 6.0),
    "9 x 9 cm": (9.0, 9.0),
    "9 x 13 cm": (9.0, 13.0),
    "10 x 10 cm": (10.0, 10.0),
    "10 x 15 cm": (10.0, 15.0),
    "13 x 13 cm": (13.0, 13.0),
    "13 x 18 cm": (13.0, 18.0),
    "15 x 20 cm": (15.0, 20.0),
    "Custom...": None,
}
PHOTO_SIZES_IN = {
    "2 x 3 in (wallet)": (2.0, 3.0),
    "3.5 x 5 in": (3.5, 5.0),
    "4 x 4 in": (4.0, 4.0),
    "4 x 6 in": (4.0, 6.0),
    "5 x 5 in": (5.0, 5.0),
    "5 x 7 in": (5.0, 7.0),
    "6 x 6 in": (6.0, 6.0),
    "8 x 8 in": (8.0, 8.0),
    "8 x 10 in": (8.0, 10.0),
    "9 x 9 in": (9.0, 9.0),
    "Custom...": None,
}
PAGE_SIZES = {
    "Letter (8.5 x 11 in)": (8.5, 11.0),
    "A4 (21 x 29.7 cm)": (8.27, 11.69),
    "Legal (8.5 x 14 in)": (8.5, 14.0),
    "Tabloid (11 x 17 in)": (11.0, 17.0),
    "A3 (29.7 x 42 cm)": (11.69, 16.54),
}
DPI_OPTIONS = [150, 300, 600]

CUT_LINE_COLOR = (160, 160, 160)
MARK_COLOR = (90, 90, 90)
CAPTION_COLOR = (60, 60, 60)
PAGE_BG = (255, 255, 255)
IMAGE_FILETYPES = [
    ("Images", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp *.heic *.gif"),
    ("All files", "*.*"),
]

# Interface palettes
THEMES = {
    "light": {
        "bg": "#f4f4f4", "fg": "#1a1a1a", "field": "#ffffff",
        "head": "#e6e6e6", "sel": "#3b6ea5", "selfg": "#ffffff",
        "canvas": "#3a3a3a", "accent": "#1a7a3a", "off": "#a0a0a0",
    },
    "dark": {
        "bg": "#2b2b2b", "fg": "#e8e8e8", "field": "#3c3c3c",
        "head": "#3a3a3a", "sel": "#4a78b0", "selfg": "#ffffff",
        "canvas": "#1e1e1e", "accent": "#5fbf7f", "off": "#777777",
    },
}


# --------------------------------------------------------------------------
# Image / layout helpers (geometry in INCHES, rendered at the given dpi)
# --------------------------------------------------------------------------
def in_to_px(inches, dpi):
    return int(round(inches * dpi))


def apply_adjustments(img, brightness=1.0, contrast=1.0,
                      saturation=1.0, grayscale=False):
    img = img.convert("RGB")
    if grayscale:
        img = ImageOps.grayscale(img).convert("RGB")
    if abs(brightness - 1.0) > 1e-3:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if abs(contrast - 1.0) > 1e-3:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if not grayscale and abs(saturation - 1.0) > 1e-3:
        img = ImageEnhance.Color(img).enhance(saturation)
    return img


def render_cropped(img, out_w, out_h, zoom=1.0, ox=0.0, oy=0.0, rotation=0):
    """Return an (out_w, out_h) crop of *img* using a 'cover' fit."""
    if rotation:
        img = img.rotate(-rotation, expand=True)
    img = img.convert("RGB")
    src_w, src_h = img.size
    target_ar = out_w / out_h
    src_ar = src_w / src_h
    if src_ar > target_ar:
        base_h, base_w = src_h, src_h * target_ar
    else:
        base_w, base_h = src_w, src_w / target_ar
    zoom = max(1.0, float(zoom))
    crop_w, crop_h = base_w / zoom, base_h / zoom
    max_dx, max_dy = (src_w - crop_w) / 2.0, (src_h - crop_h) / 2.0
    cx = src_w / 2.0 + ox * max_dx
    cy = src_h / 2.0 + oy * max_dy
    left = max(0, min(cx - crop_w / 2.0, src_w - crop_w))
    top = max(0, min(cy - crop_h / 2.0, src_h - crop_h))
    box = (int(round(left)), int(round(top)),
           int(round(left + crop_w)), int(round(top + crop_h)))
    return img.crop(box).resize((out_w, out_h), Image.LANCZOS)


def compute_grid(page_in, cell_in, margin_in, gap_in, dpi, caption_in=0.0):
    page_w, page_h = in_to_px(page_in[0], dpi), in_to_px(page_in[1], dpi)
    cell_w = in_to_px(cell_in[0], dpi)
    photo_h = in_to_px(cell_in[1], dpi)
    cap = in_to_px(caption_in, dpi)
    cell_h = photo_h + cap
    margin = in_to_px(margin_in, dpi)
    gap = in_to_px(gap_in, dpi)
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    cols = max(0, int((usable_w + gap) // (cell_w + gap))) if cell_w > 0 else 0
    rows = max(0, int((usable_h + gap) // (cell_h + gap))) if cell_h > 0 else 0
    return {
        "page_w": page_w, "page_h": page_h,
        "cell_w": cell_w, "photo_h": photo_h, "cap": cap, "cell_h": cell_h,
        "margin": margin, "gap": gap,
        "cols": cols, "rows": rows, "per_page": cols * rows,
    }


def _caption_font(px):
    px = max(8, int(px))
    for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    try:
        return ImageFont.load_default(px)
    except Exception:
        return ImageFont.load_default()


def _draw_corner_marks(draw, x, y, w, h, length, color):
    L = length
    segs = [
        ((x - L, y), (x, y)), ((x, y - L), (x, y)),
        ((x + w, y), (x + w + L, y)), ((x + w, y - L), (x + w, y)),
        ((x - L, y + h), (x, y + h)), ((x, y + h), (x, y + h + L)),
        ((x + w, y + h), (x + w + L, y + h)), ((x + w, y + h), (x + w, y + h + L)),
    ]
    for a, b in segs:
        draw.line([a, b], fill=color, width=1)


def build_pages(cropped, page_in, cell_in, margin_in, gap_in, dpi,
                guide_style="border", captions=None, caption_in=0.0,
                progress=None):
    """Compose cropped photos onto pages. `cropped` is a list of PIL images
    (already at print size). Returns a list of PIL page images."""
    g = compute_grid(page_in, cell_in, margin_in, gap_in, dpi, caption_in)
    if g["per_page"] == 0:
        raise ValueError(
            "These photos are too big for this page with the current margins.\n"
            "Try a smaller photo size, smaller margins/borders, or a larger "
            "page (Tabloid / A3 for big square prints)."
        )
    cols = g["cols"]
    cw, photo_h, cap = g["cell_w"], g["photo_h"], g["cap"]
    cell_h, gap, margin = g["cell_h"], g["gap"], g["margin"]
    grid_w = cols * cw + (cols - 1) * gap
    grid_h = g["rows"] * cell_h + (g["rows"] - 1) * gap
    start_x = (g["page_w"] - grid_w) // 2
    start_y = (g["page_h"] - grid_h) // 2
    per_page = g["per_page"]
    mark_len = max(6, int(0.06 * dpi))
    font = _caption_font(cap * 0.5) if cap else None

    pages = []
    n = len(cropped)
    total_pages = max(1, (n + per_page - 1) // per_page)
    for pi, i in enumerate(range(0, n, per_page)):
        chunk = cropped[i:i + per_page]
        page = Image.new("RGB", (g["page_w"], g["page_h"]), PAGE_BG)
        draw = ImageDraw.Draw(page)
        for idx, photo in enumerate(chunk):
            r, c = divmod(idx, cols)
            x = start_x + c * (cw + gap)
            y = start_y + r * (cell_h + gap)
            if photo.size != (cw, photo_h):
                photo = photo.resize((cw, photo_h), Image.LANCZOS)
            page.paste(photo, (x, y))
            if guide_style == "border":
                draw.rectangle([x, y, x + cw - 1, y + photo_h - 1],
                               outline=CUT_LINE_COLOR, width=1)
            elif guide_style == "corners":
                _draw_corner_marks(draw, x, y, cw, photo_h, mark_len, MARK_COLOR)
            if cap and captions:
                text = captions[i + idx] if i + idx < len(captions) else ""
                if text:
                    tb = draw.textbbox((0, 0), text, font=font)
                    tw, th = tb[2] - tb[0], tb[3] - tb[1]
                    tx = x + (cw - tw) // 2
                    ty = y + photo_h + (cap - th) // 2 - tb[1]
                    draw.text((tx, ty), text, fill=CAPTION_COLOR, font=font)
        pages.append(page)
        if progress:
            progress(pi + 1, total_pages)
    return pages


def send_to_printer(path):
    system = platform.system()
    if system == "Windows":
        os.startfile(path, "print")  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["lpr", path], check=True)
    else:
        subprocess.run(["lp", path], check=True)


def open_in_viewer(path):
    """Open a file in the OS default app (so the user can use its Print dialog)."""
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["open", path], check=True)
    else:
        subprocess.run(["xdg-open", path], check=True)


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
class PhotoItem:
    PREVIEW_MAX = 1400

    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        img = Image.open(path)
        self.image = ImageOps.exif_transpose(img).convert("RGB")
        prev = self.image.copy()
        prev.thumbnail((self.PREVIEW_MAX, self.PREVIEW_MAX), Image.LANCZOS)
        self.preview_image = prev
        # editable state
        self.zoom = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self.rotation = 0
        self.copies = 1
        self.include = True
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.grayscale = False

    def _adjusted(self, export):
        src = self.image if export else self.preview_image
        return apply_adjustments(src, self.brightness, self.contrast,
                                 self.saturation, self.grayscale)

    def render(self, out_w, out_h, export=False):
        return render_cropped(self._adjusted(export), out_w, out_h,
                              self.zoom, self.ox, self.oy, self.rotation)

    def thumbnail(self, size=44):
        t = self._adjusted(False)
        return render_cropped(t, size, size, self.zoom, self.ox, self.oy,
                              self.rotation)

    def to_dict(self):
        return {
            "path": self.path, "zoom": self.zoom, "ox": self.ox, "oy": self.oy,
            "rotation": self.rotation, "copies": self.copies,
            "include": self.include,
            "brightness": self.brightness, "contrast": self.contrast,
            "saturation": self.saturation, "grayscale": self.grayscale,
        }

    @classmethod
    def from_dict(cls, d):
        it = cls(d["path"])
        it.zoom = d.get("zoom", 1.0)
        it.ox = d.get("ox", 0.0)
        it.oy = d.get("oy", 0.0)
        it.rotation = d.get("rotation", 0)
        it.copies = d.get("copies", 1)
        it.include = d.get("include", True)
        it.brightness = d.get("brightness", 1.0)
        it.contrast = d.get("contrast", 1.0)
        it.saturation = d.get("saturation", 1.0)
        it.grayscale = d.get("grayscale", False)
        return it


# --------------------------------------------------------------------------
# A simple vertically scrollable frame for the controls panel
# --------------------------------------------------------------------------
class ScrollFrame(ttk.Frame):
    def __init__(self, parent, width=300):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, width=width, highlightthickness=0,
                                borderwidth=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_wheel, add="+")

    def _on_wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        p, inside = w, False
        while p is not None:
            if p is self:
                inside = True
                break
            p = getattr(p, "master", None)
        if not inside:
            return
        if getattr(e, "num", None) == 4 or getattr(e, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(e, "num", None) == 5 or getattr(e, "delta", 0) < 0:
            self.canvas.yview_scroll(1, "units")


# --------------------------------------------------------------------------
# Main application
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x760")
        self.minsize(1000, 640)
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass

        self.items = []
        self.current = None
        self.project_path = None
        self._preview_imgtk = None
        self._thumbs = {}
        self._disp = (1, 1, 0, 0)
        self._drag = None
        self._suspend = False

        self.dark_var = tk.BooleanVar(value=False)
        self._build_menu()
        self._build_ui()
        self._bind_shortcuts()
        self.apply_theme(False)
        self.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.on_size_change()

    # ---- menu ------------------------------------------------------------
    def _build_menu(self):
        m = tk.Menu(self)
        filem = tk.Menu(m, tearoff=0)
        filem.add_command(label="Add Photos…", accelerator="Ctrl+O",
                          command=self.add_photos)
        filem.add_command(label="Add Folder…", command=self.add_folder)
        filem.add_separator()
        filem.add_command(label="Open Project…", command=self.open_project)
        filem.add_command(label="Save Project", accelerator="Ctrl+S",
                          command=self.save_project)
        filem.add_command(label="Save Project As…", command=self.save_project_as)
        filem.add_separator()
        filem.add_command(label="Export PDF…", accelerator="Ctrl+E",
                          command=self.save_pdf)
        filem.add_command(label="Save Page Images…", command=self.save_images)
        filem.add_command(label="Print…", accelerator="Ctrl+P",
                          command=self.print_pages)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.on_exit)
        m.add_cascade(label="File", menu=filem)

        editm = tk.Menu(m, tearoff=0)
        editm.add_command(label="Rotate Left", accelerator="Ctrl+[",
                          command=lambda: self.rotate(-90))
        editm.add_command(label="Rotate Right", accelerator="Ctrl+]",
                          command=lambda: self.rotate(90))
        editm.add_command(label="Reset Crop & Adjustments",
                          command=self.reset_current)
        editm.add_separator()
        editm.add_command(label="Apply Crop to All Photos",
                          command=self.apply_crop_to_all)
        editm.add_command(label="Fill Page with Selected Photo",
                          command=self.fill_page)
        editm.add_separator()
        editm.add_command(label="Toggle Print On/Off", accelerator="Space",
                          command=self.toggle_selected_include)
        editm.add_command(label="Include All in Print",
                          command=lambda: self.set_all_include(True))
        editm.add_command(label="Exclude All from Print",
                          command=lambda: self.set_all_include(False))
        editm.add_separator()
        editm.add_command(label="Move Up", command=lambda: self.move(-1))
        editm.add_command(label="Move Down", command=lambda: self.move(1))
        editm.add_command(label="Remove Selected", accelerator="Del",
                          command=self.remove_selected)
        editm.add_command(label="Clear All", command=self.clear_all)
        m.add_cascade(label="Edit", menu=editm)

        viewm = tk.Menu(m, tearoff=0)
        viewm.add_command(label="Preview Composed Page…", accelerator="Ctrl+R",
                          command=self.preview_page)
        viewm.add_separator()
        viewm.add_checkbutton(label="Dark mode", variable=self.dark_var,
                              command=lambda: self.apply_theme(self.dark_var.get()))
        m.add_cascade(label="View", menu=viewm)

        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="User Guide", accelerator="F1",
                          command=self.show_guide)
        helpm.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        helpm.add_command(label="Print Tips", command=self.show_tips)
        helpm.add_separator()
        helpm.add_command(label="About", command=self.show_about)
        m.add_cascade(label="Help", menu=helpm)
        self.config(menu=m)

    def _bind_shortcuts(self):
        self.bind("<Control-o>", lambda e: self.add_photos())
        self.bind("<Control-s>", lambda e: self.save_project())
        self.bind("<Control-e>", lambda e: self.save_pdf())
        self.bind("<Control-p>", lambda e: self.print_pages())
        self.bind("<Control-r>", lambda e: self.preview_page())
        self.bind("<Control-bracketleft>", lambda e: self.rotate(-90))
        self.bind("<Control-bracketright>", lambda e: self.rotate(90))
        self.bind("<Delete>", lambda e: self.remove_selected())
        self.bind("<F1>", lambda e: self.show_guide())

    # ---- UI --------------------------------------------------------------
    def _build_ui(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side="top", fill="x")
        ttk.Button(bar, text="Add Photos", command=self.add_photos).pack(side="left")
        ttk.Button(bar, text="Add Folder", command=self.add_folder).pack(side="left", padx=4)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Preview Page", command=self.preview_page).pack(side="left")
        ttk.Button(bar, text="Export PDF", command=self.save_pdf).pack(side="left", padx=4)
        ttk.Button(bar, text="Save Images", command=self.save_images).pack(side="left")
        ttk.Button(bar, text="Print", command=self.print_pages).pack(side="left", padx=4)

        main = ttk.Frame(self)
        main.pack(side="top", fill="both", expand=True)

        # Left: thumbnail list + reorder
        left = ttk.Frame(main, padding=6)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Photos  (click the ✓ column to print or skip)"
                  ).pack(anchor="w")
        tvwrap = ttk.Frame(left)
        tvwrap.pack(side="top", fill="y", expand=True)
        tv = ttk.Treeview(tvwrap, columns=("inc", "copies"),
                          show="tree headings", height=6, selectmode="extended")
        tv.heading("#0", text="Photo")
        tv.heading("inc", text="✓")
        tv.heading("copies", text="×")
        tv.column("#0", width=196, stretch=False)
        tv.column("inc", width=30, anchor="center", stretch=False)
        tv.column("copies", width=30, anchor="center", stretch=False)
        tv.pack(side="left", fill="y")
        sb = ttk.Scrollbar(tvwrap, orient="vertical", command=tv.yview)
        sb.pack(side="left", fill="y")
        tv.configure(yscrollcommand=sb.set)
        tv.bind("<<TreeviewSelect>>", self.on_select)
        tv.bind("<Button-1>", self._on_tree_click, add="+")
        tv.bind("<space>", lambda e: (self.toggle_selected_include(), "break")[1])
        self.tree = tv

        rowbtn = ttk.Frame(left)
        rowbtn.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(rowbtn, text="↑", width=3, command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(rowbtn, text="↓", width=3, command=lambda: self.move(1)).pack(side="left", padx=2)
        ttk.Button(rowbtn, text="Print on/off",
                   command=self.toggle_selected_include).pack(side="left", padx=2)
        rowbtn2 = ttk.Frame(left)
        rowbtn2.pack(side="bottom", fill="x", pady=(4, 0))
        ttk.Button(rowbtn2, text="Remove", command=self.remove_selected).pack(side="left")
        ttk.Button(rowbtn2, text="Clear All", command=self.clear_all).pack(side="left", padx=2)

        # Center: crop preview
        center = ttk.Frame(main, padding=6)
        center.pack(side="left", fill="both", expand=True)
        ttk.Label(center, text="Crop preview  —  drag to move, scroll to zoom"
                  ).pack(anchor="w")
        self.preview = tk.Canvas(center, bg="#3a3a3a", highlightthickness=0)
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda e: self.refresh_preview())
        self.preview.bind("<ButtonPress-1>", self._on_pan_start)
        self.preview.bind("<B1-Motion>", self._on_pan_move)
        self.preview.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.preview.bind("<MouseWheel>", self._on_zoom_wheel)
        self.preview.bind("<Button-4>", self._on_zoom_wheel)
        self.preview.bind("<Button-5>", self._on_zoom_wheel)

        # Right: scrollable controls
        self.scroll = ScrollFrame(main, width=300)
        self.scroll.pack(side="right", fill="y")
        self._build_controls(self.scroll.inner)

        # Status bar
        self.status = tk.StringVar(value="Add some photos to begin.")
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  anchor="w", padding=4).pack(side="bottom", fill="x")

    def _build_controls(self, parent):
        pad = dict(padx=8, pady=4)

        box = ttk.LabelFrame(parent, text="Print size", padding=8)
        box.pack(fill="x", **pad)
        urow = ttk.Frame(box)
        urow.pack(fill="x", pady=(0, 4))
        ttk.Label(urow, text="Units:").pack(side="left")
        self.unit_var = tk.StringVar(value="cm")
        ttk.Combobox(urow, textvariable=self.unit_var, values=["cm", "inch"],
                     state="readonly", width=6).pack(side="left", padx=4)
        self.unit_var.trace_add("write", lambda *a: self.on_unit_change())

        self.size_var = tk.StringVar(value="9 x 9 cm")
        self.size_combo = ttk.Combobox(box, textvariable=self.size_var,
                                       values=list(PHOTO_SIZES_CM.keys()),
                                       state="readonly")
        self.size_combo.pack(fill="x")
        self.size_combo.bind("<<ComboboxSelected>>", self.on_size_change)
        custom = ttk.Frame(box)
        custom.pack(fill="x", pady=(6, 0))
        ttk.Label(custom, text="W").pack(side="left")
        self.cw_var = tk.DoubleVar(value=9.0)
        ttk.Entry(custom, textvariable=self.cw_var, width=6).pack(side="left", padx=2)
        ttk.Label(custom, text="H").pack(side="left")
        self.chh_var = tk.DoubleVar(value=9.0)
        ttk.Entry(custom, textvariable=self.chh_var, width=6).pack(side="left", padx=2)
        self.unit_suffix = tk.StringVar(value="cm")
        ttk.Label(custom, textvariable=self.unit_suffix).pack(side="left")
        self.custom_frame = custom
        self.cw_var.trace_add("write", lambda *a: self._on_custom_edit())
        self.chh_var.trace_add("write", lambda *a: self._on_custom_edit())
        self.landscape_photo = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="Landscape photo (swap W/H)",
                        variable=self.landscape_photo,
                        command=self.on_size_change).pack(anchor="w", pady=(6, 0))

        cbox = ttk.LabelFrame(parent, text="Adjust selected photo", padding=8)
        cbox.pack(fill="x", **pad)
        self.zoom_var = self._slider(cbox, "Zoom", 1.0, 4.0, 1.0)
        self.ox_var = self._slider(cbox, "Horizontal", -1.0, 1.0, 0.0)
        self.oy_var = self._slider(cbox, "Vertical", -1.0, 1.0, 0.0)
        self.bright_var = self._slider(cbox, "Brightness", 0.3, 2.0, 1.0)
        self.contrast_var = self._slider(cbox, "Contrast", 0.3, 2.0, 1.0)
        self.sat_var = self._slider(cbox, "Saturation", 0.0, 2.0, 1.0)
        self.gray_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cbox, text="Black & white", variable=self.gray_var,
                        command=self.on_adjust_change).pack(anchor="w")
        rotrow = ttk.Frame(cbox)
        rotrow.pack(fill="x", pady=(6, 0))
        ttk.Button(rotrow, text="⟲ Left", command=lambda: self.rotate(-90)
                   ).pack(side="left", expand=True, fill="x")
        ttk.Button(rotrow, text="Right ⟳", command=lambda: self.rotate(90)
                   ).pack(side="left", expand=True, fill="x", padx=(4, 0))
        ttk.Button(cbox, text="Reset", command=self.reset_current).pack(fill="x", pady=(6, 0))
        crow = ttk.Frame(cbox)
        crow.pack(fill="x", pady=(6, 0))
        ttk.Label(crow, text="Copies").pack(side="left")
        self.copies_var = tk.IntVar(value=1)
        ttk.Spinbox(crow, from_=1, to=999, width=5, textvariable=self.copies_var,
                    command=self.on_copies_change).pack(side="left", padx=4)
        ttk.Button(crow, text="To all", command=self.copies_to_all).pack(side="left")
        ttk.Button(crow, text="Fill page", command=self.fill_page).pack(side="left", padx=2)

        pbox = ttk.LabelFrame(parent, text="Page & output", padding=8)
        pbox.pack(fill="x", **pad)
        ttk.Label(pbox, text="Paper").pack(anchor="w")
        self.page_var = tk.StringVar(value="Letter (8.5 x 11 in)")
        pc = ttk.Combobox(pbox, textvariable=self.page_var,
                          values=list(PAGE_SIZES.keys()), state="readonly")
        pc.pack(fill="x")
        pc.bind("<<ComboboxSelected>>", lambda e: self._update_fit_label())
        self.landscape_page = tk.BooleanVar(value=False)
        ttk.Checkbutton(pbox, text="Landscape paper", variable=self.landscape_page,
                        command=self._update_fit_label).pack(anchor="w")

        drow = ttk.Frame(pbox)
        drow.pack(fill="x", pady=(4, 0))
        ttk.Label(drow, text="Quality (DPI)").pack(side="left")
        self.dpi_var = tk.IntVar(value=300)
        dpc = ttk.Combobox(drow, textvariable=self.dpi_var, values=DPI_OPTIONS,
                           state="readonly", width=6)
        dpc.pack(side="left", padx=4)
        dpc.bind("<<ComboboxSelected>>", lambda e: self._refresh_status())

        self.gap_var = self._slider(pbox, "Border / gap (cm)", 0.0, 2.0, 0.3)
        self.margin_var = self._slider(pbox, "Page margin (cm)", 0.0, 2.5, 0.6)

        ttk.Label(pbox, text="Cut guides").pack(anchor="w", pady=(4, 0))
        self.guide_var = tk.StringVar(value="border")
        grow = ttk.Frame(pbox)
        grow.pack(fill="x")
        for txt, val in (("Lines", "border"), ("Corner marks", "corners"),
                         ("None", "none")):
            ttk.Radiobutton(grow, text=txt, value=val, variable=self.guide_var,
                            command=self._update_fit_label).pack(side="left")
        self.caption_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(pbox, text="Print filename under each photo",
                        variable=self.caption_var,
                        command=self._update_fit_label).pack(anchor="w", pady=(4, 0))

        self.fit_label = tk.StringVar(value="")
        self.fit_lbl = ttk.Label(pbox, textvariable=self.fit_label)
        self.fit_lbl.pack(anchor="w", pady=(4, 0))

    def _slider(self, parent, label, lo, hi, init):
        ttk.Label(parent, text=label).pack(anchor="w")
        var = tk.DoubleVar(value=init)
        ttk.Scale(parent, from_=lo, to=hi, variable=var,
                  command=lambda e: self.on_adjust_change()).pack(fill="x")
        return var

    # ---- theme -----------------------------------------------------------
    def apply_theme(self, dark):
        pal = THEMES["dark" if dark else "light"]
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg=pal["bg"])
        st.configure(".", background=pal["bg"], foreground=pal["fg"],
                     fieldbackground=pal["field"], bordercolor=pal["head"])
        for w in ("TFrame", "TLabelframe", "TLabel", "TCheckbutton",
                  "TRadiobutton"):
            st.configure(w, background=pal["bg"], foreground=pal["fg"])
        st.configure("TLabelframe.Label", background=pal["bg"], foreground=pal["fg"])
        st.configure("TButton", background=pal["head"], foreground=pal["fg"])
        st.map("TButton", background=[("active", pal["sel"])],
               foreground=[("active", pal["selfg"])])
        for w in ("TEntry", "TCombobox", "TSpinbox"):
            st.configure(w, fieldbackground=pal["field"], foreground=pal["fg"],
                         background=pal["head"], arrowcolor=pal["fg"])
        st.map("TCombobox", fieldbackground=[("readonly", pal["field"])],
               foreground=[("readonly", pal["fg"])])
        st.configure("Treeview", background=pal["field"], fieldbackground=pal["field"],
                     foreground=pal["fg"], rowheight=48)
        st.map("Treeview", background=[("selected", pal["sel"])],
               foreground=[("selected", pal["selfg"])])
        st.configure("Treeview.Heading", background=pal["head"], foreground=pal["fg"])
        st.configure("TScale", background=pal["bg"])
        st.configure("TScrollbar", background=pal["head"], troughcolor=pal["bg"])
        st.configure("TSeparator", background=pal["head"])
        st.configure("Horizontal.TProgressbar", background=pal["sel"])
        self.preview.configure(bg=pal["canvas"])
        self.scroll.canvas.configure(bg=pal["bg"])
        try:
            self.fit_lbl.configure(foreground=pal["accent"])
        except Exception:
            pass
        self.tree.tag_configure("off", foreground=pal["off"])
        self.refresh_preview()

    # ---- unit / size helpers --------------------------------------------
    def _size_table(self):
        return PHOTO_SIZES_CM if self.unit_var.get() == "cm" else PHOTO_SIZES_IN

    def cell_size_unit(self):
        sizes = self._size_table()
        name = self.size_var.get()
        if sizes.get(name) is None:
            try:
                w, h = float(self.cw_var.get()), float(self.chh_var.get())
            except (tk.TclError, ValueError):
                w, h = 0.0, 0.0
        else:
            w, h = sizes[name]
        if self.landscape_photo.get():
            w, h = h, w
        return w, h, self.unit_var.get()

    def cell_size(self):
        w, h, unit = self.cell_size_unit()
        return (w / CM_PER_IN, h / CM_PER_IN) if unit == "cm" else (w, h)

    def margin_in(self):
        return float(self.margin_var.get()) / CM_PER_IN

    def gap_in(self):
        return float(self.gap_var.get()) / CM_PER_IN

    def caption_in(self):
        return (0.55 / CM_PER_IN) if self.caption_var.get() else 0.0

    def dpi(self):
        return int(self.dpi_var.get())

    def page_size(self):
        w, h = PAGE_SIZES[self.page_var.get()]
        if self.landscape_page.get():
            w, h = h, w
        return (w, h)

    def on_unit_change(self):
        unit = self.unit_var.get()
        self.unit_suffix.set(unit)
        self.size_combo["values"] = list(self._size_table().keys())
        self.size_var.set("9 x 9 cm" if unit == "cm" else "5 x 7 in")
        self.on_size_change()

    def _on_custom_edit(self):
        if self._size_table().get(self.size_var.get()) is None:
            self._update_fit_label()
            self.refresh_preview()

    def _included(self):
        return [it for it in self.items if it.include]

    def _update_fit_label(self):
        try:
            g = compute_grid(self.page_size(), self.cell_size(),
                             self.margin_in(), self.gap_in(), self.dpi(),
                             self.caption_in())
            if g["per_page"] == 0:
                self.fit_label.set("⚠ Doesn't fit on this page")
            else:
                total = sum(max(1, it.copies) for it in self._included())
                sheets = (total + g["per_page"] - 1) // g["per_page"] if total else 0
                self.fit_label.set(
                    f"{g['cols']} × {g['rows']} = {g['per_page']}/page"
                    + (f"  •  {sheets} sheet(s)" if sheets else ""))
        except Exception:
            self.fit_label.set("")

    # ---- photo management ------------------------------------------------
    def _add_paths(self, paths):
        added = 0
        heic_problem = False
        for p in paths:
            try:
                self.items.append(PhotoItem(p))
                added += 1
            except Exception as e:
                if p.lower().endswith((".heic", ".heif")) and not HEIC_OK:
                    heic_problem = True
                else:
                    messagebox.showwarning("Skipped", f"Couldn't load:\n{p}\n\n{e}")
        if heic_problem:
            messagebox.showwarning(
                "HEIC support not installed",
                "Some HEIC/HEIF photos couldn't be opened.\n\n"
                "Install the free plugin, then restart " + APP_NAME + ":\n\n"
                "    pip install pillow-heif")
        if added:
            self.rebuild_tree()
            self.select_index(len(self.items) - 1)
        self._refresh_status()
        return added

    def add_photos(self):
        paths = filedialog.askopenfilenames(title="Choose photos",
                                            filetypes=IMAGE_FILETYPES)
        if paths:
            self._add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder of photos")
        if not folder:
            return
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp",
                ".heic", ".gif")
        paths = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
                 if f.lower().endswith(exts)]
        if not paths:
            messagebox.showinfo("Empty", "No images found in that folder.")
            return
        self._add_paths(paths)

    def rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._thumbs.clear()
        for i, it in enumerate(self.items):
            check = "✓" if it.include else ""
            tags = () if it.include else ("off",)
            try:
                thumb = ImageTk.PhotoImage(it.thumbnail(44))
                self._thumbs[str(i)] = thumb
                self.tree.insert("", "end", iid=str(i), text="  " + it.name,
                                 image=thumb, values=(check, it.copies), tags=tags)
            except Exception:
                self.tree.insert("", "end", iid=str(i), text="  " + it.name,
                                 values=(check, it.copies), tags=tags)

    def select_index(self, i):
        if 0 <= i < len(self.items):
            self.tree.selection_set(str(i))
            self.tree.see(str(i))

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _selected_indices(self):
        return sorted(int(s) for s in self.tree.selection())

    def on_select(self, event=None):
        i = self._selected_index()
        if i is None:
            return
        self.current = self.items[i]
        self._load_controls_from(self.current)
        self.refresh_preview()

    def _load_controls_from(self, it):
        self._suspend = True
        self.zoom_var.set(it.zoom)
        self.ox_var.set(it.ox)
        self.oy_var.set(it.oy)
        self.bright_var.set(it.brightness)
        self.contrast_var.set(it.contrast)
        self.sat_var.set(it.saturation)
        self.gray_var.set(it.grayscale)
        self.copies_var.set(it.copies)
        self._suspend = False

    def _on_tree_click(self, event):
        # Toggle print-include when the ✓ column is clicked.
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        i = int(row)
        self.items[i].include = not self.items[i].include
        self._refresh_row(i)
        self._refresh_status()
        return "break"

    def _refresh_row(self, i):
        it = self.items[i]
        self.tree.set(str(i), "inc", "✓" if it.include else "")
        self.tree.item(str(i), tags=() if it.include else ("off",))

    def toggle_selected_include(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        # If any selected is on, turn all off; else turn all on.
        target = not any(self.items[i].include for i in idxs)
        for i in idxs:
            self.items[i].include = target
            self._refresh_row(i)
        self._refresh_status()

    def set_all_include(self, value):
        for i, it in enumerate(self.items):
            it.include = value
            self._refresh_row(i)
        self._refresh_status()

    def remove_selected(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        for i in reversed(idxs):
            del self.items[i]
        self.current = None
        self.rebuild_tree()
        self.preview.delete("all")
        if self.items:
            self.select_index(min(idxs[0], len(self.items) - 1))
        self._refresh_status()

    def clear_all(self):
        if self.items and not messagebox.askyesno(
                "Clear all", "Remove all photos from the layout?"):
            return
        self.items.clear()
        self.current = None
        self.rebuild_tree()
        self.preview.delete("all")
        self._refresh_status()

    def move(self, delta):
        i = self._selected_index()
        if i is None:
            return
        j = i + delta
        if not (0 <= j < len(self.items)):
            return
        self.items[i], self.items[j] = self.items[j], self.items[i]
        self.rebuild_tree()
        self.select_index(j)

    # ---- adjust callbacks ------------------------------------------------
    def on_adjust_change(self):
        if self._suspend or not self.current:
            return
        c = self.current
        c.zoom = float(self.zoom_var.get())
        c.ox = float(self.ox_var.get())
        c.oy = float(self.oy_var.get())
        c.brightness = float(self.bright_var.get())
        c.contrast = float(self.contrast_var.get())
        c.saturation = float(self.sat_var.get())
        c.grayscale = bool(self.gray_var.get())
        self.refresh_preview()
        self._update_thumb()

    def rotate(self, deg):
        if not self.current:
            return
        self.current.rotation = (self.current.rotation + deg) % 360
        self.refresh_preview()
        self._update_thumb()

    def reset_current(self):
        if not self.current:
            return
        c = self.current
        c.zoom, c.ox, c.oy, c.rotation = 1.0, 0.0, 0.0, 0
        c.brightness = c.contrast = c.saturation = 1.0
        c.grayscale = False
        self._load_controls_from(c)
        self.refresh_preview()
        self._update_thumb()

    def apply_crop_to_all(self):
        if not self.current:
            return
        c = self.current
        for it in self.items:
            it.zoom, it.ox, it.oy, it.rotation = c.zoom, c.ox, c.oy, c.rotation
            it.brightness, it.contrast = c.brightness, c.contrast
            it.saturation, it.grayscale = c.saturation, c.grayscale
        self.rebuild_tree()
        self.select_index(self.items.index(c))
        self.status.set("Applied current crop & adjustments to all photos.")

    def on_copies_change(self):
        if self.current:
            self.current.copies = max(1, int(self.copies_var.get()))
            self._update_tree_copies()
        self._refresh_status()

    def copies_to_all(self):
        n = max(1, int(self.copies_var.get()))
        for it in self.items:
            it.copies = n
        self.rebuild_tree()
        if self.current:
            self.select_index(self.items.index(self.current))
        self._refresh_status()

    def fill_page(self):
        if not self.current:
            messagebox.showinfo("Fill page", "Select a photo first.")
            return
        g = compute_grid(self.page_size(), self.cell_size(), self.margin_in(),
                         self.gap_in(), self.dpi(), self.caption_in())
        if g["per_page"] == 0:
            messagebox.showerror("Fill page", "This size doesn't fit the page.")
            return
        self.current.copies = g["per_page"]
        self.copies_var.set(g["per_page"])
        self._update_tree_copies()
        self._refresh_status()

    def _update_tree_copies(self):
        if self.current is None:
            return
        i = self.items.index(self.current)
        self.tree.set(str(i), "copies", self.current.copies)

    def _update_thumb(self):
        if self.current is None:
            return
        i = self.items.index(self.current)
        try:
            thumb = ImageTk.PhotoImage(self.current.thumbnail(44))
            self._thumbs[str(i)] = thumb
            self.tree.item(str(i), image=thumb)
        except Exception:
            pass

    def on_size_change(self, event=None):
        is_custom = self._size_table().get(self.size_var.get()) is None
        for child in self.custom_frame.winfo_children():
            try:
                child.configure(state="normal" if is_custom else "disabled")
            except tk.TclError:
                pass
        self._update_fit_label()
        self.refresh_preview()

    # ---- mouse pan / zoom ------------------------------------------------
    def _on_pan_start(self, e):
        if self.current:
            self._drag = (e.x, e.y, self.current.ox, self.current.oy)

    def _on_pan_move(self, e):
        if not self._drag or not self.current:
            return
        sx, sy, ox0, oy0 = self._drag
        disp_w, disp_h = self._disp[0], self._disp[1]
        nox = max(-1.0, min(1.0, ox0 - (e.x - sx) / max(1, disp_w) * 2))
        noy = max(-1.0, min(1.0, oy0 - (e.y - sy) / max(1, disp_h) * 2))
        self.current.ox, self.current.oy = nox, noy
        self._suspend = True
        self.ox_var.set(nox)
        self.oy_var.set(noy)
        self._suspend = False
        self.refresh_preview()

    def _on_zoom_wheel(self, e):
        if not self.current:
            return
        up = getattr(e, "num", None) == 4 or getattr(e, "delta", 0) > 0
        factor = 1.1 if up else 1 / 1.1
        self.current.zoom = max(1.0, min(4.0, self.current.zoom * factor))
        self._suspend = True
        self.zoom_var.set(self.current.zoom)
        self._suspend = False
        self.refresh_preview()
        self._update_thumb()

    # ---- preview ---------------------------------------------------------
    def refresh_preview(self):
        self._update_fit_label()
        if not self.current:
            return
        cw_in, ch_in = self.cell_size()
        if cw_in <= 0 or ch_in <= 0:
            return
        ar = cw_in / ch_in
        cw = max(self.preview.winfo_width(), 50)
        ch = max(self.preview.winfo_height(), 50)
        pad = 24
        aw, ah = cw - 2 * pad, ch - 2 * pad
        if aw / ah > ar:
            disp_h = ah
            disp_w = int(disp_h * ar)
        else:
            disp_w = aw
            disp_h = int(disp_w / ar)
        disp_w, disp_h = max(disp_w, 10), max(disp_h, 10)
        x = (cw - disp_w) // 2
        y = (ch - disp_h) // 2
        self._disp = (disp_w, disp_h, x, y)

        crop = self.current.render(disp_w, disp_h)
        self._preview_imgtk = ImageTk.PhotoImage(crop)
        self.preview.delete("all")
        self.preview.create_image(x, y, anchor="nw", image=self._preview_imgtk)
        self.preview.create_rectangle(x, y, x + disp_w, y + disp_h, outline="#777")
        cw_u, ch_u, unit = self.cell_size_unit()
        tag = "" if self.current.include else "   ·   (not printing)"
        self.preview.create_text(cw // 2, y + disp_h + 14,
                                 text=f"{cw_u:g} × {ch_u:g} {unit}   ·   "
                                      f"{self.current.name}{tag}", fill="#ccc")

    # ---- compose pages ---------------------------------------------------
    def _expanded(self):
        cw_in, ch_in = self.cell_size()
        out_w, out_h = in_to_px(cw_in, self.dpi()), in_to_px(ch_in, self.dpi())
        imgs, caps = [], []
        for it in self.items:
            if not it.include:
                continue
            img = it.render(out_w, out_h, export=True)
            for _ in range(max(1, it.copies)):
                imgs.append(img)
                caps.append(it.name)
        return imgs, caps

    def _make_pages(self, progress=None):
        if not self.items:
            messagebox.showinfo("No photos", "Add some photos first.")
            return None
        if not self._included():
            messagebox.showinfo(
                "Nothing to print",
                "No photos are marked to print. Click the ✓ column to include "
                "at least one photo.")
            return None
        cw_in, ch_in = self.cell_size()
        if cw_in <= 0 or ch_in <= 0:
            messagebox.showerror("Bad size", "Enter a valid width and height.")
            return None
        imgs, caps = self._expanded()
        try:
            return build_pages(imgs, self.page_size(), self.cell_size(),
                               self.margin_in(), self.gap_in(), self.dpi(),
                               self.guide_var.get(),
                               caps if self.caption_var.get() else None,
                               self.caption_in(), progress)
        except ValueError as e:
            messagebox.showerror("Layout error", str(e))
            return None

    def preview_page(self):
        pages = self._make_pages()
        if not pages:
            return
        win = tk.Toplevel(self)
        win.title(f"Page preview — {len(pages)} page(s)")
        win.geometry("640x820")
        idx = tk.IntVar(value=0)
        canvas = tk.Canvas(win, bg="#444", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        holder = {"img": None}

        def show(_=None):
            page = pages[idx.get()]
            cw = max(canvas.winfo_width(), 100)
            ch = max(canvas.winfo_height(), 100)
            scale = min(cw / page.width, ch / page.height) * 0.96
            disp = page.resize((max(1, int(page.width * scale)),
                                max(1, int(page.height * scale))), Image.LANCZOS)
            holder["img"] = ImageTk.PhotoImage(disp)
            canvas.delete("all")
            canvas.create_image(cw // 2, ch // 2, image=holder["img"])

        nav = ttk.Frame(win)
        nav.pack(side="bottom", fill="x")

        def go(d):
            idx.set((idx.get() + d) % len(pages))
            lbl.set(f"Page {idx.get() + 1} / {len(pages)}")
            show()

        ttk.Button(nav, text="◀ Prev", command=lambda: go(-1)).pack(side="left", padx=4, pady=4)
        lbl = tk.StringVar(value=f"Page 1 / {len(pages)}")
        ttk.Label(nav, textvariable=lbl).pack(side="left", expand=True)
        ttk.Button(nav, text="Next ▶", command=lambda: go(1)).pack(side="right", padx=4, pady=4)
        canvas.bind("<Configure>", show)
        win.after(60, show)

    # ---- exports ---------------------------------------------------------
    def _progress_window(self, title):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("320x90")
        win.transient(self)
        ttk.Label(win, text=title, padding=8).pack(anchor="w")
        bar = ttk.Progressbar(win, mode="determinate", length=280)
        bar.pack(padx=12, pady=6)
        win.update()

        def cb(done, total):
            bar["maximum"] = total
            bar["value"] = done
            win.update()
        return win, cb

    def save_pdf(self):
        path = filedialog.asksaveasfilename(
            title="Export PDF", defaultextension=".pdf",
            initialfile="printmosaic.pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        win, cb = self._progress_window("Building PDF…")
        try:
            pages = self._make_pages(progress=cb)
            if not pages:
                return
            pages[0].save(path, "PDF", resolution=float(self.dpi()),
                          save_all=True, append_images=pages[1:])
        finally:
            win.destroy()
        self.status.set(f"Saved PDF: {path}")
        messagebox.showinfo("Saved", f"Saved {len(pages)} page(s) to:\n{path}")

    def save_images(self):
        folder = filedialog.askdirectory(title="Folder for the page images")
        if not folder:
            return
        win, cb = self._progress_window("Saving images…")
        try:
            pages = self._make_pages(progress=cb)
            if not pages:
                return
            for i, page in enumerate(pages, 1):
                page.save(os.path.join(folder, f"printmosaic_page_{i:02d}.png"))
        finally:
            win.destroy()
        self.status.set(f"Saved {len(pages)} image(s) to {folder}")
        messagebox.showinfo("Saved", f"Saved {len(pages)} PNG page(s) to:\n{folder}")

    # ---- print dialog ----------------------------------------------------
    def print_pages(self):
        pages = self._make_pages()
        if not pages:
            return
        self._print_dialog(pages)

    def _print_dialog(self, pages):
        win = tk.Toplevel(self)
        win.title("Print")
        win.geometry("380x250")
        win.transient(self)
        win.grab_set()
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Print", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"{len(pages)} page(s) ready at {self.dpi()} DPI."
                  ).pack(anchor="w", pady=(2, 8))

        crow = ttk.Frame(frm)
        crow.pack(fill="x", pady=2)
        ttk.Label(crow, text="Copies of the whole set:").pack(side="left")
        copies = tk.IntVar(value=1)
        ttk.Spinbox(crow, from_=1, to=99, width=5, textvariable=copies).pack(side="left", padx=6)

        mode = tk.StringVar(value="default")
        ttk.Radiobutton(frm, text="Send to default printer",
                        value="default", variable=mode).pack(anchor="w", pady=(8, 0))
        ttk.Radiobutton(frm, text="Open in viewer to choose printer && settings",
                        value="viewer", variable=mode).pack(anchor="w")

        btns = ttk.Frame(frm)
        btns.pack(side="bottom", fill="x", pady=(12, 0))

        def do_print():
            n = max(1, int(copies.get()))
            allpages = pages * n
            tmp = os.path.join(tempfile.gettempdir(), "printmosaic_job.pdf")
            try:
                allpages[0].save(tmp, "PDF", resolution=float(self.dpi()),
                                 save_all=True, append_images=allpages[1:])
            except Exception as e:
                messagebox.showerror("Print failed", str(e), parent=win)
                return
            win.destroy()
            try:
                if mode.get() == "default":
                    send_to_printer(tmp)
                    self.status.set("Sent to default printer.")
                    messagebox.showinfo(
                        "Printing", "Sent to your default printer.\n\n"
                        "Tip: set scaling to 'Actual size' / 100% so prints "
                        "come out at the exact dimensions.")
                else:
                    open_in_viewer(tmp)
                    self.status.set("Opened in your PDF viewer for printing.")
                    messagebox.showinfo(
                        "Print", "Opened the pages in your default viewer.\n"
                        "Use its File ▸ Print dialog to pick a printer and "
                        "options. Set scaling to 'Actual size' / 100%.")
            except Exception as e:
                messagebox.showerror(
                    "Print failed",
                    f"Couldn't print automatically:\n{e}\n\nThe pages were "
                    f"saved here so you can print manually:\n{tmp}")

        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Print", command=do_print).pack(side="right", padx=6)

    # ---- project save / load --------------------------------------------
    def _gather_project(self):
        return {
            "app": APP_NAME, "version": APP_VERSION,
            "unit": self.unit_var.get(), "size": self.size_var.get(),
            "custom_w": float(self.cw_var.get()), "custom_h": float(self.chh_var.get()),
            "landscape_photo": self.landscape_photo.get(),
            "page": self.page_var.get(), "landscape_page": self.landscape_page.get(),
            "dpi": self.dpi(), "gap": float(self.gap_var.get()),
            "margin": float(self.margin_var.get()),
            "guide": self.guide_var.get(), "caption": self.caption_var.get(),
            "dark": self.dark_var.get(),
            "items": [it.to_dict() for it in self.items],
        }

    def save_project(self):
        if not self.project_path:
            return self.save_project_as()
        self._write_project(self.project_path)

    def save_project_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Project", defaultextension=PROJECT_EXT,
            filetypes=[("PrintMosaic project", "*" + PROJECT_EXT)])
        if path:
            self.project_path = path
            self._write_project(path)

    def _write_project(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._gather_project(), f, indent=2)
            self.title(f"{APP_NAME} — {os.path.basename(path)}")
            self.status.set(f"Project saved: {path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def open_project(self):
        path = filedialog.askopenfilename(
            title="Open Project",
            filetypes=[("PrintMosaic project", "*" + PROJECT_EXT), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Open failed", str(e))
            return
        self._apply_project(data)
        self.project_path = path
        self.title(f"{APP_NAME} — {os.path.basename(path)}")
        self.status.set(f"Opened project: {path}")

    def _apply_project(self, data):
        self._suspend = True
        self.unit_var.set(data.get("unit", "cm"))
        self.size_combo["values"] = list(self._size_table().keys())
        self.size_var.set(data.get("size", "9 x 9 cm"))
        self.cw_var.set(data.get("custom_w", 9.0))
        self.chh_var.set(data.get("custom_h", 9.0))
        self.landscape_photo.set(data.get("landscape_photo", False))
        self.page_var.set(data.get("page", "Letter (8.5 x 11 in)"))
        self.landscape_page.set(data.get("landscape_page", False))
        self.dpi_var.set(data.get("dpi", 300))
        self.gap_var.set(data.get("gap", 0.3))
        self.margin_var.set(data.get("margin", 0.6))
        self.guide_var.set(data.get("guide", "border"))
        self.caption_var.set(data.get("caption", False))
        self.dark_var.set(data.get("dark", False))
        self.unit_suffix.set(self.unit_var.get())
        self._suspend = False

        self.items = []
        missing = []
        for d in data.get("items", []):
            try:
                self.items.append(PhotoItem.from_dict(d))
            except Exception:
                missing.append(d.get("path", "?"))
        self.current = None
        self.apply_theme(self.dark_var.get())
        self.rebuild_tree()
        self.on_size_change()
        if self.items:
            self.select_index(0)
        if missing:
            messagebox.showwarning(
                "Some photos missing",
                "These files could not be found and were skipped:\n\n"
                + "\n".join(os.path.basename(m) for m in missing[:20]))

    # ---- help dialogs ----------------------------------------------------
    def _text_window(self, title, body, w=560, h=460):
        pal = THEMES["dark" if self.dark_var.get() else "light"]
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry(f"{w}x{h}")
        win.configure(bg=pal["bg"])
        txt = tk.Text(win, wrap="word", padx=12, pady=12, font=("Segoe UI", 10),
                      relief="flat", bg=pal["field"], fg=pal["fg"],
                      insertbackground=pal["fg"])
        txt.insert("1.0", body)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)

    def show_guide(self):
        self._text_window("User Guide", USER_GUIDE)

    def show_shortcuts(self):
        self._text_window("Keyboard Shortcuts", SHORTCUTS, h=380)

    def show_tips(self):
        self._text_window("Print Tips", PRINT_TIPS, h=360)

    def show_about(self):
        messagebox.showinfo(
            "About " + APP_NAME,
            f"{APP_NAME}  v{APP_VERSION}\n\n"
            "Lay out and print photos at album sizes, several to a page, "
            "with borders and cut guides for easy trimming.\n\n"
            "Built with Python, Tkinter, and Pillow.\nLicense: MIT.")

    # ---- status / exit ---------------------------------------------------
    def _refresh_status(self):
        inc = self._included()
        total = sum(max(1, it.copies) for it in inc)
        self.status.set(
            f"{len(self.items)} photo(s), {len(inc)} printing, "
            f"{total} print(s) total  ·  size {self.size_var.get()}  ·  "
            f"{self.dpi()} DPI")
        self._update_fit_label()

    def on_exit(self):
        self.destroy()


# --------------------------------------------------------------------------
# Help text
# --------------------------------------------------------------------------
USER_GUIDE = """\
PrintMosaic — Quick Guide

1.  Add photos
    Use Add Photos or Add Folder. Photos appear in the left list with
    thumbnails. EXIF rotation is applied automatically.

2.  Choose which photos to print
    Each row has a ✓ column. Click it to include or skip that photo without
    removing it. Use the "Print on/off" button or the Space bar to toggle the
    selected rows, or Edit ▸ Include All / Exclude All. Skipped photos are
    greyed out and left off the printed sheets.

3.  Remove photos
    Select one or more rows (Ctrl/Shift-click for several) and press Remove or
    the Delete key. Clear All empties the list.

4.  Choose a print size
    Pick centimetres (default) or inches, then a preset such as 9 x 9 cm, or
    Custom and type any width/height. "Landscape photo" swaps W/H.

5.  Frame each photo
    Select a photo, then drag inside the preview to move it and scroll to zoom.
    You can also use the sliders, rotate, and tune Brightness, Contrast,
    Saturation, or switch to Black & white. "Apply crop to all" copies the
    current settings to every photo.

6.  Copies & filling pages
    Set Copies of each photo, "To all" to apply one count to every photo, or
    "Fill page" to fill a sheet with the selected photo.

7.  Page & output
    Choose paper (Letter, A4, Legal, Tabloid, A3), orientation, and quality
    (DPI). Adjust border/gap and page margin. Pick cut guides — Lines, Corner
    marks, or None — and optionally print the filename under each photo. The
    coloured text shows photos-per-page and how many sheets the job needs.

8.  Output
    Preview Page flips through the composed sheets. Export PDF, Save Page
    Images (PNG per sheet), or Print to open the print dialog (set whole-set
    copies and send to the default printer or open in your viewer to choose
    a printer).

9.  Dark mode & projects
    Toggle Dark mode under the View menu. Save Project stores your layout,
    sizes, theme, and per-photo edits so you can reopen and reprint later.
"""

SHORTCUTS = """\
Keyboard Shortcuts

Ctrl + O      Add photos
Ctrl + S      Save project
Ctrl + E      Export PDF
Ctrl + P      Print (opens print dialog)
Ctrl + R      Preview composed page
Ctrl + [      Rotate selected photo left
Ctrl + ]      Rotate selected photo right
Space         Toggle Print on/off for selected rows
Delete        Remove selected photo(s)
F1            User guide

In the photo list:
Ctrl / Shift + click   Select several photos
Click the ✓ column     Include or skip a photo for printing

In the preview:
Drag          Move the photo within the crop
Scroll wheel  Zoom in / out
"""

PRINT_TIPS = """\
Tips for accurate prints

•  Set DPI to 300 for everyday prints, 600 for very small or detailed ones.

•  In the print dialog, "Send to default printer" prints straight away;
   "Open in viewer" lets you pick a specific printer and paper in your PDF
   viewer's own Print dialog.

•  Always choose "Actual size" or 100% scaling — never "Fit to page", or your
   photos will not come out at the exact dimensions.

•  Use matte or glossy photo paper for best results; plain paper works for
   proofs.

•  The thin gray Lines or Corner marks show where to cut. Leave a small
   border/gap so there is room to trim cleanly.

•  Big square prints (9 x 9 inch and up) are wider than Letter — switch units
   to inch and choose Tabloid or A3 paper.
"""


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
