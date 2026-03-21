# 🌍 OSM PBF Extractor - Zero-Touch ETL Pipeline

🇬🇧 English | [🇹🇷 Türkçe](#türkçe-dokümantasyon)

An advanced, cross-platform (Windows/Linux) Data Engineering and ETL (Extract, Transform, Load) pipeline designed to securely and efficiently process massive OpenStreetMap (OSM) `.pbf` files. 

It splits planetary-scale data into categories, separates geometries (Points, Lines, Polygons), and handles system memory smartly using Map-Reduce batching and streaming techniques to avoid RAM crashes on massive layers like `highway` or `building`.

## ✨ Key Features
* **Smart Merging & 4GB Limit Handling:** (New!) Instead of fragmented small files, the pipeline now intelligently consolidates chunks into larger files. It respects the **4GB limit** for Shapefiles and GeoJSON, automatically creating new parts (`_part1.shp`, `_part2.shp`) only when necessary.
* **Unified Exports:** GeoPackage, SQLite, and Parquet formats are merged into single files per category whenever possible to avoid file clutter.
* **Zero-Touch Execution:** Just point to the source `.pbf`, and the pipeline autonomously handles Docker mounts, Osmium filtering, and GeoPandas exports within its own directory.
* **Interactive Launcher:** Includes a `quick_run.py` script with drag-and-drop support and pre-defined extraction profiles (Strategic, Infrastructure, etc.).
* **Enterprise-Grade Stability:** Built-in hardware and OS-level protections against Windows `MAX_PATH` length limits, SQLite "Too Many SQL Variables" errors, and GeoPackage schema mismatch issues.
* **Smart Memory Management (Map-Reduce):** Prevents `MemoryError`. RAM is flushed to temporary files every 200,000 records. Once parsing is done, it merges them in **1,000,000 record batches** to keep memory usage safe and efficient.
* **Hierarchical Outputs:** Generates deep categorized folders (e.g., `osm_data/gis_outputs/boundary/administrative/administrative_points.gpkg`).
* **Resumable (Crash-Proof):** If interrupted, the script cleans up temporary broken files and resumes right where it left off.

## ⚙️ Prerequisites
1. **Python 3.8+** *(Tested on Python 3.13)*
2. **Docker:** Required for `stefda/osmium-tool` dependency isolation.
3. **Python Packages:**
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow
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

---

# 🇹🇷 Türkçe Dokümantasyon

Devasa boyutlardaki OpenStreetMap (OSM) `.pbf` verilerini güvenli, hızlı ve sistem belleğini çökertmeden işlemek için tasarlanmış ETL boru hattıdır.

Verileri kategorilerine böler, her katmanı hiyerarşik olarak noktalar (points), çizgiler (lines) ve poligonlar olarak ayırır. `highway` veya `building` gibi milyarlarca kayıt barındıran katmanlarda sistemin kilitlenmesini önlemek için "Map-Reduce" mantığıyla özel bellek yönetimi uygular.

## ✨ Temel Özellikler
* **Akıllı Birleştirme ve 4 GB Limit Yönetimi:** (Yeni!) Artık veriler çok sayıda küçük parça yerine, limitler dahilinde birleştirilerek sunulur. **Shapefile ve GeoJSON** formatları için 4 GB sınırı takip edilir; sadece dosya bu boyutu aşarsa yeni parça (`_part1.shp`, `_part2.shp`) oluşturulur.
* **Derli Toplu Çıktılar:** GeoPackage, SQLite ve Parquet formatları, dosya kirliliğini önlemek için kategori başına mümkün olduğunca tek bir dosyada birleştirilir.
* **Sıfır Temaslı Çalışma:** Sadece ana `.pbf` dosyasının yolunu verin; arka planda Docker'ı ayağa kaldırır, veriyi böler ve GIS formatlarına kendi klasörü içinde dönüştürür.
* **Etkileşimli Başlatıcı:** Sürükle-bırak destekli `quick_run.py` betiği içerir.
* **Kurumsal Seviye Kararlılık (Enterprise-Grade):** Windows `MAX_PATH` uzunluk sınırı, SQLite "Too Many SQL Variables" çökmesi ve GeoPackage şema kaymalarına karşı tam koruma sağlar.
* **Akıllı Bellek Yönetimi (Map-Reduce):** RAM şişmesini önler. Veriler 200 bin kayıtta bir geçici dosyalara yazılır ve ardından **1 milyonluk bloklar** halinde RAM dostu bir şekilde birleştirilir.
* **Hiyerarşik Dosyalama:** Veriler `osm_data/gis_outputs/boundary/administrative/administrative_points.gpkg` şeklinde derinlemesine klasörlenir.
* **Kaldığı Yerden Devam Edebilme:** Yarım kalan geçici dosyaları temizler ve hatasız şekilde kaldığı yerden devam eder.

## ⚙️ Gereksinimler
1. **Python 3.8+**
2. **Docker:** `stefda/osmium-tool` imajı üzerinden işlemler yürütülür.
3. **Gerekli Python Kütüphaneleri:**
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow
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
