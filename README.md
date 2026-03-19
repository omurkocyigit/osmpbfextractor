# 🌍 OSM PBF Extractor - Zero-Touch ETL Pipeline

🇬🇧 English | [🇹🇷 Türkçe](#türkçe-dokümantasyon)

An advanced, cross-platform (Windows/Linux) Data Engineering and ETL (Extract, Transform, Load) pipeline designed to securely and efficiently process massive OpenStreetMap (OSM) `.pbf` files. 

It splits planetary-scale data into OSINT (Open-Source Intelligence) categories, separates geometries (Points, Lines, Polygons), and handles system memory smartly using Map-Reduce batching and streaming techniques to avoid RAM crashes on massive layers like `highway` or `building`.

## ✨ Key Features
* **Zero-Touch Execution:** Just point to the source `.pbf`, and the pipeline autonomously handles Docker mounts, Osmium filtering, and GeoPandas exports within its own directory.
* **Interactive Launcher:** Includes a `quick_run.py` script with drag-and-drop support and pre-defined extraction profiles (Strategic, Infrastructure, etc.).
* **Cross-Platform:** Automatically generates `.ps1` (PowerShell) for Windows and `.sh` (Bash) for Linux/macOS environments.
* **Smart Memory Management (Map-Reduce):** Prevents `MemoryError: bad allocation`. RAM is automatically flushed to temporary `.parquet` files every 200,000 records. Once parsing is done, it seamlessly merges them via streaming.
* **Shapefile 4GB Limit Bypass:** Shapefiles exceeding standard geometry/file size limits are automatically chunked (`_part1.shp`, `_part2.shp`).
* **Hierarchical Outputs:** Generates deep categorized folders (e.g., `osm_data/gis_outputs/boundary/administrative/administrative_points.gpkg`).
* **Resumable (Crash-Proof):** If interrupted, the script detects existing directories, cleans up temporary broken files, and resumes right where it left off.
* **Bilingual Logging:** Supports both English (`--lang en`) and Turkish (`--lang tr`) terminal outputs.

## ⚙️ Prerequisites
1. **Python 3.8+** *(Tests were successfully conducted on Python 3.13)*
2. **Docker:** Must be installed and the Docker Engine must be running in the background (Docker Desktop is recommended for Windows/macOS). The pipeline relies on the `stefda/osmium-tool` image to isolate C++ dependencies. 
   You can pull the required image beforehand:
   ```bash
   docker pull stefda/osmium-tool
   ```
3. **Python Packages:**
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow
   ```

## 🚀 Usage

**Option A: Interactive Quick Launcher (Recommended)**
Simply run the quick launcher. It will prompt you to drag & drop your `.pbf` file, select a language, and choose an extraction profile (Full, Strategic, Infrastructure, or Custom). No need to memorize commands.
```bash
python quick_run.py
```

**Option B: Command Line Interface (CLI)**
You can specify the exact tags to filter and the language of the logs.
```bash
# Windows Example (All tags, English logs)
python auto_runner.py --pbf "C:\pbf\sample.pbf" --tags all --lang en

# Linux Example (Specific tags, Turkish logs)
python auto_runner.py --pbf "/var/data/sample.osm.pbf" --tags military,boundary,telecom --lang tr
```

---

# 🇹🇷 Türkçe Dokümantasyon

Devasa boyutlardaki OpenStreetMap (OSM) `.pbf` verilerini güvenli, hızlı ve sistem belleğini çökertmeden işlemek için tasarlanmış platformlar arası (Windows/Linux) Veri Mühendisliği ve ETL boru hattıdır.

Verileri OSINT (Açık Kaynak İstihbaratı) kategorilerine böler, her katmanı hiyerarşik olarak noktalar (points), çizgiler (lines) ve poligonlar olarak ayırır. `highway` veya `building` gibi milyarlarca kayıt barındıran katmanlarda sistemin kilitlenmesini önlemek için "Map-Reduce" mantığıyla özel bellek yönetimi uygular.

## ✨ Temel Özellikler
* **Sıfır Temaslı Çalışma:** Sadece ana `.pbf` dosyasının yolunu verin; arka planda Docker'ı ayağa kaldırır, veriyi böler ve GIS formatlarına kendi klasörü içinde dönüştürür.
* **Etkileşimli Başlatıcı:** Sürükle-bırak destekli ve hazır veri profilleri (Stratejik, Altyapı vb.) sunan `quick_run.py` betiği içerir.
* **Çapraz Platform (Cross-Platform):** Windows için otomatik olarak PowerShell (`.ps1`), Linux/macOS için Bash (`.sh`) betikleri üretir.
* **Akıllı Bellek Yönetimi (Map-Reduce):** RAM şişmesini önler. Her 200.000 kayıtta bir bellek boşaltılarak geçici süper hızlı `.parquet` dosyalarına yazılır. PBF tamamen okunduğunda bu parçalar "Streaming" (akış) yöntemiyle RAM'i yormadan birleştirilir.
* **Shapefile 4GB Limit Koruması:** Shapefile formatının boyutsal veya satır bazlı limitlerini aşan veriler otomatik olarak `_part1`, `_part2` olarak dilimlenir.
* **Hiyerarşik Dosyalama:** Veriler `osm_data/gis_outputs/boundary/administrative/administrative_points.gpkg` şeklinde derinlemesine klasörlenerek çıkarılır.
* **Kaldığı Yerden Devam Edebilme:** Elektrik kesintisi durumunda, işlem görmüş katmanları atlar, yarım kalan geçici dosyaları temizler ve hatasız şekilde kaldığı yerden devam eder.
* **Çoklu Dil Desteği:** Terminal çıktıları için İngilizce (`--lang en`) ve Türkçe (`--lang tr`) dil seçenekleri sunar.

## ⚙️ Gereksinimler
1. **Python 3.8+** *(Testler Python 3.13 üzerinde başarıyla gerçekleştirilmiştir)*
2. **Docker:** Sisteminizde kurulu ve Docker Engine arka planda çalışır durumda olmalıdır (Windows ve macOS kullanıcıları için Docker Desktop önerilir). İşlemler C++ bağımlılıklarını izole etmek adına `stefda/osmium-tool` imajı üzerinden yürütülür. 
   Başlamadan önce ilgili Docker paketini indirmek için şu komutu çalıştırabilirsiniz:
   ```bash
   docker pull stefda/osmium-tool
   ```
3. **Gerekli Python Kütüphaneleri:**
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow
   ```

## 🚀 Kullanım

**Seçenek A: Etkileşimli Başlatıcı (Önerilen)**
Sadece hızlı başlatıcıyı çalıştırın. Size PBF dosyanızı sürükleyip bırakmanızı, dil seçmenizi ve bir veri profili (Tüm, Stratejik, Altyapı veya Özel) seçmenizi soracaktır. Komut ezberlemenize gerek kalmaz.
```bash
python quick_run.py
```

**Seçenek B: Komut Satırı (CLI)**
İster tüm etiketleri, isterseniz de sadece ihtiyacınız olanları ve log dilini belirtebilirsiniz.
```bash
# Windows Örneği (Tüm etiketler, İngilizce Loglar)
python auto_runner.py --pbf "C:\pbf\sample.pbf" --tags all --lang en

# Linux Örneği (Belirli etiketler, Türkçe Loglar)
python auto_runner.py --pbf "/var/data/sample.osm.pbf" --tags military,boundary,telecom --lang tr
```
