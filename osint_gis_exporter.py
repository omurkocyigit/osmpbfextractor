import os
import osmium
import json
import sqlite3
import subprocess
import tempfile
import pandas as pd
import geopandas as gpd
from shapely import wkt
import gc
import warnings
import re
import shutil
import psutil
import time

# GDAL ve Bellek Ayarları
os.environ['GDAL_CACHEMAX'] = '128'
os.environ['OGR_SQLITE_CACHE'] = '64'
os.environ['OGR_SQLITE_SYNCHRONOUS'] = 'OFF'
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio")

RAM_FLUSH_THRESHOLD_PERCENT = 80
RAM_CHECK_EVERY_N_RECORDS   = 10000
MIN_RECORDS_BEFORE_FLUSH    = 20000

OSMIUM_DOCKER_IMAGE = "stefda/osmium-tool"
DOCKER_SIZE_THRESHOLD_MB = 500  # Bu boyutun üzerindeki PBF dosyaları otomatik Docker moduna geçer

ALL_EXPECTED_COLS = [
    'osm_id', 'osm_type', 'name', 'category', 'sub_cat', 'admin_level',
    'version', 'timestamp', 'user', 'changeset', 'tags',
    'operator', 'ref', 'substance', 'plant_source', 'voltage',
    'industrial', 'communication', 'telecom', 'capacity', 'resource',
    'access', 'security', 'frequency', 'height', 'strat_level'
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "osm_data")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "export_config.json")
OUTPUT_DIR = os.path.join(DATA_DIR, "gis_outputs")

MSG = {
    "en": {"start": "\n=== STEP 3: OSINT GIS EXPORTER ===\n", "success": "\n=== SUCCESS: EXPORT COMPLETED ===\n"},
    "tr": {"start": "\n=== 3. ADIM: OSINT GIS EXPORTER ===\n", "success": "\n=== MÜKEMMEL: TÜM VERİLER ÇIKARILDI ===\n"}
}

OSINT_TARGET_TAGS = {
    "industrial": ["oil_well", "gas_well", "oil", "well", "refinery", "mine", "biogas_plant", "chemical", "works", "petroleum"],
    "power": ["plant", "generator", "substation", "line", "minor_line", "cable", "transformer", "tower", "switch", "insulator", "storage_batteries", "converter"],
    "military": ["base", "airfield", "barracks", "bunker", "checkpoint", "danger_area", "range", "training_area", "naval_base", "trench", "radar", "intelligence", "security_post", "nuclear_weapons_facility"],
    "telecom": ["data_center", "exchange", "connection_point", "line", "tower", "mast", "satellite_station", "antenna", "wireless"],
    "man_made": ["communications_tower", "mast", "water_tower", "storage_tank", "gasometer", "pipeline", "bunker", "radar", "monitoring_station", "submarine_cable_landing", "petroleum_refinery", "shipyard", "mineshaft", "hydrogen_tank", "antenna", "satellite_dish", "water_works", "wastewater_plant"],
    "amenity": ["police", "prison", "courthouse", "embassy", "fire_station", "hospital", "townhall", "bank", "university", "fuel", "charging_station", "consulate", "customs"],
    "office": ["government", "diplomatic", "telecommunication", "energy", "ngo", "lawyer", "security", "intelligence"],
    "landuse": ["residential", "industrial", "commercial", "military", "institutional", "cemetery", "reservoir", "forest", "quarry", "port", "logistics"],
    "building": ["government", "hospital", "industrial", "train_station", "bunker", "ruins", "warehouse", "data_center", "diplomatic", "security"],
    "boundary": ["administrative", "maritime", "political", "disputed", "protected_area", "national_park"],
    "place": ["city", "town", "village", "hamlet", "suburb", "neighbourhood", "island", "islet"],
    "highway": ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "track", "construction"],
    "aeroway": ["aerodrome", "helipad", "heliport", "runway", "taxiway", "apron", "hangar", "navigationaid"],
    "railway": ["station", "yard", "junction", "rail", "subway", "tram", "light_rail"],
    "waterway": ["river", "stream", "canal", "drain", "ditch", "dam", "lock", "waterfall"],
    "natural": ["water", "coastline", "bay", "beach", "spring", "peak", "volcano", "cliff", "ridge", "glacier"],
    "harbour": ["port", "terminal", "quay", "marina", "dock", "yes"],
    "barrier": ["border_control", "city_wall", "fence", "military_checkpoint", "toll_booth", "block", "security_fence"],
    "emergency": ["ambulance_station", "siren", "bunker", "disaster_response", "water_rescue", "control_centre"],
    "route": ["pipeline", "power"],
    "shop": ["supermarket", "mall", "pharmacy", "electronics", "hardware", "convenience"],
    "tourism": ["hotel", "museum", "viewpoint", "attraction", "information", "gallery"],
    "leisure": ["park", "stadium", "sports_centre", "swimming_pool", "marina", "garden"]
}


def sanitize_name(name):
    return re.sub(r'(?u)[^-\w.]', '_', str(name).strip())[:40]


def _iter_safe_lines(path, max_bytes=50 * 1024 * 1024):
    """
    Binary mode satır okuyucu. max_bytes üzerindeki satırları RAM'e yüklemeden atlar.
    json.loads() C extension'ını devasa satırlardan korur.
    """
    CHUNK = 8 * 1024 * 1024
    buf = bytearray()
    is_oversized = False
    skipped = 0

    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            pos = 0
            while pos < len(chunk):
                nl = chunk.find(b"\n", pos)
                if nl == -1:
                    if not is_oversized:
                        buf.extend(chunk[pos:])
                        if len(buf) > max_bytes:
                            is_oversized = True
                            skipped += 1
                            buf = bytearray()
                    pos = len(chunk)
                else:
                    segment = chunk[pos:nl]
                    pos = nl + 1
                    if is_oversized:
                        is_oversized = False
                        buf = bytearray()
                        continue
                    buf.extend(segment)
                    if len(buf) > max_bytes:
                        skipped += 1
                        buf = bytearray()
                        continue
                    line = bytes(buf).strip(b"\x1e\r ")
                    buf = bytearray()
                    if line:
                        try:
                            yield line.decode("utf-8", errors="replace")
                        except Exception:
                            pass

    if skipped:
        print(f"      [INFO] {skipped} aşırı büyük satır atlandı (>{max_bytes // 1024 // 1024}MB)")


def _geojson_to_wkt(geom):
    """Pure Python GeoJSON → WKT. Shapely/GEOS kullanmaz, C++ crash riski sıfır."""
    gtype = geom.get("type", "")
    coords = geom.get("coordinates")

    def _pt(c):
        return f"{c[0]} {c[1]}"

    def _ring(ring):
        return "(" + ",".join(_pt(c) for c in ring) + ")"

    try:
        if gtype == "Point":
            return f"POINT ({_pt(coords)})"
        elif gtype == "LineString":
            return "LINESTRING (" + ",".join(_pt(c) for c in coords) + ")"
        elif gtype == "MultiLineString":
            return "MULTILINESTRING (" + ",".join(_ring(ls) for ls in coords) + ")"
        elif gtype == "Polygon":
            return "POLYGON (" + ",".join(_ring(r) for r in coords) + ")"
        elif gtype == "MultiPolygon":
            polys = ",".join("(" + ",".join(_ring(r) for r in poly) + ")" for poly in coords)
            return f"MULTIPOLYGON ({polys})"
        elif gtype == "GeometryCollection":
            geoms = [_geojson_to_wkt(g) for g in geom.get("geometries", [])]
            geoms = [g for g in geoms if g]
            return ("GEOMETRYCOLLECTION (" + ",".join(geoms) + ")") if geoms else None
        else:
            return None
    except Exception:
        return None


def get_missing_subcats(tag, formats, lang):
    target_list = OSINT_TARGET_TAGS.get(tag, [])
    if not target_list:
        return "all" if not os.path.exists(os.path.join(OUTPUT_DIR, tag)) else []
    missing, exts = [], []
    if "Parquet" in formats: exts.append(".parquet")
    if "GeoPackage (GPKG)" in formats: exts.append(".gpkg")
    if "SQLite" in formats: exts.append(".db")
    if "Shapefile (SHP)" in formats: exts.append(".shp")
    if "GeoJSON" in formats: exts.append(".geojson")
    for sc in target_list:
        p = os.path.join(OUTPUT_DIR, tag, sanitize_name(sc))
        if not os.path.exists(p):
            missing.append(sc)
            continue
        f_exts = set()
        for f in os.listdir(p):
            if '.' in f:
                try:
                    if os.path.getsize(os.path.join(p, f)) > 1024:
                        f_exts.add(f[f.rfind('.'):])
                except OSError:
                    pass
        if not any(e in f_exts for e in exts):
            missing.append(sc)
    return missing


def save_temp_batch(records, tag, batch_id, pbf_name=""):
    """JSONL mimarisi: her batch ayrı bir dosyaya yazılır, merge fازında birleştirilir."""
    if not records:
        return
    try:
        df = pd.DataFrame(records)
        for c in ALL_EXPECTED_COLS:
            if c not in df.columns:
                df[c] = ""
        df = df.fillna("").astype(str)
        pbf_tag = sanitize_name(pbf_name.replace(".pbf", "").replace(".geojsonseq", ""))
        for sc in df['sub_cat'].unique():
            sd = os.path.join(OUTPUT_DIR, tag, sanitize_name(sc), "temp_parts")
            os.makedirs(sd, exist_ok=True)
            subset = df[df['sub_cat'] == sc]
            for grp in subset['geom_group'].unique():
                final_sub = subset[subset['geom_group'] == grp].drop(columns=['geom_group'])
                out_path = os.path.join(sd, f"{sanitize_name(sc)}_{grp}_{pbf_tag}_b{batch_id}.jsonl")
                final_sub.to_json(out_path, orient='records', lines=True)
    except Exception as e:
        print(f"  [Flush Hatası] {e}")
    finally:
        if 'df' in locals():
            del df


# =============================================================================
# DOCKER EXPORT MODU: C++ crash'e karşı tam güvenli yol
# Python hiçbir zaman osmium C++ kodunu doğrudan çağırmaz.
# osmium export Docker içinde çalışır, Python hazır dosyayı okur.
# =============================================================================

def _create_osmium_export_config():
    """osmium export için OSM attribute'larını dahil eden config dosyası oluşturur."""
    config = {
        "attributes": {
            "type": True,
            "id": True,
            "version": True,
            "timestamp": True,
            "changeset": True,
            "uid": True,
            "user": True
        }
    }
    cfg_path = os.path.join(DATA_DIR, ".osmium_export_cfg.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return cfg_path


def export_pbf_to_geojsonseq(pbf_path):
    """
    Docker üzerinden osmium export çalıştırır.
    PBF → GeoJSON Sequence (satır başına bir feature).
    Python tarafında hiç osmium C++ kodu çalışmaz → crash imkânsız.
    Çıktı dosyası işlendikten sonra silinmeli (disk tasarrufu için).
    """
    abs_data_dir = os.path.abspath(DATA_DIR)
    pbf_name = os.path.basename(pbf_path)
    out_name = pbf_name.replace(".pbf", ".geojsonseq")
    out_path = os.path.join(DATA_DIR, out_name)

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        print(f"      [Cache] {out_name} zaten mevcut.")
        return out_path

    cfg_path = _create_osmium_export_config()
    cfg_name = os.path.basename(cfg_path)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{abs_data_dir}:/data",
        OSMIUM_DOCKER_IMAGE,
        "osmium", "export",
        f"/data/{pbf_name}",
        "-f", "geojsonseq",
        "--config", f"/data/{cfg_name}",
        "-o", f"/data/{out_name}",
        "--overwrite"
    ]
    print(f"      [Docker Export] {pbf_name} → {out_name} (uzun sürebilir)...")
    try:
        subprocess.run(cmd, check=True, timeout=7200)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        print("      [Docker Export] Çıktı dosyası oluşturulamadı.")
        return None
    except Exception as e:
        print(f"      [Docker Export HATA] {e}")
        return None


def stream_geojsonseq_to_jsonl(geojsonseq_path, tag, wl, pbf_name):
    """
    GeoJSON Sequence dosyasını satır satır akışlı okur.
    Her satır bir GeoJSON Feature → filtrele → JSONL batch'e yaz.
    Tüm işlemler Python'da, C++ crash riski sıfır.
    """
    if wl is not None:
        target_values = set(wl)          # [] → tüm değerleri kabul et (filtre yok)
    else:
        target_values = set(OSINT_TARGET_TAGS.get(tag, []))
    records = []
    batch_id = 1
    count = 0

    try:
        size_gb = os.path.getsize(geojsonseq_path) / (1024 ** 3)
        print(f"      [Stream] {os.path.basename(geojsonseq_path)} ({size_gb:.2f} GB) okunuyor...")
    except Exception:
        pass

    for line in _iter_safe_lines(geojsonseq_path):
        try:
            feature = json.loads(line)
        except Exception:
            continue

        props = feature.get("properties") or {}
        val = props.get(tag)
        if val is None:
            continue
        val = str(val).lower().strip()
        if target_values and val not in target_values:
            continue

        geom = feature.get("geometry")
        if not geom:
            continue

        geom_type = geom.get("type", "")
        if geom_type == "Point":
            o_type = "node"
        elif geom_type in ("MultiPolygon", "Polygon"):
            o_type = "area"
        else:
            o_type = "way"

        wkt_g = _geojson_to_wkt(geom)
        if not wkt_g:
            continue

        raw_id = props.get("@id", 0)
        try:
            osm_id = int(raw_id)
        except Exception:
            osm_id = 0

        rec = {
            "osm_id": osm_id,
            "osm_type": o_type,
            "name": props.get("name", props.get("name:en", "Unknown")),
            "category": tag,
            "sub_cat": val,
            "admin_level": props.get("admin_level", ""),
            "version": str(props.get("@version", "")),
            "timestamp": str(props.get("@timestamp", "")),
            "user": str(props.get("@user", "unknown")),
            "changeset": str(props.get("@changeset", "")),
            "tags": json.dumps(
                {k: v for k, v in props.items() if not k.startswith("@")},
                ensure_ascii=False
            ),
            "geometry_wkt": wkt_g,
            "geom_group": "points" if o_type == "node" else ("polygons" if o_type == "area" else "lines"),
            "operator": props.get("operator", ""),
            "ref": props.get("ref", ""),
            "substance": props.get("substance", ""),
            "plant_source": props.get("plant:source", props.get("generator:source", "")),
            "voltage": props.get("voltage", ""),
            "industrial": props.get("industrial", ""),
            "communication": props.get("communication", ""),
            "telecom": props.get("telecom", ""),
            "capacity": props.get("capacity", ""),
            "resource": props.get("resource", ""),
            "access": props.get("access", ""),
            "security": props.get("security", ""),
            "frequency": props.get("frequency", ""),
            "height": props.get("height", ""),
            "strat_level": props.get("strat_level", props.get("level", "")),
        }
        records.append(rec)
        count += 1

        if count % 100000 == 0:
            print(f"      ... {count} obje işlendi ...")

        if len(records) >= 20000 or (len(records) > 5000 and psutil.virtual_memory().percent > 80):
            save_temp_batch(records, tag, batch_id, pbf_name)
            records.clear()
            batch_id += 1

    if records:
        save_temp_batch(records, tag, batch_id, pbf_name)
        records.clear()

    print(f"      Toplam: {count} obje işlendi.")


# =============================================================================
# PYOSMIUM MODU: Hızlı yol (küçük dosyalar için)
# =============================================================================

class AdvancedOsintHandler(osmium.SimpleHandler):
    def __init__(self, key, formats, lang, whitelist=None, pbf_name=""):
        super().__init__()
        self.key, self.formats, self.lang, self.whitelist, self.pbf_name = key, formats, lang, whitelist, pbf_name
        self.records, self.fab, self.count, self.b_id = [], osmium.geom.WKTFactory(), 0, 1

    def check_flush(self):
        if len(self.records) >= 20000 or (len(self.records) > 5000 and psutil.virtual_memory().percent > 80):
            save_temp_batch(self.records, self.key, self.b_id, self.pbf_name)
            self.records.clear()
            self.b_id += 1

    def process(self, obj, o_type):
        try:
            if self.key in obj.tags:
                val = obj.tags.get(self.key)
                if self.whitelist is not None:
                    if self.whitelist and val not in self.whitelist:
                        return
                else:
                    if OSINT_TARGET_TAGS.get(self.key) and val not in OSINT_TARGET_TAGS[self.key]:
                        return
                try:
                    if o_type == 'node':
                        wkt_g = self.fab.create_point(obj)
                    elif o_type == 'area':
                        wkt_g = self.fab.create_multipolygon(obj)
                    else:
                        if len(obj.nodes) < 2:
                            return
                        wkt_g = self.fab.create_linestring(obj)
                except Exception:
                    return
                tags = obj.tags
                try:
                    ver, ts, usr, chg = obj.version, str(obj.timestamp), obj.user, obj.changeset
                except Exception:
                    ver, ts, usr, chg = 0, "", "unknown", 0
                extra = {
                    "operator": tags.get("operator", ""), "ref": tags.get("ref", ""),
                    "substance": tags.get("substance", ""),
                    "plant_source": tags.get("plant:source", tags.get("generator:source", "")),
                    "voltage": tags.get("voltage", ""), "industrial": tags.get("industrial", ""),
                    "communication": tags.get("communication", ""), "telecom": tags.get("telecom", ""),
                    "capacity": tags.get("capacity", ""), "resource": tags.get("resource", ""),
                    "access": tags.get("access", ""), "security": tags.get("security", ""),
                    "frequency": tags.get("frequency", ""), "height": tags.get("height", ""),
                    "strat_level": tags.get("strat_level", tags.get("level", ""))
                }
                res = {
                    "osm_id": obj.id, "osm_type": o_type,
                    "name": tags.get('name', tags.get('name:en', 'Unknown')),
                    "category": self.key, "sub_cat": str(val).lower().strip(),
                    "admin_level": tags.get('admin_level', ''),
                    "version": ver, "timestamp": ts, "user": usr, "changeset": chg,
                    "tags": json.dumps({t.k: t.v for t in tags}, ensure_ascii=False),
                    "geometry_wkt": wkt_g,
                    "geom_group": 'points' if o_type == 'node' else ('polygons' if o_type == 'area' else 'lines')
                }
                res.update(extra)
                self.records.append(res)
                self.count += 1
                if self.count % 100000 == 0:
                    print(f"      ... {self.count} obje işlendi ...")
                self.check_flush()
        except Exception:
            pass

    def node(self, n): self.process(n, 'node')
    def area(self, a): self.process(a, 'area')
    def way(self, w):
        if not w.is_closed():
            self.process(w, 'way')


def _apply_pyosmium(pbf, t, fmts, lang, wl):
    """Pyosmium ile PBF okur. sparse_file_array index kullanır."""
    h = AdvancedOsintHandler(t, fmts, lang, whitelist=wl, pbf_name=os.path.basename(pbf))
    idx_dir = os.path.join(DATA_DIR, ".idx_cache")
    os.makedirs(idx_dir, exist_ok=True)
    tmp_idx = os.path.join(idx_dir, f"{t}_{os.getpid()}.idx").replace("\\", "/")
    try:
        h.apply_file(pbf, locations=True, idx=f"sparse_file_array,{tmp_idx}")
    except Exception as e:
        print(f"      -> [UYARI] pyosmium hatası: {e}")
    finally:
        try:
            if os.path.exists(tmp_idx):
                os.remove(tmp_idx)
        except Exception:
            pass
    if h.records:
        save_temp_batch(h.records, t, h.b_id, pbf_name=os.path.basename(pbf))
    h.records.clear()
    del h
    gc.collect()


# =============================================================================
# MERGE FAZ: JSONL → Nihai Formatlar
# =============================================================================

def merge_and_export_final(tag, formats, lang):
    """Faz 2: Tüm JSONL dosyaları okunup nihai formatlara dönüştürülür."""
    td = os.path.join(OUTPUT_DIR, tag)
    if not os.path.exists(td):
        return
    for scf in os.listdir(td):
        sc_dir = os.path.join(td, scf)
        tp_dir = os.path.join(sc_dir, "temp_parts")
        if not os.path.isdir(tp_dir):
            continue
        t_files = [f for f in os.listdir(tp_dir) if f.endswith(".jsonl") or f.endswith(".parquet")]
        if not t_files:
            continue

        prefixes = {f[:f.rfind('_b')] for f in t_files if '_b' in f}

        for pre in prefixes:
            parts = [f for f in t_files if f.startswith(pre + "_b")]
            print(f"      -> [İşleniyor] {tag}/{scf} | {pre} ({len(parts)} parça)")
            base = os.path.join(sc_dir, pre)

            e_ids = set()
            try:
                pq_c = base + ".parquet"
                if os.path.exists(pq_c):
                    if os.path.isdir(pq_c):
                        for p in os.listdir(pq_c):
                            e_ids.update(pd.read_parquet(os.path.join(pq_c, p), columns=['osm_id'])['osm_id'].astype('int64').values)
                    else:
                        e_ids.update(pd.read_parquet(pq_c, columns=['osm_id'])['osm_id'].astype('int64').values)
            except Exception:
                pass

            all_ok = True
            b_size = 4 if len(parts) > 50 else 8

            for i in range(0, len(parts), b_size):
                if psutil.virtual_memory().percent > 88:
                    gc.collect()
                    time.sleep(2)
                    if psutil.virtual_memory().percent > 92:
                        print(f"      ! [RAM] %{psutil.virtual_memory().percent:.0f} - batch atlanıyor ({i})")
                        all_ok = False
                        continue

                dfs = []
                for p in parts[i:i + b_size]:
                    try:
                        p_path = os.path.join(tp_dir, p)
                        tmp = pd.read_json(p_path, orient='records', lines=True) if p.endswith(".jsonl") else pd.read_parquet(p_path)
                        if tmp.empty:
                            continue
                        for c in ALL_EXPECTED_COLS:
                            if c not in tmp.columns:
                                tmp[c] = ""
                        tmp = tmp.astype(str)
                        dfs.append(tmp)
                    except Exception as e:
                        print(f"      ! [JSONL Okuma] {p}: {e}")

                if not dfs:
                    continue

                try:
                    bdf = pd.concat(dfs, ignore_index=True)
                    del dfs
                    if e_ids:
                        bdf = bdf[~bdf['osm_id'].astype('int64').isin(e_ids)]
                    if bdf.empty:
                        continue
                    bdf.drop_duplicates(subset=['osm_id', 'osm_type'], inplace=True)

                    try:
                        bgdf = gpd.GeoDataFrame(bdf, geometry=gpd.GeoSeries.from_wkt(bdf['geometry_wkt']), crs="EPSG:4326")
                    except Exception:
                        bdf['geometry'] = bdf['geometry_wkt'].apply(lambda x: wkt.loads(x) if x else None)
                        bgdf = gpd.GeoDataFrame(bdf, geometry='geometry', crs="EPSG:4326")

                    bgdf.drop(columns=['geometry_wkt'], inplace=True, errors='ignore')
                    bgdf = bgdf[bgdf.geometry.notnull() & bgdf.geometry.is_valid & ~bgdf.geometry.is_empty]
                    del bdf
                except Exception as e:
                    print(f"      ! [Geometri Hatası] {e}")
                    all_ok = False
                    continue

                if "SQLite" in formats:
                    try:
                        dbf = base + ".db"
                        exists = os.path.exists(dbf) and os.path.getsize(dbf) > 0
                        with sqlite3.connect(dbf) as conn:
                            tdf = pd.DataFrame(bgdf.drop(columns='geometry'))
                            tdf['geometry_wkt'] = bgdf.geometry.to_wkt()
                            tdf.to_sql('features', conn, if_exists="append" if exists else "replace", index=False, chunksize=5000)
                    except Exception as e:
                        print(f"      ! [SQLite HATA] {e}")
                        all_ok = False

                if "Parquet" in formats:
                    try:
                        pf = base + ".parquet"
                        if os.path.exists(pf):
                            if not os.path.isdir(pf):
                                old = pd.read_parquet(pf)
                                os.remove(pf)
                                os.makedirs(pf)
                                old.to_parquet(os.path.join(pf, "base.parquet"))
                            bgdf.to_parquet(os.path.join(pf, f"batch_{i}.parquet"))
                        else:
                            bgdf.to_parquet(pf, compression="snappy")
                    except Exception as e:
                        print(f"      ! [Parquet HATA] {e}")
                        all_ok = False

                if "GeoJSON" in formats or "Shapefile (SHP)" in formats:
                    _write_heavy_formats(bgdf, base, formats, pre, sc_dir)

                del bgdf
                gc.collect()

            if all_ok:
                for p in parts:
                    try:
                        os.remove(os.path.join(tp_dir, p))
                    except Exception:
                        pass

        try:
            if not os.listdir(tp_dir):
                shutil.rmtree(tp_dir, ignore_errors=True)
        except Exception:
            pass


def _write_heavy_formats(gdf, base, formats, prefix, sc_dir):
    chunk_size = 100000
    for start in range(0, len(gdf), chunk_size):
        chunk = gdf.iloc[start:start + chunk_size].copy()
        if "GeoJSON" in formats:
            try:
                chunk.to_file(base + ".geojson", driver="GeoJSON", engine="pyogrio",
                              mode="a" if os.path.exists(base + ".geojson") else "w")
            except Exception as e:
                print(f"      ! [GeoJSON HATA] {e}")
        if "Shapefile (SHP)" in formats:
            try:
                sd = os.path.join(sc_dir, "shp")
                os.makedirs(sd, exist_ok=True)
                chunk.rename(columns={
                    'admin_level': 'adm_lvl', 'timestamp': 'ts', 'changeset': 'chgset',
                    'plant_source': 'p_src', 'industrial': 'indus',
                    'communication': 'comms', 'telecom': 'telcom'
                }, inplace=True)
                chunk.columns = [col[:10] for col in chunk.columns]
                p_idx = 1
                while (os.path.exists(os.path.join(sd, f"{prefix}_v{p_idx}.shp")) and
                       os.path.getsize(os.path.join(sd, f"{prefix}_v{p_idx}.shp")) > 1.4 * 1024 ** 3):
                    p_idx += 1
                shp_path = os.path.join(sd, f"{prefix}_v{p_idx}.shp")
                chunk.to_file(shp_path, driver="ESRI Shapefile", engine="pyogrio",
                              mode="a" if os.path.exists(shp_path) else "w")
            except Exception as e:
                print(f"      ! [SHP HATA] {e}")
        del chunk
        gc.collect()


# =============================================================================
# TAG İŞLEME: Mod seçimi burada yapılır
# =============================================================================

def process_tag(t, fmts, lang, mode, use_docker=False, subtags_override=None):
    """
    Bir tag için tam işleme döngüsü.
    use_docker=True → Docker osmium export (crash'e karşı %100 güvenli)
    use_docker=False → pyosmium apply_file (hızlı, küçük dosyalar için)
    subtags_override: None → OSINT_TARGET_TAGS whitelist kullan
                      []   → tüm değerleri çıkar (filtre yok)
                      ["x","y"] → sadece bu değerleri çıkar
    """
    merge_and_export_final(t, fmts, lang)

    # subtags_override verilmişse standart skip mantığını atla
    if subtags_override is None:
        if mode == "standard" and os.path.exists(os.path.join(OUTPUT_DIR, t)) and os.listdir(os.path.join(OUTPUT_DIR, t)):
            return
        m = get_missing_subcats(t, fmts, lang)
        if isinstance(m, list) and not m:
            return
        wl = m if isinstance(m, list) else None
    else:
        # [] = tümü, ["x","y"] = belirli değerler
        wl = subtags_override
        if wl:
            print(f"  [Subtag Filtresi] {t} → {wl}")
        else:
            print(f"  [Subtag Filtresi] {t} → TÜM DEĞERLER")

    if wl and os.path.exists(os.path.join(OUTPUT_DIR, t)):
        swl = [sanitize_name(x) for x in wl]
        for sc in os.listdir(os.path.join(OUTPUT_DIR, t)):
            if sc not in swl:
                shutil.rmtree(os.path.join(OUTPUT_DIR, t, sc, "temp_parts"), ignore_errors=True)

    MIN_PBF_KB = 100  # Bu boyutun altındaki dosyalar boş sayılır, atlanır

    part_files = sorted([
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if f.startswith(f"filtered_{t}_part") and f.endswith(".pbf") and "islenmis" not in f
        and os.path.getsize(os.path.join(DATA_DIR, f)) >= MIN_PBF_KB * 1024
    ])

    base_pbf = os.path.join(DATA_DIR, f"filtered_{t}.pbf")

    if part_files:
        # Parçalar mevcutsa her zaman parçalar üzerinden işle (base varsa da atla)
        pbf_files = part_files
        if os.path.exists(base_pbf):
            base_kb = os.path.getsize(base_pbf) / 1024
            print(f"  [Parça Modu] {len(part_files)} parça bulundu — base ({base_kb:.0f} KB) atlanıyor.")
    else:
        # Parça yok, base dosyasını kullan (boyut kontrolü ile)
        pbf_files = []
        if os.path.exists(base_pbf):
            if os.path.getsize(base_pbf) >= MIN_PBF_KB * 1024:
                pbf_files.append(base_pbf)
            else:
                print(f"  [UYARI] {os.path.basename(base_pbf)} çok küçük ({os.path.getsize(base_pbf)/1024:.1f} KB), atlanıyor.")

    if not pbf_files:
        print(f"  [UYARI] {t} için PBF dosyası bulunamadı.")
        return
    pbf_files.sort()

    mode_label = "Docker Export" if use_docker else "pyosmium"
    print(f"  [Mod: {mode_label}] {t} → {len(pbf_files)} dosya")

    for pbf in pbf_files:
        print(f"\n[Çıkarılıyor] {os.path.basename(pbf)}...")

        pbf_size_mb = os.path.getsize(pbf) / (1024 ** 2)
        pbf_use_docker = use_docker or (pbf_size_mb > DOCKER_SIZE_THRESHOLD_MB)
        if pbf_use_docker and not use_docker:
            print(f"      [Auto-Docker] {pbf_size_mb:.0f} MB > {DOCKER_SIZE_THRESHOLD_MB} MB eşiği → Docker modu")

        if pbf_use_docker:
            geojsonseq = export_pbf_to_geojsonseq(pbf)
            if geojsonseq:
                stream_geojsonseq_to_jsonl(geojsonseq, t, wl, os.path.basename(pbf))
                try:
                    os.remove(geojsonseq)
                    print(f"      [Temizlendi] {os.path.basename(geojsonseq)}")
                except Exception:
                    pass
            else:
                print(f"      [Fallback] Docker export başarısız, pyosmium deneniyor...")
                _apply_pyosmium(pbf, t, fmts, lang, wl)
        else:
            _apply_pyosmium(pbf, t, fmts, lang, wl)

        gc.collect()

    merge_and_export_final(t, fmts, lang)


# =============================================================================
# ANA FONKSİYON
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=None,
                        help="Tek bir tag işle (örn: landuse)")
    parser.add_argument("--mode", choices=["pyosmium", "docker"], default="pyosmium",
                        help="pyosmium: hızlı | docker: crash'e karşı güvenli")
    parser.add_argument("--subtags", default=None,
                        help="Alt tag filtresi: 'all' → tümü çıkar | 'forest,residential' → belirli değerler")
    cli_args, _ = parser.parse_known_args()

    if not os.path.exists(CONFIG_PATH):
        print(f"[HATA] {CONFIG_PATH} bulunamadı.")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    tags = cfg.get("tags", [])
    fmts = cfg.get("formats", [])
    lang = cfg.get("lang", "en")
    mode = cfg.get("skip_mode", "standard")

    if cli_args.tag:
        tags = [cli_args.tag]

    # --subtags çözümleme
    subtags_override = None
    if cli_args.subtags is not None:
        raw = cli_args.subtags.strip()
        if raw.lower() == "all":
            subtags_override = []          # boş liste = filtre yok, tümü çıkar
        else:
            subtags_override = [s.strip() for s in raw.split(",") if s.strip()]

    use_docker = cli_args.mode == "docker"

    print(MSG[lang]["start"])
    if use_docker:
        print("  [Docker Export Modu] C++ crash riski sıfır, her veri işlenecek.\n")

    for t in tags:
        process_tag(t, fmts, lang, mode, use_docker=use_docker, subtags_override=subtags_override)

    print(MSG[lang]["success"])


if __name__ == "__main__":
    main()
