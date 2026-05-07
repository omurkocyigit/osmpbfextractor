import os
import subprocess
import math
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OSM_DATA_DIR = os.path.join(SCRIPT_DIR, "osm_data")
OSMIUM_DOCKER_IMAGE = "stefda/osmium-tool"
TARGET_CHUNK_SIZE_GB = 1.5   # 1.5 GB üzeri dosyalar bölünür
MIN_PART_SIZE_KB     = 100   # Bu boyutun altındaki parçalar boş (veri yok) sayılır ve silinir

ALL_TARGET_TAGS = [
    "boundary", "place", "military", "amenity", "power", "telecom",
    "highway", "aeroway", "railway", "waterway", "harbour", "barrier",
    "man_made", "landuse", "office", "building", "natural", "emergency",
    "industrial", "route"
]

def get_next_part_number(tag):
    """Bu tag için kullanılabilir bir sonraki parça numarasını döndür."""
    max_n = -1
    for f in os.listdir(OSM_DATA_DIR):
        if f.startswith(f"filtered_{tag}_part") and f.endswith(".pbf"):
            try:
                n_str = f.split(f"filtered_{tag}_part")[1].replace(".pbf", "")
                n = int(n_str)
                max_n = max(max_n, n)
            except Exception:
                pass
    return max_n + 1

def split_file(file_path, tag):
    """Verilen PBF dosyasını boylam dilimleriyle bölünür."""
    file_size_gb = os.path.getsize(file_path) / (1024 ** 3)
    num_parts = math.ceil(file_size_gb / TARGET_CHUNK_SIZE_GB)
    slice_width = 360.0 / num_parts
    abs_data_dir = os.path.abspath(OSM_DATA_DIR)
    file_name = os.path.basename(file_path)
    start_num = get_next_part_number(tag)

    print(f"\n[BÖLÜNÜYOR] {file_name} ({file_size_gb:.2f} GB) → {num_parts} parça...")

    success = True
    for i in range(num_parts):
        min_lon = -180.0 + (i * slice_width)
        max_lon = min_lon + slice_width
        bbox = f"{min_lon},-90,{max_lon},90"
        out_file = f"filtered_{tag}_part{start_num + i:03d}.pbf"
        print(f"   -> Dilim {i + 1}/{num_parts} ({min_lon:.1f}° - {max_lon:.1f}°) → {out_file}")
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{abs_data_dir}:/data",
            OSMIUM_DOCKER_IMAGE,
            "osmium", "extract",
            "-b", bbox,
            f"/data/{file_name}",
            "-o", f"/data/{out_file}",
            "--overwrite"
        ]
        out_path = os.path.join(abs_data_dir, out_file)
        try:
            subprocess.run(cmd, check=True, timeout=3600)
            # Boş parçaları temizle (veri olmayan boylamlarda osmium küçük header dosyası üretir)
            if os.path.exists(out_path):
                size_kb = os.path.getsize(out_path) / 1024
                if size_kb < MIN_PART_SIZE_KB:
                    os.remove(out_path)
                    print(f"   [Boş] {out_file} ({size_kb:.1f} KB) — bu boylam aralığında veri yok, silindi.")
        except Exception as e:
            print(f"   ! Dilim {i + 1} hatası: {e}")
            success = False

    if success:
        processed = os.path.join(OSM_DATA_DIR, f"islenmis_{file_name}")
        if os.path.exists(processed):
            os.remove(processed)
        os.rename(file_path, processed)
        print(f"✅ {file_name} başarıyla {num_parts} parçaya bölündü.")
    else:
        print(f"⚠️ {file_name} bölünürken bazı hatalar oluştu, orijinal dosya korundu.")

def check_and_split_tag(tag):
    """
    Bir tag için tüm PBF dosyalarını (base + part dosyaları dahil) kontrol eder.
    1.5 GB üzerindeki her dosyayı böler. Part dosyaları da kontrol edilir.
    """
    if not os.path.exists(OSM_DATA_DIR):
        return False

    files_to_check = []

    # Ana dosya
    base = os.path.join(OSM_DATA_DIR, f"filtered_{tag}.pbf")
    if os.path.exists(base):
        files_to_check.append(base)

    # Mevcut part dosyaları (islenmis_ olanlar hariç)
    for f in sorted(os.listdir(OSM_DATA_DIR)):
        if (f.startswith(f"filtered_{tag}_part")
                and f.endswith(".pbf")
                and "islenmis" not in f):
            files_to_check.append(os.path.join(OSM_DATA_DIR, f))

    # Mevcut boş parçaları temizle (önceki çalıştırmadan kalan 1 KB dosyalar)
    for f in sorted(os.listdir(OSM_DATA_DIR)):
        if (f.startswith(f"filtered_{tag}_part") and f.endswith(".pbf") and "islenmis" not in f):
            fp = os.path.join(OSM_DATA_DIR, f)
            size_kb = os.path.getsize(fp) / 1024
            if size_kb < MIN_PART_SIZE_KB:
                try:
                    os.remove(fp)
                    print(f"   [Temizlendi] {f} ({size_kb:.1f} KB) — boş parça silindi.")
                except Exception as e:
                    print(f"   [Silinemedi] {f}: {e}")

    did_split = False
    for fpath in files_to_check:
        if not os.path.exists(fpath):   # boş parça temizliğinde silinmiş olabilir
            continue
        size_gb = os.path.getsize(fpath) / (1024 ** 3)
        fname = os.path.basename(fpath)
        if size_gb > TARGET_CHUNK_SIZE_GB:
            split_file(fpath, tag)
            did_split = True
        else:
            print(f"  {fname} ({size_gb:.2f} GB) — boyut uygun, bolme gerekmez.")

    return did_split

def main(tags=None):
    if not os.path.exists(OSM_DATA_DIR):
        print("osm_data dizini bulunamadı.")
        return

    print(f"\n[🛠️] PBF dosyaları kontrol ediliyor (eşik: {TARGET_CHUNK_SIZE_GB} GB)...")
    tag_list = tags if tags else ALL_TARGET_TAGS
    for tag in tag_list:
        check_and_split_tag(tag)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=None, help="Sadece bu tag'ı kontrol et")
    args = parser.parse_args()
    tags = [args.tag] if args.tag else None
    main(tags)
