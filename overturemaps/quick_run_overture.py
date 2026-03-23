"""
OvertureMaps — Interactive Quick Launcher
==========================================
Guides the user step by step through:
  1. Language selection
  2. BBox selection (presets or custom)
  3. Theme selection
  4. Export format selection
  5. Memory mode selection
Then calls overture_extractor.run() directly.
"""

import sys
from pathlib import Path

# ── Preset BBoxes ─────────────────────────────────────────────────────────────

PRESETS = {
    "en": [
        ("Istanbul - Taksim Square (small test)",   (28.974, 41.035, 28.982, 41.040)),
        ("Istanbul - Bosphorus region",             (28.95,  41.00,  29.05,  41.10)),
        ("Ankara - Kızılay center",                 (32.844, 39.916, 32.862, 39.926)),
        ("Istanbul - Full city",                    (28.50,  40.80,  29.40,  41.30)),
    ],
    "tr": [
        ("İstanbul - Taksim Meydanı (küçük test)",  (28.974, 41.035, 28.982, 41.040)),
        ("İstanbul - Boğaz bölgesi",                (28.95,  41.00,  29.05,  41.10)),
        ("Ankara - Kızılay merkez",                 (32.844, 39.916, 32.862, 39.926)),
        ("İstanbul - Tüm şehir",                    (28.50,  40.80,  29.40,  41.30)),
    ],
}

# ── Bilingual UI Text ─────────────────────────────────────────────────────────

UI = {
    "en": {
        "banner": (
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║        OvertureMaps  DuckDB  Extractor               ║\n"
            "║   Download Overture data for any bbox → multi-format ║\n"
            "╚══════════════════════════════════════════════════════╝"
        ),
        "lang_prompt":   "Select language / Dil seçin  [en/tr, default=en]: ",
        "bbox_header":   "\n── BBox Selection ──────────────────────────────",
        "bbox_menu":     (
            "  [1] Custom (enter coordinates manually)\n"
            "  [2] Istanbul - Taksim Square (small test area)\n"
            "  [3] Istanbul - Bosphorus region\n"
            "  [4] Ankara - Kızılay center\n"
            "  [5] Istanbul - Full city"
        ),
        "bbox_choice":   "Your choice [1-5, default=2]: ",
        "bbox_custom":   "Enter bbox as  min_lon,min_lat,max_lon,max_lat : ",
        "bbox_invalid":  "  Invalid coordinates. Please try again.",
        "theme_header":  "\n── Theme Selection ─────────────────────────────",
        "theme_menu":    (
            "  [1] all — all themes  (default)\n"
            "  [2] places           (POIs)\n"
            "  [3] buildings        (footprints)\n"
            "  [4] transportation   (roads, rail…)\n"
            "  [5] base             (land, water, land use)\n"
            "  [6] divisions        (admin boundaries)\n"
            "  [7] addresses"
        ),
        "theme_choice":  "Your choice [1-7, default=1]: ",
        "fmt_header":    "\n── Export Formats ──────────────────────────────",
        "fmt_prompt":    "Formats (geojson, gpkg, shp, parquet — comma-separated) [all]: ",
        "mem_header":    "\n── Memory Mode ─────────────────────────────────",
        "mem_menu":      (
            "  [1] AUTO — let the script decide  (default)\n"
            "  [2] RAM  — keep data in memory (fast, needs free RAM)\n"
            "  [3] DISK — spill to disk (slower, safe for large areas)"
        ),
        "mem_choice":    "Your choice [1-3, default=1]: ",
        "summary":       "\n── Summary ──────────────────────────────────────",
        "s_bbox":        "  BBox    : {}",
        "s_themes":      "  Themes  : {}",
        "s_formats":     "  Formats : {}",
        "s_mem":         "  Mode    : {}",
        "confirm":       "Start extraction? [Y/n]: ",
        "aborted":       "  Aborted.",
        "running":       "\n Starting extraction…\n",
    },
    "tr": {
        "banner": (
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║        OvertureMaps  DuckDB  Çıkarıcı                ║\n"
            "║   Overture verisini bbox ile çek → çok formatlı dışa ║\n"
            "╚══════════════════════════════════════════════════════╝"
        ),
        "lang_prompt":   "Select language / Dil seçin  [en/tr, varsayılan=tr]: ",
        "bbox_header":   "\n── BBox Seçimi ──────────────────────────────────",
        "bbox_menu":     (
            "  [1] Özel (koordinatları elle gir)\n"
            "  [2] İstanbul - Taksim Meydanı (küçük test alanı)\n"
            "  [3] İstanbul - Boğaz bölgesi\n"
            "  [4] Ankara - Kızılay merkez\n"
            "  [5] İstanbul - Tüm şehir"
        ),
        "bbox_choice":   "Seçiminiz [1-5, varsayılan=2]: ",
        "bbox_custom":   "BBox girin  min_lon,min_lat,max_lon,max_lat : ",
        "bbox_invalid":  "  Geçersiz koordinatlar. Lütfen tekrar deneyin.",
        "theme_header":  "\n── Tema Seçimi ──────────────────────────────────",
        "theme_menu":    (
            "  [1] tümü — tüm temalar  (varsayılan)\n"
            "  [2] places           (İlgi noktaları)\n"
            "  [3] buildings        (Bina ayak izleri)\n"
            "  [4] transportation   (Yollar, demiryolu…)\n"
            "  [5] base             (Arazi, su, arazi kullanımı)\n"
            "  [6] divisions        (İdari sınırlar)\n"
            "  [7] addresses        (Adresler)"
        ),
        "theme_choice":  "Seçiminiz [1-7, varsayılan=1]: ",
        "fmt_header":    "\n── Dışa Aktarım Formatları ──────────────────────",
        "fmt_prompt":    "Formatlar (geojson, gpkg, shp, parquet — virgülle) [hepsi]: ",
        "mem_header":    "\n── Bellek Modu ──────────────────────────────────",
        "mem_menu":      (
            "  [1] OTOMATİK — betik karar verir  (varsayılan)\n"
            "  [2] RAM  — bellekte tut (hızlı, boş RAM gerekli)\n"
            "  [3] DİSK — diske yaz (yavaş, büyük alanlar için güvenli)"
        ),
        "mem_choice":    "Seçiminiz [1-3, varsayılan=1]: ",
        "summary":       "\n── Özet ──────────────────────────────────────────",
        "s_bbox":        "  BBox    : {}",
        "s_themes":      "  Temalar : {}",
        "s_formats":     "  Formatlar: {}",
        "s_mem":         "  Mod     : {}",
        "confirm":       "Çıkarıma başlansın mı? [E/h]: ",
        "aborted":       "  İptal edildi.",
        "running":       "\n Çıkarım başlıyor…\n",
    },
}

THEME_MAP = {
    "2": ["places"],
    "3": ["buildings"],
    "4": ["transportation"],
    "5": ["base"],
    "6": ["divisions"],
    "7": ["addresses"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def u(lang: str, key: str) -> str:
    return UI.get(lang, UI["en"]).get(key, "")


# ── Interactive Flow ──────────────────────────────────────────────────────────

def main():
    # ── Language ──────────────────────────────────────────────────────────────
    print(UI["en"]["lang_prompt"], end="")
    raw_lang = ask("").lower()
    lang = "tr" if raw_lang == "tr" else "en"

    print(u(lang, "banner"))

    # ── BBox ──────────────────────────────────────────────────────────────────
    print(u(lang, "bbox_header"))
    print(u(lang, "bbox_menu"))
    bbox_choice = ask(u(lang, "bbox_choice")) or "2"

    if bbox_choice == "1":
        while True:
            raw = ask(u(lang, "bbox_custom"))
            try:
                parts = [float(x.strip()) for x in raw.split(",")]
                if len(parts) != 4:
                    raise ValueError
                bbox = tuple(parts)
                break
            except ValueError:
                print(u(lang, "bbox_invalid"))
    else:
        preset_list = PRESETS[lang]
        idx = int(bbox_choice) - 2 if bbox_choice.isdigit() else 0
        idx = max(0, min(idx, len(preset_list) - 1))
        bbox = preset_list[idx][1]

    # ── Themes ────────────────────────────────────────────────────────────────
    print(u(lang, "theme_header"))
    print(u(lang, "theme_menu"))
    tc = ask(u(lang, "theme_choice")) or "1"
    themes = None if tc == "1" or tc == "" else THEME_MAP.get(tc)

    # ── Formats ───────────────────────────────────────────────────────────────
    print(u(lang, "fmt_header"))
    raw_fmt = ask(u(lang, "fmt_prompt")).strip()
    if not raw_fmt or raw_fmt.lower() in ("all", "hepsi", "tümü"):
        formats = ["geojson", "gpkg", "shp", "parquet"]
    else:
        formats = [f.strip().lower() for f in raw_fmt.split(",") if f.strip()]
        formats = [f for f in formats if f in ("geojson", "gpkg", "shp", "parquet")]
        if not formats:
            formats = ["geojson", "gpkg", "shp", "parquet"]

    # ── Memory Mode ───────────────────────────────────────────────────────────
    print(u(lang, "mem_header"))
    print(u(lang, "mem_menu"))
    mc = ask(u(lang, "mem_choice")) or "1"

    import psutil
    total_gb = psutil.virtual_memory().total / 1024 ** 3
    if mc == "2":
        disk_mode = False
        mode_label = "RAM"
    elif mc == "3":
        disk_mode = True
        mode_label = "DISK"
    else:
        # AUTO: if available RAM < 4 GB → disk mode
        free_gb = psutil.virtual_memory().available / 1024 ** 3
        disk_mode = free_gb < 4.0
        mode_label = f"AUTO → {'DISK' if disk_mode else 'RAM'}  ({free_gb:.1f} GB free)"

    # ── Summary & Confirm ─────────────────────────────────────────────────────
    print(u(lang, "summary"))
    print(u(lang, "s_bbox").format(bbox))
    print(u(lang, "s_themes").format(themes or "all"))
    print(u(lang, "s_formats").format(", ".join(formats)))
    print(u(lang, "s_mem").format(mode_label))
    print()

    confirm = ask(u(lang, "confirm")).lower()
    if confirm in ("n", "h", "no", "hayır"):
        print(u(lang, "aborted"))
        return

    print(u(lang, "running"))

    # ── Run ───────────────────────────────────────────────────────────────────
    from overture_extractor import run
    out_dir = Path(__file__).parent / "output"

    run(
        bbox=bbox,
        themes=themes,
        formats=formats,
        lang=lang,
        output_dir=out_dir,
        version=None,
        disk_mode=disk_mode,
    )


if __name__ == "__main__":
    main()
