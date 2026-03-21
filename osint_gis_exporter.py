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

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "osm_data") 
CONFIG_PATH = os.path.join(SCRIPT_DIR, "export_config.json")
OUTPUT_DIR = os.path.join(DATA_DIR, "gis_outputs")

SHP_CHUNK_SIZE = 1000000 # Parçaları birleştirme eşiği (Her 1M kayıtta bir dosya işlemi yapılır)

MSG = {
    "en": {
        "start": "\n=============================================\n  STEP 3: OSINT GIS EXPORTER\n=============================================\n",
        "err_conf": "Error: export_config.json not found.",
        "skip": "\n[Skipped] '{}' already exists. Moving to next...",
        "not_in_dict": "\n[Info] '{}' is not in OSINT dict, all data will be extracted.",
        "process": "\n[Processing] {}...",
        "warn_temp": "\n[Warning] Incomplete temp files found for '{}'. Cleaning and restarting...",
        "ram_flush": "\n      >>> RAM Limit reached! Flushing {} records to temp file (Part {})...",
        "ram_load": "      ... {} objects loaded to RAM ...",
        "crit_mem": "\n[CRITICAL] {} is too large. PBF Node Cache exceeded RAM.",
        "disk_cache": "\n[INFO] Large PBF detected ({:.1f} GB). Switching to Disk-Based Node Cache (Dense File Array) to prevent RAM explosion...",
        "fallback_mem": "\n[WARNING] Memory error occurred. Attempting fallback to Disk-Based Cache...",
        "flush_final": "\n      >>> Flushing final {} records to temp storage (Part {})...",
        "merge_start": "\n   >>> Merging temporary chunks for {} via Streaming...",
        "merge_log": "      -> [Merge] Folder: {}/{}/ | Object Group: {} ({} chunks processing...)",
        "success": "\n=============================================\nSUCCESS: EXPORT COMPLETED!\nCheck '{}' folder.\n============================================="
    },
    "tr": {
        "start": "\n=============================================\n  3. ADIM: OSINT GIS EXPORTER (NİHAİ ÇIKARIM)\n=============================================\n",
        "err_conf": "Hata: export_config.json bulunamadı.",
        "skip": "\n[Atlandı] '{}' katmanı zaten mevcut. Sonraki hedefe geçiliyor...",
        "not_in_dict": "\n[Bilgi] '{}' özel OSINT sözlüğünde yok, içindeki tüm veriler çekilecek.",
        "process": "\n[İşleniyor] {} süzülüyor...",
        "warn_temp": "\n[Uyarı] '{}' için yarım kalmış geçici dosyalar bulundu. Klasör silinip baştan başlanıyor...",
        "ram_flush": "\n      >>> RAM limiti aşıldı! {} kayıt geçici Parquet dosyasına yazılıyor (Part {})...",
        "ram_load": "      ... {} obje RAM'e alındı ...",
        "crit_mem": "\n[KRİTİK UYARI] {} çok büyük. PBF Node Cache RAM'i aştı.",
        "disk_cache": "\n[BİLGİ] Devasa PBF dosyası tespit edildi ({:.1f} GB). RAM patlamasını kesin önlemek için Disk Tabanlı Önbellek (Dense File Array) sistemine geçiliyor...",
        "fallback_mem": "\n[UYARI] Bellek hatası alındı. Sistem kendini Disk Tabanlı Önbellek ile yeniden başlatmaya çalışıyor...",
        "flush_final": "\n      >>> Kalan son {} kayıt geçici Parquet'ye yazılıyor (Part {})...",
        "merge_start": "\n   >>> {} için geçici parçalar Streaming (Akış) mantığıyla birleştiriliyor...",
        "merge_log": "      -> [Hiyerarşi] Klasör: {}/{}/ | Obje Grubu: {} ({} parça dosyaya işleniyor...)",
        "success": "\n=============================================\nMÜKEMMEL! TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI!\nÇıktılarınız '{}' klasöründe sizi bekliyor.\n============================================="
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
    # BOMBA 2 FIX: MAX_PATH çökmesini engellemek için isim uzunluğu 40 karakter ile sınırlandırıldı.
    clean = re.sub(r'(?u)[^-\w.]', '_', str(name).strip())
    return clean[:40]

def is_already_processed(tag, lang):
    tag_dir = os.path.join(OUTPUT_DIR, tag)
    if os.path.exists(tag_dir):
        has_temp = any("temp_parts" in dirs for root, dirs, files in os.walk(tag_dir))
        if has_temp:
            print(MSG[lang]["warn_temp"].format(tag))
            shutil.rmtree(tag_dir)
            return False
        if len(os.listdir(tag_dir)) > 0:
            return True
    return False

def save_temp_batch(records, tag, batch_id):
    if not records: return

    df = pd.DataFrame(records)
    
    # BOMBA 3 FIX: Veritabanlarında "Schema Mismatch" (Şema Kayması) engellemek için 
    # sütun tipleri tartışmaya kapalı şekilde String (Metin) olarak zorlandı.
    str_cols = ['osm_id', 'osm_type', 'name', 'category', 'sub_cat', 'admin_level']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    df['geometry'] = df['geometry_wkt'].apply(wkt.loads)
    df.drop('geometry_wkt', axis=1, inplace=True)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    
    del df
    gc.collect()
    
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

    for subcat_folder in os.listdir(tag_dir):
        subcat_dir = os.path.join(tag_dir, subcat_folder)
        if not os.path.isdir(subcat_dir): continue
        
        temp_dir = os.path.join(subcat_dir, "temp_parts")
        if not os.path.exists(temp_dir): continue

        # Sadece parquet parçalarını al (part_N.parquet formatında)
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

            shp_part_idx = 1
            gj_part_idx = 1
            
            # RAM patlamasın diye parçaları SHP_CHUNK_SIZE limitine göre (Varsayılan 1M kayıt) gruplayarak birleştiriyoruz.
            # batch_size, 200k'lık kaç parçanın birleştirileceğini belirler.
            batch_size = max(1, SHP_CHUNK_SIZE // 200000)
            
            for i in range(0, len(parts), batch_size):
                batch_parts = parts[i:i+batch_size]
                gdfs = []
                for p in batch_parts:
                    gdfs.append(gpd.read_parquet(os.path.join(temp_dir, p)))
                
                batch_gdf = pd.concat(gdfs, ignore_index=True)
                del gdfs
                gc.collect()
                
                is_first_batch = (i == 0)

                # 1. GeoPackage (GPKG) - Sınır yok, tek dosyada birleştirilir
                if "GeoPackage (GPKG)" in formats:
                    mode = "w" if is_first_batch else "a"
                    batch_gdf.to_file(f"{base_filename}.gpkg", driver="GPKG", layer=prefix, engine="pyogrio", mode=mode)

                # 2. SQLite - Sınır yok, tek veritabanı
                if "SQLite" in formats:
                    conn = sqlite3.connect(f"{base_filename}.db")
                    temp_df = pd.DataFrame(batch_gdf.drop(columns='geometry'))
                    temp_df['geometry_wkt'] = batch_gdf['geometry'].apply(lambda x: x.wkt)
                    # BOMBA 1 FIX: chunksize=1000 eklendi
                    temp_df.to_sql('features', conn, if_exists='replace' if is_first_batch else 'append', index=False, chunksize=1000)
                    conn.close()
                    del temp_df

                # 3. Parquet - Küçükse tek dosya, çok büyükse parçalı dizin olarak bırakılır
                if "Parquet" in formats:
                    pq_path = f"{base_filename}.parquet"
                    if len(parts) <= batch_size:
                        if os.path.isdir(pq_path): shutil.rmtree(pq_path)
                        batch_gdf.to_parquet(pq_path)
                    else:
                        if os.path.isfile(pq_path): os.remove(pq_path)
                        os.makedirs(pq_path, exist_ok=True)
                        batch_gdf.to_parquet(os.path.join(pq_path, f"part_{i//batch_size}.parquet"))

                # 4. Shapefile (SHP) - 4GB Sınırı gözetilerek birleştirilir
                if "Shapefile (SHP)" in formats:
                    shp_dir = os.path.join(subcat_dir, "shp")
                    os.makedirs(shp_dir, exist_ok=True)
                    subset_shp = batch_gdf.copy()
                    subset_shp.columns = [col[:10] for col in subset_shp.columns] 
                    
                    while True:
                        if len(parts) <= batch_size:
                            c_shp = os.path.join(shp_dir, f"{prefix}.shp")
                        else:
                            c_shp = os.path.join(shp_dir, f"{prefix}_part{shp_part_idx}.shp")
                        
                        # .shp veya .dbf 3.5GB'ı geçtiyse yeni parta geç (Emniyet sınırı)
                        dbf_p = c_shp.replace(".shp", ".dbf")
                        if os.path.exists(c_shp) and (os.path.getsize(c_shp) > 3.5 * 1024**3 or (os.path.exists(dbf_p) and os.path.getsize(dbf_p) > 3.5 * 1024**3)):
                            shp_part_idx += 1
                            continue
                        break
                    
                    try:
                        subset_shp.to_file(c_shp, driver="ESRI Shapefile", engine="pyogrio", mode="a" if os.path.exists(c_shp) else "w")
                    except Exception: pass
                    del subset_shp

                # 5. GeoJSON - Boyut sınırı ve performans için parçalı birleştirilir
                if "GeoJSON" in formats:
                    if len(parts) <= batch_size:
                        gj_path = f"{base_filename}.geojson"
                    else:
                        gj_path = f"{base_filename}_part{gj_part_idx}.geojson"
                    
                    batch_gdf.to_file(gj_path, driver="GeoJSON", engine="pyogrio")
                    gj_part_idx += 1

                del batch_gdf
                gc.collect()

        shutil.rmtree(temp_dir)

class AdvancedOsintHandler(osmium.SimpleHandler):
    def __init__(self, target_key, formats, lang):
        super(AdvancedOsintHandler, self).__init__()
        self.target_key = target_key
        self.formats = formats
        self.lang = lang
        self.records = []
        self.wkbfab = osmium.geom.WKTFactory()
        
        self.islenen_kayit = 0
        self.batch_id = 1
        self.BATCH_LIMIT = 200000 

    def check_memory_and_flush(self):
        if len(self.records) >= self.BATCH_LIMIT:
            print(MSG[self.lang]["ram_flush"].format(self.BATCH_LIMIT, self.batch_id))
            save_temp_batch(self.records, self.target_key, self.batch_id)
            self.records.clear()
            gc.collect()
            self.batch_id += 1

    def process_element(self, tags, osm_id, osm_type, geom_wkt):
        if self.target_key in tags:
            tag_value = tags.get(self.target_key)
            target_list = OSINT_TARGET_TAGS.get(self.target_key)
            
            if target_list is not None and len(target_list) > 0:
                if tag_value not in target_list: return
            
            name = tags.get('name', tags.get('name:en', 'Unknown Object'))
            admin_level = tags.get('admin_level', '')
            safe_sub_cat = str(tag_value).lower().strip() if tag_value else 'other'
            
            self.records.append({
                "osm_id": osm_id, "osm_type": osm_type, "name": name,
                "category": self.target_key, "sub_cat": safe_sub_cat,
                "admin_level": admin_level, "geometry_wkt": geom_wkt
            })
            
            self.islenen_kayit += 1
            if self.islenen_kayit % 100000 == 0:
                print(MSG[self.lang]["ram_load"].format(self.islenen_kayit))
                
            self.check_memory_and_flush()

    def node(self, n):
        if self.target_key in n.tags:
            try:
                wkt_geom = self.wkbfab.create_point(n)
                self.process_element(n.tags, n.id, 'node', wkt_geom)
            except: pass

    def area(self, a):
        if self.target_key in a.tags:
            try:
                wkt_geom = self.wkbfab.create_multipolygon(a)
                self.process_element(a.tags, a.id, 'area', wkt_geom)
            except: pass

    def way(self, w):
        if self.target_key in w.tags and not w.is_closed():
            try:
                wkt_geom = self.wkbfab.create_linestring(w)
                self.process_element(w.tags, w.id, 'way', wkt_geom)
            except: pass

def main():
    if not os.path.exists(CONFIG_PATH):
        print("Error: export_config.json not found.")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    target_tags = config.get("tags", [])
    selected_formats = config.get("formats", [])
    lang = config.get("lang", "en")
    cache_type = config.get("cache", "auto")

    print(MSG[lang]["start"])

    for tag in target_tags:
        if is_already_processed(tag, lang):
            print(MSG[lang]["skip"].format(tag))
            continue

        if tag not in OSINT_TARGET_TAGS:
            print(MSG[lang]["not_in_dict"].format(tag))
            
        pbf_file = os.path.join(DATA_DIR, f"filtered_{tag}.pbf")
        
        if not os.path.exists(pbf_file):
            continue
            
        print(MSG[lang]["process"].format(pbf_file))
        handler = AdvancedOsintHandler(tag, selected_formats, lang)
        
        # --- CACHE STRATEGY (RAM vs DISK) ---
        pbf_size_gb = os.path.getsize(pbf_file) / (1024 * 1024 * 1024)
        
        # Determine the effective cache method
        use_disk = False
        if cache_type == "disk":
            use_disk = True
        elif cache_type == "ram":
            use_disk = False
        else: # auto
            if pbf_size_gb > 1.5:
                print(MSG[lang]["disk_cache"].format(pbf_size_gb))
                use_disk = True

        try:
            if use_disk:
                handler.apply_file(pbf_file, locations=True, idx='dense_file_array')
            else:
                try:
                    handler.apply_file(pbf_file, locations=True)
                except MemoryError:
                    print(MSG[lang]["crit_mem"].format(tag))
                    print(MSG[lang]["fallback_mem"])
                    # Cleanup and retry with disk
                    handler.records.clear()
                    gc.collect()
                    handler.apply_file(pbf_file, locations=True, idx='dense_file_array')
        except Exception as e:
            print(f"\n[ERROR] {e}")
        # ------------------------------------

        if handler.records:
            print(MSG[lang]["flush_final"].format(len(handler.records), handler.batch_id))
            save_temp_batch(handler.records, tag, handler.batch_id)

        handler.records.clear()
        del handler
        gc.collect()

        merge_and_export_final(tag, selected_formats, lang)

    print(MSG[lang]["success"].format(OUTPUT_DIR))

if __name__ == "__main__":
    main()