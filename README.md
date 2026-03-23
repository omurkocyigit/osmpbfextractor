# 🌍 OSM PBF Extractor - Zero-Touch ETL Pipeline

🇬🇧 English | [🇹🇷 Türkçe](#türkçe-dokümantasyon)

An advanced, cross-platform (Windows/Linux) Data Engineering and ETL (Extract, Transform, Load) pipeline designed to securely and efficiently process massive OpenStreetMap (OSM) `.pbf` files.

It splits planetary-scale data into categories, separates geometries (Points, Lines, Polygons), and handles system memory smartly using Map-Reduce batching and streaming techniques to avoid RAM crashes on massive layers like `highway` or `building`.

## ✨ Key Features

* **Proactive RAM Guard:** Even if RAM mode is selected, the pipeline continuously monitors memory usage via `psutil`. When RAM utilization exceeds **75%** or free RAM drops below **2 GB**, records are flushed to disk immediately — before any `MemoryError` can occur. This makes RAM mode safe even for planet-scale `.pbf` files.
* **Smart Merging & 4GB Limit Handling:** Instead of fragmented small files, the pipeline intelligently consolidates chunks into larger files. It respects the **4GB limit** for Shapefiles and GeoJSON, automatically creating new parts (`_part1.shp`, `_part2.shp`, `_part1.geojson`, …) only when necessary.
* **Unified Exports:** GeoPackage and Parquet formats are merged into single files per category to avoid file clutter. SQLite is also kept as a single database per category.
* **Zero-Touch Execution:** Just point to the source `.pbf`, and the pipeline autonomously handles Docker mounts, Osmium filtering, and GeoPandas exports within its own directory.
* **Interactive Launcher:** Includes a `quick_run.py` script with drag-and-drop support and pre-defined extraction profiles (Full OSINT, Strategic, Infrastructure, Custom).
* **Enterprise-Grade Stability:** Built-in protections against Windows `MAX_PATH` length limits, SQLite "Too Many SQL Variables" errors, and schema mismatch issues.
* **Map-Reduce Memory Management:** RAM is flushed to temporary Parquet files every 200,000 records. Once parsing is done, chunks are merged in **1,000,000 record batches** to keep memory usage safe and efficient.
* **Hierarchical Outputs:** Generates deep categorized folders (e.g., `osm_data/gis_outputs/boundary/administrative/administrative_points.gpkg`).
* **Resumable (Crash-Proof):** If interrupted, the script cleans up temporary broken files and resumes from where it left off.

## ⚙️ Prerequisites

1. **Python 3.8+** *(Tested on Python 3.13)*
2. **Docker:** Required for `stefda/osmium-tool` dependency isolation.
3. **Python Packages:**
   ```bash
   pip install -r requirements.txt
   ```
   Or manually:
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow psutil
   ```

## 🚀 Usage

**Option A: Interactive Quick Launcher (Recommended)**
```bash
python quick_run.py
```

**Option B: Command Line Interface (CLI)**
```bash
python auto_runner.py --pbf "path/to/file.pbf" --tags all --lang en
```

## 🧠 Cache Mode Selection

When running `quick_run.py`, you will be asked to choose a node cache type:

| Mode | Description | Best For |
|------|-------------|----------|
| **AUTO** *(Recommended)* | Uses DISK for files > 1.5 GB, RAM otherwise | General use |
| **RAM** | Fast in-memory node cache + proactive RAM guard | Small/medium files |
| **DISK** | Disk-based node cache (Dense File Array) | Planet-scale files |

> **Note:** Even in RAM mode, the pipeline monitors memory every 5,000 records and flushes to disk automatically if RAM pressure is detected. You will not get an out-of-memory crash.

## 📁 Output Structure

```
osm_data/gis_outputs/
└── {tag}/
    └── {sub_category}/
        ├── {prefix}.gpkg          ← Single GeoPackage (no size limit)
        ├── {prefix}.parquet       ← Single Parquet (or directory if very large)
        ├── {prefix}.db            ← Single SQLite database
        ├── {prefix}.geojson       ← GeoJSON, split at 3.8 GB
        │   {prefix}_part2.geojson
        └── shp/
            ├── {prefix}.shp       ← Shapefile, split at 3.8 GB
            └── {prefix}_part2.shp
```

---

# 🇹🇷 Türkçe Dokümantasyon

[🇬🇧 English](#-osm-pbf-extractor---zero-touch-etl-pipeline)

Devasa boyutlardaki OpenStreetMap (OSM) `.pbf` verilerini güvenli, hızlı ve sistem belleğini çökertmeden işlemek için tasarlanmış ETL boru hattıdır.

Verileri kategorilerine böler, her katmanı hiyerarşik olarak noktalar (points), çizgiler (lines) ve poligonlar olarak ayırır. `highway` veya `building` gibi milyarlarca kayıt barındıran katmanlarda sistemin kilitlenmesini önlemek için "Map-Reduce" mantığıyla özel bellek yönetimi uygular.

## ✨ Temel Özellikler

* **Proaktif RAM Koruması:** RAM modu seçilmiş olsa bile sistem, `psutil` aracılığıyla bellek kullanımını sürekli izler. RAM kullanımı **%75'i** aşarsa veya boş RAM **2 GB'ın** altına düşerse, herhangi bir `MemoryError` hatası oluşmadan kayıtlar diske yazılır. Bu sayede RAM modu, planet boyutundaki `.pbf` dosyalarında bile güvenle kullanılabilir.
* **Akıllı Birleştirme ve 4 GB Limit Yönetimi:** Artık veriler çok sayıda küçük parça yerine, limitler dahilinde birleştirilerek sunulur. **Shapefile ve GeoJSON** için 4 GB sınırı takip edilir; dosya bu boyutu aşarsa yeni parça (`_part1.shp`, `_part2.shp`, `_part1.geojson`, …) oluşturulur.
* **Derli Toplu Çıktılar:** GeoPackage ve Parquet formatları, kategori başına tek bir dosyada birleştirilir. SQLite de kategori başına tek veritabanı olarak tutulur.
* **Sıfır Temaslı Çalışma:** Sadece ana `.pbf` dosyasının yolunu verin; arka planda Docker'ı ayağa kaldırır, veriyi böler ve GIS formatlarına kendi klasörü içinde dönüştürür.
* **Etkileşimli Başlatıcı:** Sürükle-bırak destekli `quick_run.py` betiği ve hazır profiller (Tam OSINT, Stratejik, Altyapı, Özel) içerir.
* **Kurumsal Seviye Kararlılık:** Windows `MAX_PATH` uzunluk sınırı, SQLite "Too Many SQL Variables" çökmesi ve şema kaymalarına karşı tam koruma sağlar.
* **Map-Reduce Bellek Yönetimi:** Veriler 200 bin kayıtta bir geçici Parquet dosyalarına yazılır ve ardından **1 milyonluk bloklar** halinde RAM dostu bir şekilde birleştirilir.
* **Hiyerarşik Dosyalama:** Veriler `osm_data/gis_outputs/boundary/administrative/administrative_points.gpkg` şeklinde derinlemesine klasörlenir.
* **Kaldığı Yerden Devam Edebilme:** Yarım kalan geçici dosyaları temizler ve hatasız şekilde kaldığı yerden devam eder.

## ⚙️ Gereksinimler

1. **Python 3.8+**
2. **Docker:** `stefda/osmium-tool` imajı üzerinden işlemler yürütülür.
3. **Gerekli Python Kütüphaneleri:**
   ```bash
   pip install -r requirements.txt
   ```
   Ya da manuel olarak:
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow psutil
   ```

## 🚀 Kullanım

**Seçenek A: Etkileşimli Başlatıcı (Önerilen)**
```bash
python quick_run.py
```

**Seçenek B: Komut Satırı (CLI)**
```bash
python auto_runner.py --pbf "dosya/yolu.pbf" --tags all --lang tr
```

## 🧠 Önbellek (Cache) Modu Seçimi

`quick_run.py` çalıştırıldığında önbellek tipi sorulur:

| Mod | Açıklama | En İyi Kullanım |
|-----|----------|-----------------|
| **OTOMATİK** *(Önerilen)* | 1,5 GB üzeri dosyalarda DISK, altında RAM kullanır | Genel kullanım |
| **RAM** | Hızlı bellek içi önbellek + proaktif RAM koruması | Küçük/orta dosyalar |
| **DİSK** | Disk tabanlı önbellek (Dense File Array) | Planet boyutlu dosyalar |

> **Not:** RAM modunda bile sistem her 5.000 kayıtta bir belleği kontrol eder ve RAM baskısı algılanırsa otomatik olarak diske yazar. Yetersiz bellek hatası (OOM) almazsınız.

## 📁 Çıktı Yapısı

```
osm_data/gis_outputs/
└── {etiket}/
    └── {alt_kategori}/
        ├── {ön_ek}.gpkg          ← Tek GeoPackage dosyası (boyut sınırı yok)
        ├── {ön_ek}.parquet       ← Tek Parquet dosyası (veya çok büyükse dizin)
        ├── {ön_ek}.db            ← Tek SQLite veritabanı
        ├── {ön_ek}.geojson       ← GeoJSON, 3,8 GB'da bölünür
        │   {ön_ek}_part2.geojson
        └── shp/
            ├── {ön_ek}.shp       ← Shapefile, 3,8 GB'da bölünür
            └── {ön_ek}_part2.shp
```
