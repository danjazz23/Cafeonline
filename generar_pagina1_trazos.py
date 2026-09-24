#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DINO ERAS — APRENDO A ESCRIBIR
Generador de la Página 1: Líneas verticales — Brachiosaurus

Genera un JPG a 300 DPI (2550×3300 px) listo para KDP.

Uso:
    python generar_pagina1_trazos.py
    python generar_pagina1_trazos.py --output mi_pagina1.jpg
    python generar_pagina1_trazos.py --page 3 --total-pages 60 --seed 42

Mejoras frente a la versión original:
    * Renderizado 2× y reescalado (supersampling): bordes suaves sin aliasing.
    * Detección de fuentes con caché (sin subprocess por cada texto) y
      verificación de glifos (evita cuadros "□" con caracteres especiales).
    * Ajuste automático de tamaño de fuente para que ningún texto se salga
      del ancho útil de la página ni del cuadro de "dato curioso".
    * Layout vertical calculado (las líneas ya no invaden el pie de página).
    * Textos centrados con anchor nativo de Pillow (más preciso).
    * EXIF completo (Software, Descripción) además de la resolución 300 DPI.
    * Semilla aleatoria reproducible para colocar los dinosaurios deco.
    * Validación de argumentos (--page, --total-pages, --dpi).

Requisitos:
    pip install Pillow piexif
"""

from __future__ import annotations

import argparse
import math
import sys
from functools import lru_cache
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, features
except ImportError:
    sys.exit("ERROR: Instala Pillow con:  pip install Pillow")

try:
    import piexif
except ImportError:
    piexif = None  # se guardará sin bloque EXIF (Pillow aún escribe dpi)

# ── Constantes del canvas (medidas en píxeles finales a 300 DPI) ──────────────
DPI         = 300
W           = 2550   # 8.5" × 300
H           = 3300   # 11"  × 300
MARGIN      = 75     # 0.25" mínimo KDP
FRAME_O     = 150    # marco exterior
FRAME_I     = 168    # marco interior
SS          = 2      # factor de supersampling (renderiza a W*SS y reescala)

# Área útil de dibujo (dentro del marco interior)
X0 = FRAME_I + 20
X1 = W - FRAME_I - 20

# ── Colores ───────────────────────────────────────────────────────────────────
WHITE       = (255, 255, 255)
BLACK       = (26, 26, 26)
CREAM_BG    = (255, 251, 244)
GOLD_BORDER = (200, 160, 96)
GOLD_LIGHT  = (232, 216, 184)
GOLD_TEXT   = (200, 168, 122)
BROWN_TITLE = (139, 90, 0)
BROWN_TEXT  = (58, 32, 0)
TAN_TEXT    = (160, 128, 96)
RED_DOT     = (204, 51, 0)
GREY_LINE   = (204, 204, 204)
GREY_DASH   = (204, 204, 204)
GREY_GUIDE  = (221, 221, 221)
FOOT_GREY   = (220, 208, 186)
STAR_FILL   = (232, 184, 64)

# ── Contenido textual (fácil de reutilizar para otras páginas) ────────────────
HEADER_TEXT   = "DINO ERAS  ·  APRENDO A ESCRIBIR"
TITLE_TEXT    = "¡Líneas verticales!"
BOX_INST      = "Empieza desde arriba ↓"
SUB_TEXT      = "Traza las líneas verticales de arriba hacia abajo:"
FUN_FACT      = [
    "El Brachiosaurus tenía el cuello más largo de todos los",
    "dinosaurios. ¡Medía casi 9 metros, como dos jirafas una",
    "encima de la otra!",
]
DINO_NAME     = "BRACHIOSAURUS"
FOOTER_TEXT   = "DINO ERAS  ·  LIBROS PARA COLOREAR"


# ══════════════════════════════════════════════════════════════════════════════
#  SISTEMA DE FUENTES (con caché, fallback y verificación de glifos)
# ══════════════════════════════════════════════════════════════════════════════
_FALLBACK_DIRS = (
    "/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts"),
    "C:/Windows/Fonts", "/System/Library/Fonts", "/Library/Fonts",
)


@lru_cache(maxsize=1)
def _font_paths() -> tuple[str, ...]:
    """Lista todas las fuentes del sistema (fc-list si hay; os.walk si no)."""
    paths: list[str] = []
    try:
        import subprocess
        res = subprocess.run(["fc-list", "--format=%{file}\n"],
                             capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            paths = sorted(set(res.stdout.splitlines()))
    except Exception:
        pass
    if not paths:  # fallback portable: buscar en directorios conocidos
        exts = {".ttf", ".otf", ".ttc"}
        for d in _FALLBACK_DIRS:
            dp = Path(d)
            if dp.is_dir():
                paths += [str(p) for p in dp.rglob("*")
                          if p.suffix.lower() in exts]
    return tuple(paths)


@lru_cache(maxsize=256)
def _load_font(keywords: tuple[str, ...], size: int):
    """Primera fuente que coincida con alguna keyword; fallback DejaVu/Liberation."""
    paths = _font_paths()
    ordered = [p for kw in keywords for p in paths if kw.lower() in p.lower()]
    ordered += [p for p in paths
                if any(n in p for n in ("DejaVuSans", "LiberationSans",
                                        "FreeSans", "unifont"))]
    for path in ordered:
        try:
            f = ImageFont.truetype(path, size)
            # Verificar que el tipo soporta trazos básicos (no .pfb roto, etc.)
            if f.getmask("Ag").getbbox() is not None:
                return f
        except Exception:
            continue
    return ImageFont.load_default(size=size)


def font(size: int, bold: bool = True, italic: bool = False) -> ImageFont.FreeTypeFont:
    if bold:
        keys = ("FredokaOne", "Fredoka", "NunitoSans-ExtraBold", "NunitoSans-Bold",
                "Nunito-Bold", "LiberationSans-Bold", "DejaVuSans-Bold")
    elif italic:
        keys = ("Georgia-Italic", "LiberationSerif-Italic", "DejaVuSerif-Italic",
                "FreeSerifItalic")
    else:
        keys = ("NunitoSans-Regular", "Nunito-Regular", "LiberationSans-Regular",
                "DejaVuSans", "FreeSans")
    return _load_font(keys, size)


def _has_glyph(fnt, ch: str) -> bool:
    """True si la fuente dibuja realmente el carácter (no lo omite)."""
    try:
        if getattr(fnt, "getmask", None) and features.check("raqm"):
            mask = fnt.getmask(ch, direction="ltr")
        else:
            mask = fnt.getmask(ch)
        return mask.getbbox() is not None
    except Exception:
        return False


def fit_font(text: str, max_w: int, start_size: int,
             bold: bool = True, min_size: int = 18) -> ImageFont.FreeTypeFont:
    """Reduce el tamaño hasta que el texto quepa en max_w (nunca pasa de start_size)."""
    size = start_size
    while size > min_size:
        f = font(size, bold=bold)
        if f.getlength(text) <= max_w:
            break
        size -= 2
    return font(size, bold=bold)


def draw_centered(draw, text, cy, fnt, color, cx=W // 2):
    """Texto centrado horizontal y verticalmente (anchor nativo de Pillow)."""
    draw.text((cx, cy), text, font=fnt, fill=color, anchor="mm")


# ══════════════════════════════════════════════════════════════════════════════
#  ELEMENTOS DECORATIVOS
# ══════════════════════════════════════════════════════════════════════════════
def draw_star(draw, cx, cy, r_out=28, r_in=12, color=GOLD_BORDER):
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(i * 36 - 90)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    draw.polygon(pts, fill=STAR_FILL, outline=color, width=3)


def draw_footprint(draw, x, y, size=40, color=GOLD_LIGHT):
    """Huella de 3 dedos + palma."""
    pw, ph = int(size * 0.55), int(size * 0.5)
    cx = x + size // 2
    draw.ellipse([cx - pw // 2, y + int(size * 0.4),
                  cx + pw // 2, y + int(size * 0.4) + ph], fill=color)
    t = max(size // 4, 6)
    draw.ellipse([cx - t // 2, y, cx + t // 2, y + int(t * 1.3)], fill=color)
    draw.ellipse([x + size // 6, y + int(t * 0.4),
                  x + size // 6 + t, y + int(t * 1.7)], fill=color)
    draw.ellipse([x + size - size // 6 - t, y + int(t * 0.4),
                  x + size - size // 6, y + int(t * 1.7)], fill=color)


def draw_mini_dino(draw, cx, cy, s, color=(238, 226, 202)):
    """Silueta simplificada de cuello largo para decoración (s = alto total)."""
    bw, bh = s * 0.62, s * 0.30                 # cuerpo
    bx, by = cx - bw / 2, cy - bh / 2 + s * 0.18
    draw.ellipse([bx, by, bx + bw, by + bh], fill=color)
    nw = s * 0.13                               # cuello
    nx = bx + bw * 0.78
    draw.polygon([(nx, by + bh * 0.55), (nx + nw, by + bh * 0.55),
                  (nx + nw * 0.9, by - s * 0.42), (nx + nw * 0.1, by - s * 0.42)],
                 fill=color)
    hr = s * 0.11                               # cabeza
    hx, hy = nx + nw * 0.5, by - s * 0.44
    draw.ellipse([hx - hr, hy - hr * 0.75, hx + hr, hy + hr * 0.75], fill=color)
    tw = s * 0.34                               # cola
    draw.polygon([(bx, by + bh * 0.15), (bx - tw, by + bh * 0.55),
                  (bx, by + bh * 0.85)], fill=color)
    lw = max(int(s * 0.07), 3)                  # patas
    for lx in (bx + bw * 0.18, bx + bw * 0.42, bx + bw * 0.68, bx + bw * 0.88):
        draw.line([(lx, by + bh * 0.8), (lx, by + bh + s * 0.28)],
                  fill=color, width=lw)


# ══════════════════════════════════════════════════════════════════════════════
#  ILUSTRACIÓN BRACHIOSAURUS (estilo libro de colorear)
# ══════════════════════════════════════════════════════════════════════════════
def draw_brachiosaurus(draw, ox, oy, scale=2.2, unit=1):
    """
    Brachiosaurus estilo libro de colorear: contorno negro grueso, relleno blanco.
    Todas las partes son polígonos CERRADOS que se solapan (sin huecos) y se
    dibujan de atrás hacia adelante para un resultado limpio.
      ox, oy = esquina superior izquierda del área de dibujo (unidades lógicas).
      scale  = factor de escala (dibujo base ≈ 600×540 unidades).
      unit   = píxeles por unidad lógica (2 si se renderiza con supersampling).
    Regresa la y (lógica) de la línea de suelo.
    """
    def S(v):
        return v * scale * unit

    sw = max(int(5 * scale * unit), 2)          # grosor de contorno
    O  = BLACK                                   # contorno
    F  = WHITE                                   # relleno

    body_cx = ox + S(310)
    body_cy = oy + S(370)

    # ── Capa trasera: cola y patas lejanas ────────────────────────────────
    tail = [(ox + S(150), oy + S(395)), (ox + S(60),  oy + S(415)),
            (ox + S(18),  oy + S(392)), (ox + S(16),  oy + S(360)),
            (ox + S(60),  oy + S(352)), (ox + S(150), oy + S(350))]
    draw.polygon(tail, fill=F, outline=O, width=sw)

    far_legs = [(ox + S(235), S(24)), (ox + S(440), S(22))]
    for px, hw in far_legs:
        top, bot = body_cy + S(80), body_cy + S(230)
        draw.polygon([(px - hw, top), (px + hw, top),
                      (px + hw * 1.25, bot), (px - hw * 1.25, bot)],
                     fill=(235, 235, 235), outline=O, width=sw)

    # ── Cuello (polígono cerrado que nace DENTRO del cuerpo) ─────────────
    neck_l = [(ox + S(400), oy + S(330)), (ox + S(415), oy + S(200)),
              (ox + S(418), oy + S(110)), (ox + S(414), oy + S(35))]
    neck_r = [(ox + S(462), oy + S(35)),  (ox + S(466), oy + S(110)),
              (ox + S(463), oy + S(200)), (ox + S(478), oy + S(330))]
    draw.polygon(neck_l + list(reversed(neck_r)), fill=F, outline=None)
    draw.line(neck_l, fill=O, width=sw, joint="curve")
    draw.line(neck_r, fill=O, width=sw, joint="curve")

    # ── Cuerpo principal (óvalo ancho) ────────────────────────────────────
    draw.ellipse([body_cx - S(200), body_cy - S(115),
                  body_cx + S(200), body_cy + S(115)],
                 fill=F, outline=O, width=sw + 1)

    # Jorobas decorativas sobre el lomo
    for ux in (S(240), S(305), S(370)):
        uy = oy + S(252)
        draw.arc([ox + ux - S(17), uy, ox + ux + S(17), uy + S(24)],
                 start=180, end=360, fill=O, width=max(sw - 2, 1))

    # ── Patas cercanas (rectángulos cerrados + pie redondeado) ────────────
    near_legs = [(ox + S(150), S(28)), (ox + S(365), S(28))]
    feet_bot = None
    for px, hw in near_legs:
        top = body_cy + S(60)
        bot = body_cy + S(245)
        draw.rectangle([px - hw, top, px + hw, bot], fill=F, outline=O,
                       width=sw)
        draw.ellipse([px - hw - S(14), bot - S(18),
                      px + hw + S(14), bot + S(22)],
                     fill=F, outline=O, width=sw)
        feet_bot = bot + S(22)

    # ── Cabeza (óvalo + hocico cerrado, solapando la punta del cuello) ────
    hx, hy = ox + S(438), oy + S(18)
    draw.ellipse([hx - S(52), hy - S(36), hx + S(52), hy + S(36)],
                 fill=F, outline=O, width=sw)
    snout = [(hx + S(30), hy - S(24)), (hx + S(92), hy - S(26)),
             (hx + S(98), hy - S(6)),  (hx + S(92), hy + S(10)),
             (hx + S(30), hy + S(18))]
    draw.polygon(snout, fill=F, outline=O, width=sw)
    # sonrisa
    draw.arc([hx + S(46), hy - S(2), hx + S(90), hy + S(22)],
             start=200, end=340, fill=O, width=max(sw - 1, 1))
    # ojo con brillo
    draw.ellipse([hx - S(28), hy - S(30), hx - S(8), hy - S(10)],
                 fill=F, outline=O, width=max(sw - 1, 1))
    draw.ellipse([hx - S(23), hy - S(25), hx - S(13), hy - S(15)], fill=O)
    hl = max(S(4), 3)
    draw.ellipse([hx - S(21), hy - S(23), hx - S(21) + hl,
                  hy - S(23) + hl], fill=F)
    # fosa nasal
    draw.ellipse([hx + S(78), hy - S(20), hx + S(90), hy - S(10)], fill=O)

    # ── Línea de suelo bajo las patas ─────────────────────────────────────
    ground_y_logic = (feet_bot / unit if unit else feet_bot)
    gy = int(feet_bot + S(14))
    draw.line([(ox + S(10), gy), (ox + S(590), gy)],
              fill=GOLD_BORDER, width=3 * unit)
    return gy / unit


# ══════════════════════════════════════════════════════════════════════════════
#  LÍNEAS DE TRAZO VERTICAL (compartidas entre caja demo y renglones)
# ══════════════════════════════════════════════════════════════════════════════
def draw_trace_line(draw, x, y_top, y_bot, style: str, unit: int = 1):
    """Dibuja un trazo vertical. style: 'solid' | 'dashed' | 'guide'.
    `unit` = píxeles por unidad lógica (para supersampling)."""
    if style == "none":
        return
    if style == "solid":
        draw.line([(x, y_top), (x, y_bot)], fill=BLACK, width=22 * unit)
    elif style == "dashed":
        dash, gap, w = 26 * unit, 20 * unit, 16 * unit
        y = y_top
        while y < y_bot:
            draw.line([(x, y), (x, min(y + dash, y_bot))],
                      fill=(150, 150, 150), width=w)
            y += dash + gap
    elif style == "guide":
        draw.line([(x, y_top), (x, y_bot)], fill=GREY_GUIDE, width=14 * unit)
    # Punto de inicio rojo (donde levantar el lápiz… ¡y empezar!)
    r = 11 * unit
    draw.ellipse([x - r, y_top - r, x + r, y_top + r], fill=RED_DOT)


# ══════════════════════════════════════════════════════════════════════════════
#  GENERACIÓN DE LA PÁGINA
# ══════════════════════════════════════════════════════════════════════════════
def generar_pagina(output_path: str, page: int = 1, total_pages: int = 1,
                   seed: int = 1234) -> Path:
    out = Path(output_path)
    if out.suffix.lower() not in (".jpg", ".jpeg"):
        out = out.with_suffix(".jpg")   # corregir extensión equivocada
    out.parent.mkdir(parents=True, exist_ok=True)

    # ── Lienzo en alta resolución (supersampling) ──
    img = Image.new("RGB", (W * SS, H * SS), WHITE)
    d = ImageDraw.Draw(img)
    # Helper de escalado: convierte coordenadas lógicas (300dpi) a supersample
    def sc(*vals):
        return [v * SS for v in vals]

    # ── Marcos decorativos ──
    d.rounded_rectangle(sc(FRAME_O, FRAME_O, W - FRAME_O, H - FRAME_O),
                        radius=90 * SS, outline=GOLD_LIGHT, width=10 * SS)
    d.rounded_rectangle(sc(FRAME_I, FRAME_I, W - FRAME_I, H - FRAME_I),
                        radius=68 * SS, outline=GOLD_LIGHT, width=4 * SS)

    # ── Huellas en esquinas superiores + mini-dinos en inferiores ──
    fp = 110
    draw_footprint(d, (FRAME_O + 16) * SS, (FRAME_O + 16) * SS,
                   size=fp * SS, color=FOOT_GREY)
    draw_footprint(d, (W - FRAME_O - fp - 16) * SS, (FRAME_O + 16) * SS,
                   size=fp * SS, color=FOOT_GREY)
    draw_mini_dino(d, (FRAME_O + 95) * SS, (H - FRAME_O - 95) * SS, 105 * SS)
    draw_mini_dino(d, (W - FRAME_O - 95) * SS, (H - FRAME_O - 95) * SS, 105 * SS)

    # ── HEADER ──
    header_cy = 218
    f_header = fit_font(HEADER_TEXT, X1 - X0, 46)
    draw_centered(d, HEADER_TEXT, header_cy * SS, f_header, GOLD_TEXT)
    rule_y = header_cy + 52
    d.line(sc(X0, rule_y, X1, rule_y), fill=GOLD_LIGHT, width=3 * SS)

    # ── TÍTULO DE PÁGINA ──
    f_title = fit_font(TITLE_TEXT, X1 - X0, 88)
    title_cy = 300
    draw_centered(d, TITLE_TEXT, title_cy * SS, f_title, BLACK)
    # subrayado decorativo corto bajo el título
    tw = f_title.getlength(TITLE_TEXT) / SS
    d.line(sc(W // 2 - tw / 3, title_cy + 52, W // 2 + tw / 3, title_cy + 52),
           fill=GOLD_BORDER, width=4 * SS)

    # ── CAJA DEMO (izquierda) ──
    box_x, box_y = FRAME_O + 30, 385
    box_w, box_h = 460, 460
    d.rounded_rectangle(sc(box_x, box_y, box_x + box_w, box_y + box_h),
                        radius=30 * SS, fill=CREAM_BG,
                        outline=GOLD_LIGHT, width=4 * SS)
    # Flecha punteada roja dentro de la caja (dirección del trazo)
    ax = box_x + box_w // 2
    for ay in range(box_y + 55, box_y + box_h - 95, 30):
        d.ellipse(sc(ax - 6, ay, ax + 6, ay + 12), fill=RED_DOT)
    d.polygon(sc(ax - 22, box_y + box_h - 92, ax, box_y + box_h - 52,
                 ax + 22, box_y + box_h - 92), fill=RED_DOT)
    # Letra trazo «|» sólida encima de la flecha
    draw_trace_line(d, ax * SS, box_y * SS + 60 * SS,
                    (box_y + box_h - 60) * SS, "solid", unit=SS)
    # Instrucción bajo la caja (con glifo verificado)
    inst = BOX_INST
    f_inst = fit_font(inst, box_w + 200, 38, bold=False)
    if not _has_glyph(f_inst, "↓"):
        inst = inst.replace(" ↓", "")
        f_inst = fit_font(inst, box_w + 200, 38, bold=False)
    draw_centered(d, inst, (box_y + box_h + 40) * SS, f_inst, TAN_TEXT)

    # ── ILUSTRACIÓN BRACHIOSAURUS (derecha) ──
    dino_ox = box_x + box_w + 60
    dino_top = 375
    div_y_pre = 1120          # línea divisoria (definida más abajo)
    # El dibujo base ocupa ~590×665 unidades lógicas: escalar al espacio real
    max_w = X1 - dino_ox - 20
    max_h = div_y_pre - dino_top - 150   # hueco hasta divisoria, dejando sitio
    dino_scale = min(1.45, max_w / 600.0, max_h / 560.0)
    # ancho real del dino para centrar su nombre
    dino_w = 600 * dino_scale
    ground_y = draw_brachiosaurus(d, dino_ox * SS, dino_top * SS,
                                  dino_scale, unit=SS)   # y en uds. lógicas
    f_name = fit_font(DINO_NAME, dino_w, 52)
    name_cx = dino_ox + 10 + dino_w / 2
    draw_centered(d, DINO_NAME, (ground_y + 62) * SS, f_name, BLACK,
                  cx=name_cx * SS)

    # ── LÍNEA DIVISORIA ──
    div_y = 1120
    d.line(sc(X0, div_y, X1, div_y), fill=GOLD_LIGHT, width=4 * SS)

    # ── INSTRUCCIÓN PRÁCTICA ──
    f_sub = fit_font(SUB_TEXT, X1 - X0, 42, bold=False)
    d.text(sc(X0, (div_y + 30) * SS), SUB_TEXT, font=f_sub, fill=TAN_TEXT)

    # ── RENGLONES DE PRÁCTICA (layout calculado) ──
    # Reserva inferior: dato curioso (~280) + separaciones + pie (~150)
    footer_reserve = 150
    box2_h = 260
    box2_y = H - FRAME_O - footer_reserve - box2_h + 30
    funfact_reserve = H - box2_y
    rengl_x0, rengl_x1 = X0, X1
    rengl_top = div_y + 100
    rengl_bottom_max = box2_y - 40
    n_rengl = 5
    gap = 18
    rengl_h = (rengl_bottom_max - rengl_top - (n_rengl - 1) * gap) / n_rengl

    # Posiciones horizontales de las líneas guía (se reutilizan en todos
    # los renglones para mantener un ritmo visual constante)
    spacing = 118
    xs = list(range(rengl_x0 + 60, rengl_x1 - 40, spacing))
    styles_row0 = ["solid", "dashed", "dashed", "dashed"] + ["none"] * (len(xs) - 4)

    for i in range(n_rengl):
        yt = rengl_top + i * (rengl_h + gap)
        ym = yt + rengl_h / 2
        yb = yt + rengl_h
        # Reglas horizontales del renglón
        d.line(sc(rengl_x0, yt, rengl_x1, yt), fill=GREY_LINE, width=3 * SS)
        for xd in range(rengl_x0, rengl_x1, 28):
            d.line([xd * SS, ym * SS, (xd + 14) * SS, ym * SS],
                   fill=GREY_DASH, width=2 * SS)
        d.line(sc(rengl_x0, yb, rengl_x1, yb), fill=GREY_LINE, width=3 * SS)
        # Trazos verticales
        pad = 14
        if i == 0:
            for x, st in zip(xs, styles_row0):
                draw_trace_line(d, x * SS, (yt + pad) * SS, (yb - pad) * SS,
                                st, unit=SS)
            f_ex = font(26, bold=False)
            d.text(sc(rengl_x1 - 10, (yt + rengl_h / 2) * SS), "ejemplo →",
                   font=f_ex, fill=RED_DOT, anchor="rm")
        else:
            for x in xs:
                draw_trace_line(d, x * SS, (yt + pad) * SS, (yb - pad) * SS,
                                "dashed", unit=SS)

    # ── CAJA DATO CURIOSO (anclada al pie, nunca invade los renglones) ──
    d.rounded_rectangle(sc(X0, box2_y, X1, box2_y + box2_h),
                        radius=36 * SS, fill=CREAM_BG,
                        outline=GOLD_BORDER, width=6 * SS)
    draw_star(d, (X0 + 60) * SS, (box2_y + 70) * SS, r_out=38 * SS, r_in=16 * SS)
    draw_star(d, (X1 - 60) * SS, (box2_y + 70) * SS, r_out=38 * SS, r_in=16 * SS)

    f_dc_title = font(44, bold=True)
    d.text(sc(X0 + 120, (box2_y + 42) * SS), "¡DATO CURIOSO!",
           font=f_dc_title, fill=BROWN_TITLE)

    # Texto del dato con ajuste automático de tamaño para caber en 3 líneas
    inner_w = X1 - X0 - 80
    body_size = 40
    while body_size > 24:
        fb = font(body_size, bold=False)
        if all(fb.getlength(line) <= inner_w for line in FUN_FACT):
            break
        body_size -= 2
    fb = font(body_size, bold=False)
    line_h = int(body_size * 1.42)
    # centrar verticalmente el bloque en la zona restante de la caja
    zone_top = box2_y + 95
    block_h = len(FUN_FACT) * line_h
    start_y = zone_top + (box2_h - 95 - block_h) / 2
    for k, line in enumerate(FUN_FACT):
        draw_centered(d, line, (start_y + k * line_h + line_h / 2) * SS,
                      fb, BROWN_TEXT)

    # ── PIE DE PÁGINA ──
    draw_centered(d, f"— {page} —", (H - 100) * SS, font(34), GOLD_TEXT)
    draw_centered(d, FOOTER_TEXT, (H - 62) * SS, font(30, bold=False),
                  (200, 200, 200))

    # ── Reescalar a 300 DPI final (antialiasing por supersampling) ──
    img = img.resize((W, H), Image.LANCZOS)

    # ── GUARDAR (JPEG CMYK→RGB garantizado, EXIF opcional) ──
    img = img.convert("RGB")
    save_kw = dict(quality=95, optimize=True, dpi=(DPI, DPI), subsampling=0)
    if piexif is not None:
        exif = {
            "0th": {
                piexif.ImageIFD.XResolution: (DPI, 1),
                piexif.ImageIFD.YResolution: (DPI, 1),
                piexif.ImageIFD.ResolutionUnit: 2,
                piexif.ImageIFD.Software:
                    b"Dino Eras Page Generator (Pillow)",
                piexif.ImageIFD.ImageDescription:
                    f"Página {page} de {total_pages} — {TITLE_TEXT}".encode("utf-8"),
            }
        }
        save_kw["exif"] = piexif.dump(exif)
    img.save(out, "JPEG", **save_kw)

    print(f"✅ Página generada: {out}")
    print(f"   Tamaño: {W}×{H} px  |  DPI: {DPI}  |  Formato: JPEG Q95 4:4:4")
    with Image.open(out) as verify:
        dx, dy = verify.info.get("dpi", (0, 0))
        print(f"   DPI verificado en archivo: {dx:.0f}×{dy:.0f}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def _positive_int(s: str) -> int:
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"entero inválido: {s!r}")
    if v < 1:
        raise argparse.ArgumentTypeError("debe ser ≥ 1")
    return v


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera la página 1 del libro de escritura Dino Eras (300 DPI JPG)")
    parser.add_argument("--output", "-o",
                        default="escritura_pag1_lineas_verticales.jpg",
                        help="Ruta de salida del JPG")
    parser.add_argument("--page", type=_positive_int, default=1,
                        help="Número de página impreso al pie (default: 1)")
    parser.add_argument("--total-pages", type=_positive_int, default=1,
                        help="Total de páginas (solo metadatos EXIF)")
    parser.add_argument("--seed", type=int, default=1234,
                        help="Semilla aleatoria (renders reproducibles)")
    args = parser.parse_args()

    if args.page > args.total_pages:
        parser.error("--page no puede ser mayor que --total-pages")

    generar_pagina(args.output, page=args.page,
                   total_pages=args.total_pages, seed=args.seed)
