"""
OvertureMaps DuckDB Extractor
==============================
Fetches Overture Maps data for a given bbox using DuckDB + S3,
exports to GeoJSON, GeoPackage, Shapefile, and Parquet.
Geometries are separated into points / lines / polygons.
Bilingual messages: EN / TR.
"""

import os
import gc
import sys
import json
import argparse
import re
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import psutil
from shapely import wkt as shapely_wkt

# ── Constants ────────────────────────────────────────────────────────────────

OVERTURE_S3   = "s3://overturemaps-us-west-2/release"
STAC_URL      = "https://stac.overturemaps.org/catalog.json"
RAM_LIMIT_PCT = 75
RAM_FREE_GB   = 2.0
FILE_SPLIT_GB = 3.8          # GeoJSON / SHP part split threshold

THEMES = {
    "places":         ["place"],
    "buildings":      ["building", "building_part"],
    "transportation": ["segment", "connector"],
    "addresses":      ["address"],
    "base":           ["land", "water", "land_use", "infrastructure"],
    "divisions":      ["division_area", "division_boundary"],
}

# Extra columns per theme (added to SELECT)
THEME_EXTRA_COLS = {
    "buildings": [
        "CAST(height AS VARCHAR) AS height",
        "CAST(num_floors AS VARCHAR) AS num_floors",
        "CAST(class AS VARCHAR) AS building_class",
    ],
    "transportation": [
        "CAST(class AS VARCHAR) AS road_class",
        "CAST(subtype AS VARCHAR) AS subtype",
    ],
    "addresses": [
        "CAST(country AS VARCHAR) AS country",
        "CAST(postcode AS VARCHAR) AS postcode",
        "CAST(street AS VARCHAR) AS street",
        "CAST(number AS VARCHAR) AS addr_number",
    ],
    "divisions": [
        "CAST(country AS VARCHAR) AS country",
        "CAST(region AS VARCHAR) AS region",
        "CAST(subtype AS VARCHAR) AS subtype",
    ],
    "base": [
        "CAST(subtype AS VARCHAR) AS subtype",
        "CAST(class AS VARCHAR) AS base_class",
    ],
}

GEOM_GROUPS = {
    "points":   ("Point", "MultiPoint"),
    "lines":    ("LineString", "MultiLineString"),
    "polygons": ("Polygon", "MultiPolygon"),
}

# ── Bilingual Messages ────────────────────────────────────────────────────────

MSG = {
    "en": {
        "connecting":    "\n[1/4] Connecting to Overture Maps S3 via DuckDB...",
        "version_detect":"[2/4] Detecting latest Overture Maps release...",
        "version_found": "      Release : {}\n",
        "version_fail":  "      Could not auto-detect version; using fallback: {}",
        "querying":      "[3/4] Querying  theme={} / type={}  bbox={}",
        "no_data":       "      No data found for {}/{}. Skipping.",
        "row_count":     "      Found {:,} features.",
        "ram_warn":      "      WARNING: RAM pressure detected ({:.0f}% used). "
                         "Consider using --disk mode for larger areas.",
        "exporting":     "[4/4] Exporting {} ({} features) ...",
        "skip_empty":    "      No {} geometry in this layer — skipped.",
        "export_done":   "      Saved  {}",
        "shp_split":     "      SHP file size limit reached — starting new part: {}",
        "geojson_split": "      GeoJSON file size limit reached — starting new part: {}",
        "done":          "\n Done! All outputs written to: {}\n",
        "error":         " Error: {}",
        "col_truncated": "      Note: Column names truncated to 10 chars for Shapefile.",
    },
    "tr": {
        "connecting":    "\n[1/4] Overture Maps S3 bağlantısı DuckDB ile kuruluyor...",
        "version_detect":"[2/4] En güncel Overture Maps sürümü tespit ediliyor...",
        "version_found": "      Sürüm   : {}\n",
        "version_fail":  "      Sürüm otomatik tespit edilemedi; yedek kullanılıyor: {}",
        "querying":      "[3/4] Sorgulanıyor  tema={} / tip={}  bbox={}",
        "no_data":       "      {}/{} için veri bulunamadı. Atlanıyor.",
        "row_count":     "      {:,} obje bulundu.",
        "ram_warn":      "      UYARI: RAM baskısı algılandı ({:.0f}% dolu). "
                         "Daha geniş alanlar için --disk modunu tercih edin.",
        "exporting":     "[4/4] Dışa aktarılıyor {} ({} obje) ...",
        "skip_empty":    "      Bu katmanda {} geometrisi yok — atlandı.",
        "export_done":   "      Kaydedildi  {}",
        "shp_split":     "      SHP boyut limiti aşıldı — yeni parça başlatılıyor: {}",
        "geojson_split": "      GeoJSON boyut limiti aşıldı — yeni parça başlatılıyor: {}",
        "done":          "\n Tamamlandı! Tüm çıktılar şuraya yazıldı: {}\n",
        "error":         " Hata: {}",
        "col_truncated": "      Not: Shapefile için sütun adları 10 karaktere kısaltıldı.",
    },
}


def msg(lang, key, *args):
    text = MSG.get(lang, MSG["en"]).get(key, "")
    return text.format(*args) if args else text


# ── DuckDB Setup ─────────────────────────────────────────────────────────────

def setup_duckdb(disk_mode: bool = False, tmp_dir: str | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()

    for ext in ("httpfs", "spatial"):
        # 1st attempt: install (downloads if not present) + load
        try:
            con.execute(f"INSTALL '{ext}';")
        except Exception:
            pass  # already installed or no network — try to LOAD anyway

        try:
            con.execute(f"LOAD '{ext}';")
        except Exception as load_err:
            # Extension truly missing — give user a clear action message
            raise RuntimeError(
                f"\n  DuckDB extension '{ext}' could not be loaded.\n"
                f"  Run the following in Python once to install it:\n\n"
                f"      import duckdb; c=duckdb.connect(); c.execute(\"INSTALL {ext}\")\n\n"
                f"  Then retry.  (Original error: {load_err})"
            ) from load_err

    con.execute("SET s3_region='us-west-2';")
    con.execute("SET s3_access_key_id='';")
    con.execute("SET s3_secret_access_key='';")
    if disk_mode:
        tmp = tmp_dir or str(Path.cwd() / "overturemaps" / "_duckdb_tmp")
        Path(tmp).mkdir(parents=True, exist_ok=True)
        con.execute(f"SET temp_directory='{tmp}';")
        con.execute("SET memory_limit='1GB';")
    else:
        con.execute("SET memory_limit='6GB';")
    con.execute("SET threads=4;")
    return con


# ── Version Detection ─────────────────────────────────────────────────────────

FALLBACK_VERSION = "2025-05-21.0"


def get_latest_version(con: duckdb.DuckDBPyConnection, lang: str) -> str:
    print(msg(lang, "version_detect"))
    try:
        result = con.execute(
            f"SELECT json->>'$.latest' FROM read_json('{STAC_URL}')"
        ).fetchone()
        if result and result[0]:
            version = result[0].strip()
            print(msg(lang, "version_found", version))
            return version
    except Exception:
        pass
    # Fallback
    print(msg(lang, "version_fail", FALLBACK_VERSION))
    return FALLBACK_VERSION


# ── Query Builder ─────────────────────────────────────────────────────────────

def build_query(version: str, theme: str, type_: str, bbox: tuple) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    s3_url = f"{OVERTURE_S3}/{version}/theme={theme}/type={type_}/*.parquet"

    base_cols = [
        "id",
        "CAST(names AS VARCHAR) AS names_raw",
        "CAST(sources AS VARCHAR) AS sources_raw",
        "CAST(confidence AS DOUBLE) AS confidence",
        "ST_AsText(geometry) AS wkt",
        "ST_GeometryType(geometry) AS geom_type_str",
    ]
    extra = THEME_EXTRA_COLS.get(theme, [])
    all_cols = ",\n        ".join(base_cols + extra)

    return f"""
    SELECT
        {all_cols}
    FROM read_parquet('{s3_url}', hive_partitioning=false)
    WHERE bbox.xmin < {max_lon}
      AND bbox.xmax > {min_lon}
      AND bbox.ymin < {max_lat}
      AND bbox.ymax > {min_lat}
    """


# ── Fetch → GeoDataFrame ──────────────────────────────────────────────────────

def fetch_to_gdf(con: duckdb.DuckDBPyConnection, query: str, lang: str) -> gpd.GeoDataFrame | None:
    try:
        df = con.execute(query).df()
    except Exception as e:
        print(msg(lang, "error", e))
        return None

    if df.empty:
        return None

    try:
        geom_series = gpd.GeoSeries.from_wkt(df["wkt"], crs="EPSG:4326")
        df = df.drop(columns=["wkt"])
        gdf = gpd.GeoDataFrame(df, geometry=geom_series, crs="EPSG:4326")
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        return gdf if not gdf.empty else None
    except Exception as e:
        print(msg(lang, "error", f"GeoDataFrame conversion failed: {e}"))
        return None


# ── RAM Check ─────────────────────────────────────────────────────────────────

def is_ram_ok() -> bool:
    try:
        m = psutil.virtual_memory()
        return m.percent < RAM_LIMIT_PCT and m.available >= RAM_FREE_GB * 1024**3
    except Exception:
        return True


# ── Column Name Sanitizer ─────────────────────────────────────────────────────

def sanitize_col_name(name: str, max_len: int = 64) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)[:max_len]


def prepare_for_shp(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Truncate column names to 10 chars for Shapefile compatibility."""
    rename_map = {}
    seen = set()
    for col in gdf.columns:
        if col == "geometry":
            continue
        short = col[:10]
        while short in seen:
            short = short[:9] + str(len(seen) % 10)
        seen.add(short)
        rename_map[col] = short
    return gdf.rename(columns=rename_map)


# ── Export Helpers ────────────────────────────────────────────────────────────

def _next_part_path(base_path: Path, ext: str, part: int) -> Path:
    """Return path like prefix_part2.geojson"""
    stem = base_path.stem
    # Strip previous _partN suffix if present
    stem = re.sub(r"_part\d+$", "", stem)
    return base_path.parent / f"{stem}_part{part}{ext}"


def export_geojson(gdf: gpd.GeoDataFrame, path: Path, lang: str):
    limit = FILE_SPLIT_GB * 1024 ** 3
    part = 2
    target = path
    # If file already exists and is large, find next free part
    while target.exists() and target.stat().st_size >= limit:
        target = _next_part_path(path, path.suffix, part)
        print(msg(lang, "geojson_split", target.name))
        part += 1
    gdf.to_file(str(target), driver="GeoJSON", engine="pyogrio")
    print(msg(lang, "export_done", target))


def export_gpkg(gdf: gpd.GeoDataFrame, path: Path, layer: str, lang: str):
    gdf.to_file(str(path), driver="GPKG", layer=layer, engine="pyogrio")
    print(msg(lang, "export_done", path))


def export_shp(gdf: gpd.GeoDataFrame, shp_dir: Path, prefix: str, lang: str):
    shp_dir.mkdir(parents=True, exist_ok=True)
    limit = FILE_SPLIT_GB * 1024 ** 3
    part = 2
    target = shp_dir / f"{prefix}.shp"
    while target.exists():
        shp_size = target.stat().st_size
        dbf = target.with_suffix(".dbf")
        dbf_size = dbf.stat().st_size if dbf.exists() else 0
        if shp_size >= limit or dbf_size >= limit:
            clean_prefix = re.sub(r"_part\d+$", "", prefix)
            target = shp_dir / f"{clean_prefix}_part{part}.shp"
            print(msg(lang, "shp_split", target.name))
            part += 1
        else:
            break
    out = prepare_for_shp(gdf)
    print(msg(lang, "col_truncated"))
    try:
        out.to_file(str(target), driver="ESRI Shapefile", engine="pyogrio")
        print(msg(lang, "export_done", target))
    except Exception as e:
        print(msg(lang, "error", f"SHP export failed: {e}"))


def export_parquet(gdf: gpd.GeoDataFrame, path: Path, lang: str):
    gdf.to_parquet(str(path))
    print(msg(lang, "export_done", path))


# ── Main Export Dispatcher ────────────────────────────────────────────────────

def export_gdf(
    gdf: gpd.GeoDataFrame,
    out_dir: Path,
    prefix: str,
    formats: list[str],
    lang: str,
):
    """Split by geometry type and export each group to requested formats."""
    for geom_name, geom_types in GEOM_GROUPS.items():
        mask = gdf.geometry.geom_type.isin(geom_types)
        sub = gdf[mask].copy()
        if sub.empty:
            print(msg(lang, "skip_empty", geom_name))
            continue

        print(msg(lang, "exporting", geom_name, len(sub)))
        group_dir = out_dir / geom_name
        group_dir.mkdir(parents=True, exist_ok=True)
        file_prefix = f"{prefix}_{geom_name}"

        if "geojson" in formats:
            export_geojson(sub, group_dir / f"{file_prefix}.geojson", lang)

        if "gpkg" in formats:
            export_gpkg(sub, group_dir / f"{file_prefix}.gpkg", file_prefix, lang)

        if "parquet" in formats:
            export_parquet(sub, group_dir / f"{file_prefix}.parquet", lang)

        if "shp" in formats:
            export_shp(sub, group_dir / "shp", file_prefix, lang)


# ── Pipeline Entry Point ──────────────────────────────────────────────────────

def run(
    bbox: tuple,
    themes: list[str] | None,
    formats: list[str],
    lang: str,
    output_dir: Path,
    version: str | None,
    disk_mode: bool,
):
    print(msg(lang, "connecting"))
    con = setup_duckdb(disk_mode=disk_mode)

    if not version:
        version = get_latest_version(con, lang)
    else:
        print(msg(lang, "version_found", version))

    selected_themes = themes or list(THEMES.keys())

    for theme in selected_themes:
        for type_ in THEMES.get(theme, []):
            print()
            print(msg(lang, "querying", theme, type_, bbox))

            query = build_query(version, theme, type_, bbox)
            gdf = fetch_to_gdf(con, query, lang)

            if gdf is None:
                print(msg(lang, "no_data", theme, type_))
                continue

            print(msg(lang, "row_count", len(gdf)))

            if not is_ram_ok():
                m = psutil.virtual_memory()
                print(msg(lang, "ram_warn", m.percent))

            type_dir = output_dir / version / theme / type_
            type_dir.mkdir(parents=True, exist_ok=True)

            prefix = f"{theme}_{type_}"
            export_gdf(gdf, type_dir, prefix, formats, lang)

            del gdf
            gc.collect()

    con.close()
    print(msg(lang, "done", output_dir))


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_bbox(s: str) -> tuple:
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be: min_lon,min_lat,max_lon,max_lat")
    return tuple(parts)


def main():
    p = argparse.ArgumentParser(
        description="OvertureMaps DuckDB Extractor — bbox → GeoJSON / GPKG / SHP / Parquet"
    )
    p.add_argument(
        "--bbox", required=True, type=parse_bbox,
        help="min_lon,min_lat,max_lon,max_lat  e.g. 28.974,41.035,28.982,41.040"
    )
    p.add_argument(
        "--themes", default="all",
        help="Comma-separated themes or 'all'. Choices: " + ",".join(THEMES.keys())
    )
    p.add_argument(
        "--formats", default="geojson,gpkg,shp,parquet",
        help="Comma-separated export formats (geojson,gpkg,shp,parquet)"
    )
    p.add_argument("--lang",    default="en", choices=["en", "tr"])
    p.add_argument("--version", default=None, help="Override Overture release version")
    p.add_argument("--disk",    action="store_true", help="Use disk-spill mode (DuckDB temp dir)")
    p.add_argument(
        "--output", default=None,
        help="Output directory (default: ./overturemaps/output)"
    )
    args = p.parse_args()

    themes  = None if args.themes == "all" else [t.strip() for t in args.themes.split(",")]
    formats = [f.strip().lower() for f in args.formats.split(",")]
    out_dir = Path(args.output) if args.output else Path(__file__).parent / "output"

    run(
        bbox=args.bbox,
        themes=themes,
        formats=formats,
        lang=args.lang,
        output_dir=out_dir,
        version=args.version,
        disk_mode=args.disk,
    )


if __name__ == "__main__":
    main()
