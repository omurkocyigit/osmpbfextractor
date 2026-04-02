import osmium
import os
import json
import sqlite3
import pandas as pd
import geopandas as gpd
from shapely import wkt
import math
import gc
import warnings
import re
import shutil
import psutil

# RAM izleme sabitleri
RAM_FLUSH_THRESHOLD_PERCENT = 85   # RAM %85'i geçerse flush
RAM_FLUSH_THRESHOLD_GB      = 5.0  # Boş RAM 5GB altına inerse flush
RAM_CHECK_EVERY_N_RECORDS   = 10000 # Her 10k kayıtta bir RAM kontrol et

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "osm_data") 
CONFIG_PATH = os.path.join(SCRIPT_DIR, "export_config.json")
OUTPUT_DIR = os.path.join(DATA_DIR, "gis_outputs")

SHP_CHUNK_SIZE = 1000000 

MSG = {
    "en": {
        "start": "\n=============================================\n  STEP 3: OSINT GIS EXPORTER\n=============================================\n",
        "err_conf": "Error: export_config.json not found.",
        "skip": "\n[Skipped] '{}' already exists with complete output files.",
        "not_in_dict": "\n[Info] '{}' is not in OSINT dict, all data will be extracted.",
        "process": "\n[Processing] {}...",
        "warn_temp": "\n[Warning] Incomplete or split files found for '{}'. Cleaning and restarting...",
        "ram_flush": "\n      >>> RAM Limit reached! Flushing {} records to temp file (Part {})...",
        "ram_load": "      ... {} objects loaded to RAM ...",
        "crit_mem": "\n[CRITICAL] {} is too large. PBF Node Cache exceeded RAM.",
        "disk_cache": "\n[INFO] Large PBF detected ({:.1f} GB). Switching to Disk-Based Node Cache...",
        "fallback_mem": "\n[WARNING] Memory error occurred. Attempting fallback...",
        "flush_final": "\n      >>> Flushing final {} records to temp storage (Part {})...",
        "merge_start": "\n   >>> Merging temporary chunks for {} via Streaming...",
        "merge_log": "      -> [Merge] Folder: {}/{}/ | Object Group: {} ({} chunks processing...)",
        "success": "\n=============================================\nSUCCESS: EXPORT COMPLETED!\nCheck '{}' folder.\n=============================================",
        "partial_success": "\n=============================================\nPROCESS COMPLETED WITH ERRORS!\nSome layers failed: {}\nCheck logs and retry.\n=============================================",
        "ram_pressure": "\n      >>> RAM pressure detected! Flushing {} records early to disk (Part {})..."
    },
    "tr": {
        "start": "\n=============================================\n  3. ADIM: OSINT GIS EXPORTER (NİHAİ ÇIKARIM)\n=============================================\n",
        "err_conf": "Hata: export_config.json bulunamadı.",
        "skip": "\n[Atlandı] '{}' katmanı zaten eksiksiz tamamlanmış görünüyor.",
        "not_in_dict": "\n[Bilgi] '{}' özel OSINT sözlüğünde yok, içindeki tüm veriler çekilecek.",
        "process": "\n[İşleniyor] {} süzülüyor...",
        "warn_temp": "\n[Uyarı] '{}' için yarım kalmış veya parçalı dosyalar bulundu. Klasör silinip baştan başlanıyor...",
        "ram_flush": "\n      >>> RAM limiti aşıldı! {} kayıt geçici Parquet dosyasına yazılıyor (Part {})...",
        "ram_load": "      ... {} obje RAM'e alındı ...",
        "crit_mem": "\n[KRİTİK UYARI] {} çok büyük. PBF Node Cache RAM'i aştı.",
        "disk_cache": "\n[BİLGİ] Devasa PBF dosyası tespit edildi ({:.1f} GB). Disk Tabanlı Önbellek sistemine geçiliyor...",
        "fallback_mem": "\n[UYARI] Bellek hatası alındı. Sistem dayanıklı modda yeniden deniyor...",
        "flush_final": "\n      >>> Kalan son {} kayıt geçici Parquet'ye yazılıyor (Part {})...",
        "merge_start": "\n   >>> {} için geçici parçalar Streaming (Akış) mantığıyla birleştiriliyor...",
        "merge_log": "      -> [Hiyerarşi] Klasör: {}/{}/ | Obje Grubu: {} ({} parça dosyaya işleniyor...)",
        "success": "\n=============================================\nMÜKEMMEL! TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI!\nÇıktılarınız '{}' klasöründe sizi bekliyor.\n=============================================",
        "partial_success": "\n=============================================\nİŞLEMLER HATALARLA TAMAMLANDI!\nŞu katmanlar başarısız oldu: {}\nLütfen PBF dosyalarını ve hataları kontrol edin.\n=============================================",
        "ram_pressure": "\n      >>> RAM baskısı tespit edildi! {} kayıt erken diske yazılıyor (Part {})..."
    }
}

OSINT_TARGET_TAGS = {
    "boundary": ["administrative", "maritime", "political", "disputed", "protected_area", "national_park"],
    "place": ["city", "town", "village", "hamlet", "suburb", "neighbourhood", "island", "islet", "sea", "ocean", "strait"],
    "military": [],
    "amenity": ["police", "prison", "courthouse", "embassy", "fire_station", "ranger_station", "hospital", "townhall", "shelter"],
    "power": ["plant", "generator", "substation", "line", "tower", "transformer"],
    "telecom": ["data_center", "exchange", "connection_point", "line"],
    "highway": ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "track"], 
    "aeroway": ["aerodrome", "helipad", "runway", "taxiway", "apron", "hangar", "navigationaid"],
    "railway": ["station", "yard", "junction", "rail", "subway", "tram", "light_rail"],
    "waterway": ["river", "stream", "canal", "drain", "ditch", "dam", "lock", "waterfall", "weir"],
    "natural": ["water", "coastline", "bay", "strait", "cape", "beach", "reef", "spring", "peak", "volcano", "cliff", "ridge", "hill", "saddle", "valley", "cave_entrance", "wood", "scrub", "glacier"],
    "harbour": [],
    "barrier": ["border_control", "city_wall", "fence", "military_checkpoint", "toll_booth", "block", "retaining_wall", "ditch"],
    "man_made": ["communications_tower", "mast", "water_tower", "storage_tank", "works", "pipeline", "bunker", "camp", "bridge", "pier", "breakwater"],
    "landuse": ["residential", "industrial", "commercial", "military", "institutional", "cemetery", "reservoir", "forest", "quarry"],
    "office": ["government", "diplomatic", "telecommunication", "energy"],
    "building": ["government", "bunker", "ruins", "hospital", "industrial", "train_station", "bridge"],
    "emergency": ["ambulance_station", "siren", "bunker", "disaster_response", "water_rescue"]
}

def sanitize_name(name):
    clean = re.sub(r'(?u)[^-\w.]', '_', str(name).strip())
    return clean[:40]

def is_ram_critical():
    try:
        mem = psutil.virtual_memory()
        return (mem.percent >= RAM_FLUSH_THRESHOLD_PERCENT or
                mem.available < RAM_FLUSH_THRESHOLD_GB * 1024 ** 3)
    except:
        return False

def is_already_processed(tag, formats, lang):
    tag_dir = os.path.join(OUTPUT_DIR, tag)
    if not os.path.exists(tag_dir): return False

    for root, dirs, files in os.walk(tag_dir):
        if "temp_parts" in dirs: return False

    expected_extensions = []
    if "Parquet" in formats: expected_extensions.append(".parquet")
    if "GeoPackage (GPKG)" in formats: expected_extensions.append(".gpkg")
    if "SQLite" in formats: expected_extensions.append(".db")
    if "Shapefile (SHP)" in formats: expected_extensions.append(".shp")
    if "GeoJSON" in formats: expected_extensions.append(".geojson")

    found_extensions = set()
    for root, dirs, files in os.walk(tag_dir):
        for f in files:
            f_path = os.path.join(root, f)
            for ext in expected_extensions:
                if f.endswith(ext) and os.path.getsize(f_path) > 0:
                    if not ("_part" in f and ext in [".parquet", ".gpkg", ".db"]):
                        found_extensions.add(ext)

    for ext in expected_extensions:
        if ext not in found_extensions: return False
    
    return True

def save_temp_batch(records, tag, batch_id):
    if not records: return
    df = pd.DataFrame(records)
    str_cols = ['osm_id', 'osm_type', 'name', 'category', 'sub_cat', 'admin_level']
    for col in str_cols:
        if col in df.columns: df[col] = df[col].fillna("").astype(str)
    df['geometry'] = df['geometry_wkt'].apply(wkt.loads)
    df.drop('geometry_wkt', axis=1, inplace=True)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    
    def get_geom_group(geom_type):
        if 'Point' in geom_type: return 'points'
        elif 'Line' in geom_type: return 'lines'
        elif 'Polygon' in geom_type: return 'polygons'
        return 'other'
        
    gdf['geom_group'] = gdf.geom_type.apply(get_geom_group)
    
    for sub_cat in gdf['sub_cat'].unique():
        safe_subcat = sanitize_name(sub_cat)
        subcat_dir = os.path.join(OUTPUT_DIR, tag, safe_subcat)
        temp_dir = os.path.join(subcat_dir, "temp_parts")
        os.makedirs(temp_dir, exist_ok=True)
        
        subcat_gdf = gdf[gdf['sub_cat'] == sub_cat]
        for group in subcat_gdf['geom_group'].unique():
            subset = subcat_gdf[subcat_gdf['geom_group'] == group].drop(columns=['geom_group'])
            if subset.empty: continue
            temp_path = os.path.join(temp_dir, f"{safe_subcat}_{group}_part{batch_id}.parquet")
            subset.to_parquet(temp_path)
    del gdf
    gc.collect()

def merge_and_export_final(tag, formats, lang):
    tag_dir = os.path.join(OUTPUT_DIR, tag)
    if not os.path.exists(tag_dir): return
    print(MSG[lang]["merge_start"].format(tag))
    all_merged_successfully = True

    for subcat_folder in os.listdir(tag_dir):
        subcat_dir = os.path.join(tag_dir, subcat_folder)
        if not os.path.isdir(subcat_dir): continue
        temp_dir = os.path.join(subcat_dir, "temp_parts")
        if not os.path.exists(temp_dir): continue
        temp_files = [f for f in os.listdir(temp_dir) if f.endswith(".parquet")]
        if not temp_files: continue

        prefixes = set()
        for f in temp_files:
            match = re.match(r"(.+)_part\d+\.parquet", f)
            if match: prefixes.add(match.group(1))

        for prefix in prefixes:
            parts = [f for f in temp_files if f.startswith(f"{prefix}_part")]
            # Numerik sıralama (part1, part2, part10 vb. doğru sıralansın diye)
            parts.sort(key=lambda x: int(re.search(r'_part(\d+)\.parquet', x).group(1)))
            print(MSG[lang]["merge_log"].format(tag, subcat_folder, prefix, len(parts)))
            base_filename = os.path.join(subcat_dir, prefix)

            try:
                gdfs = [gpd.read_parquet(os.path.join(temp_dir, p)) for p in parts]
                full_gdf = pd.concat(gdfs, ignore_index=True)
                del gdfs
                gc.collect()

                if "Parquet" in formats: full_gdf.to_parquet(f"{base_filename}.parquet")
                if "GeoPackage (GPKG)" in formats: full_gdf.to_file(f"{base_filename}.gpkg", driver="GPKG", layer=prefix, engine="pyogrio")
                if "SQLite" in formats:
                    conn = sqlite3.connect(f"{base_filename}.db")
                    temp_df = pd.DataFrame(full_gdf.drop(columns='geometry'))
                    temp_df['geometry_wkt'] = full_gdf['geometry'].apply(lambda x: x.wkt)
                    temp_df.to_sql('features', conn, if_exists='replace', index=False, chunksize=1000)
                    conn.close()

                if "Shapefile (SHP)" in formats:
                    shp_dir = os.path.join(subcat_dir, "shp")
                    os.makedirs(shp_dir, exist_ok=True)
                    subset_shp = full_gdf.copy()
                    subset_shp.columns = [col[:10] for col in subset_shp.columns] 
                    is_large = len(subset_shp) > 500000 or (len(subset_shp) > 200000 and "polygon" in prefix)
                    
                    if is_large:
                        print(f"      [!] {prefix} looks large, splitting SHP proactively...")
                        chunk_size = 400000
                        for idx, start in enumerate(range(0, len(subset_shp), chunk_size)):
                            subset_shp.iloc[start:start+chunk_size].to_file(os.path.join(shp_dir, f"{prefix}_part{idx+1}.shp"), driver="ESRI Shapefile", engine="pyogrio")
                    else:
                        try:
                            subset_shp.to_file(os.path.join(shp_dir, f"{prefix}.shp"), driver="ESRI Shapefile", engine="pyogrio")
                        except:
                            for idx, start in enumerate(range(0, len(subset_shp), 300000)):
                                subset_shp.iloc[start:start+300000].to_file(os.path.join(shp_dir, f"{prefix}_part{idx+1}.shp"), driver="ESRI Shapefile", engine="pyogrio")
                    del subset_shp

                if "GeoJSON" in formats:
                    try: full_gdf.to_file(f"{base_filename}.geojson", driver="GeoJSON", engine="pyogrio")
                    except:
                        for idx, start in enumerate(range(0, len(full_gdf), 400000)):
                            full_gdf.iloc[start:start+400000].to_file(f"{base_filename}_part{idx+1}.geojson", driver="GeoJSON", engine="pyogrio")
                del full_gdf
                gc.collect()
            except Exception as e:
                print(f"      [!] Critical error merging {prefix}: {e}")
                all_merged_successfully = False

        if all_merged_successfully:
            try: shutil.rmtree(temp_dir)
            except: pass

class AdvancedOsintHandler(osmium.SimpleHandler):
    def __init__(self, target_key, formats, lang):
        super(AdvancedOsintHandler, self).__init__()
        self.target_key, self.formats, self.lang = target_key, formats, lang
        self.records, self.wkbfab = [], osmium.geom.WKTFactory()
        self.islenen_kayit, self.batch_id, self.BATCH_LIMIT, self._ram_check_ctr = 0, 1, 200000, 0

    def check_memory_and_flush(self):
        do_flush = len(self.records) >= self.BATCH_LIMIT
        if not do_flush:
            self._ram_check_ctr += 1
            if self._ram_check_ctr >= RAM_CHECK_EVERY_N_RECORDS:
                self._ram_check_ctr = 0
                if self.records and is_ram_critical():
                    print(MSG[self.lang]["ram_pressure"].format(len(self.records), self.batch_id))
                    do_flush = True
        if do_flush:
            print(MSG[self.lang]["ram_flush"].format(len(self.records), self.batch_id))
            try:
                save_temp_batch(self.records, self.target_key, self.batch_id)
                self.records.clear()
                self.batch_id += 1
            except Exception as e: print(f"      [!] Batch save error: {e}")
            gc.collect()
            self._ram_check_ctr = 0

    def process_element(self, tags, osm_id, osm_type, geom_wkt):
        try:
            if self.target_key in tags:
                tag_value = tags.get(self.target_key)
                target_list = OSINT_TARGET_TAGS.get(self.target_key)
                if target_list and tag_value not in target_list: return
                name = tags.get('name', tags.get('name:en', 'Unknown Object'))
                self.records.append({
                    "osm_id": osm_id, "osm_type": osm_type, "name": name,
                    "category": self.target_key, "sub_cat": str(tag_value).lower().strip() if tag_value else 'other',
                    "admin_level": tags.get('admin_level', ''), "geometry_wkt": geom_wkt
                })
                self.islenen_kayit += 1
                if self.islenen_kayit % 100000 == 0: print(MSG[self.lang]["ram_load"].format(self.islenen_kayit))
                self.check_memory_and_flush()
        except: pass

    def node(self, n):
        if self.target_key in n.tags:
            try: self.process_element(n.tags, n.id, 'node', self.wkbfab.create_point(n))
            except: pass
    def area(self, a):
        if self.target_key in a.tags:
            try: self.process_element(a.tags, a.id, 'area', self.wkbfab.create_multipolygon(a))
            except: pass
    def way(self, w):
        if self.target_key in w.tags and not w.is_closed():
            try: self.process_element(w.tags, w.id, 'way', self.wkbfab.create_linestring(w))
            except: pass

def main():
    if not os.path.exists(CONFIG_PATH): return
    with open(CONFIG_PATH, "r", encoding="utf-8") as f: config = json.load(f)
    target_tags, selected_formats, lang, cache_type = config.get("tags", []), config.get("formats", []), config.get("lang", "en"), config.get("cache", "auto")
    print(MSG[lang]["start"])
    failed_tags = []
    
    for tag in target_tags:
        if is_already_processed(tag, selected_formats, lang):
            print(MSG[lang]["skip"].format(tag)); continue
        tag_dir = os.path.join(OUTPUT_DIR, tag)
        if os.path.exists(tag_dir):
            print(MSG[lang]["warn_temp"].format(tag))
            try: shutil.rmtree(tag_dir)
            except: pass
        pbf_file = os.path.join(DATA_DIR, f"filtered_{tag}.pbf")
        if not os.path.exists(pbf_file): continue
        print(MSG[lang]["process"].format(pbf_file))
        handler = AdvancedOsintHandler(tag, selected_formats, lang)
        tmp_file = os.path.join(DATA_DIR, f"nodes_{tag}.tmp")
        pbf_size_gb = os.path.getsize(pbf_file) / (1024**3)
        
        # Windows Stability Strategy
        if pbf_size_gb > 10: strategies = [f'dense_file_array,{tmp_file}', 'flex_mem']
        else: strategies = ['flex_mem', f'sparse_file_array,{tmp_file}']

        success = False
        for strategy in strategies:
            try:
                print(f"      -> Strategy: {strategy.split(',')[0]}...")
                handler.apply_file(pbf_file, locations=True, idx=strategy)
                success = True; break
            except Exception as e:
                print(f"      [!] {strategy.split(',')[0]} failed. Cleaning up..."); gc.collect()
                if os.path.exists(tmp_file):
                    try: os.remove(tmp_file)
                    except: pass
        if not success:
            try:
                print("      -> Strategy: Final Fallback (Auto)...")
                handler.apply_file(pbf_file, locations=True)
                success = True
            except Exception as e:
                print(f"\n[ERROR] {tag} processing failed: {e}")
                failed_tags.append(tag); continue

        if handler.records:
            print(MSG[lang]["flush_final"].format(len(handler.records), handler.batch_id))
            save_temp_batch(handler.records, tag, handler.batch_id)
        handler.records.clear()
        del handler
        gc.collect()
        merge_and_export_final(tag, selected_formats, lang)
        if os.path.exists(tmp_file):
            try: os.remove(tmp_file)
            except: pass

    if failed_tags: print(MSG[lang]["partial_success"].format(", ".join(failed_tags)))
    else: print(MSG[lang]["success"].format(OUTPUT_DIR))

if __name__ == "__main__":
    main()
