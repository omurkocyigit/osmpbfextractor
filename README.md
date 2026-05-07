# 🌍 OSM PBF Extractor — Zero-Crash OSINT ETL Pipeline

🇬🇧 [English](#english-documentation) | 🇹🇷 [Türkçe](#türkçe-dokümantasyon)

---

## English Documentation

A robust, cross-platform (Windows / Linux) ETL pipeline built to process **planet-scale OpenStreetMap (OSM) `.pbf` files** for OSINT and GIS intelligence workflows.

The pipeline filters raw OSM data by strategic tags (military, boundary, power, telecom, etc.), reconstructs geometries, and exports to multiple GIS formats — without crashing, regardless of input file size.

---

### ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Zero-Crash Architecture** | Each tag processed in an isolated subprocess. One crash or timeout never stops the pipeline. |
| **Dual-Mode Processing** | **pyosmium** for small files (<500 MB), **Docker osmium export** for large files — automatically selected per file. |
| **Auto PBF Splitting** | Files >1.5 GB are split into longitude slices before extraction. Empty slices (<100 KB) are discarded automatically. |
| **`--subtags all`** | Extract every OSM value under a tag, not just the built-in OSINT whitelist. |
| **PBF Validation** | Optional header or full-scan validation of filtered PBFs before processing. Corrupt files can be deleted and regenerated interactively. |
| **Orphan Cleanup** | Leftover `.geojsonseq` files from crashed runs are detected at startup and offered for cleanup or reuse as cache. |
| **24-Hour Timeout** | Per-tag subprocess timeout is 24 hours — large tags (highway, natural) process completely. |
| **RAM Guard** | Memory is monitored continuously; records are flushed to disk when RAM > 80%. No OOM crashes. |
| **Pure-Python WKT** | Geometry conversion uses a zero-dependency WKT writer — no Shapely/GEOS in the streaming path. |
| **Smart Skip** | Standard (folder exists) or Detailed (per-subtag file check) skip modes to avoid reprocessing completed data. |

---

### 🗂️ Pipeline Overview

```
quick_run.py  ──────────────────────────────────────────────┐
                                                            ▼
auto_runner.py                                              │
  [Step 0] Clean old scripts                               │
  [Step 1] Generate osint_filter.ps1 / .sh                │
  [Step 2] Run Docker osmium tags-filter (per tag)         │
  [Pre-Split] pbf_splitter.py  ←─── splits >1.5 GB PBFs   │
  [Step 3] osint_gis_exporter.py (per tag, subprocess)     │
            ├── pyosmium mode  (file < 500 MB)             │
            └── Docker export mode (file ≥ 500 MB)         │
                                                            ▼
osm_data/gis_outputs/{tag}/{sub_category}/
    {prefix}.parquet  /  .gpkg  /  .db  /  .geojson  /  shp/
```

---

### ⚙️ Prerequisites

1. **Python 3.8+** *(tested on Python 3.13)*
2. **Docker Desktop** — `stefda/osmium-tool` image must be available locally
3. **Python packages:**
   ```bash
   pip install -r requirements.txt
   ```
   or manually:
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow psutil
   ```

> Pull the Docker image once before first run:
> ```bash
> docker pull stefda/osmium-tool
> ```

---

### 🚀 Usage

#### Option A — Interactive Launcher (Recommended)

```bash
python quick_run.py
```

Prompts for: PBF path, cache mode, skip mode, PBF validation, output formats, tag profile.

#### Option B — CLI

```bash
python auto_runner.py \
  --pbf "D:/mbtiles/planet.osm.pbf" \
  --tags military,boundary,power \
  --lang tr \
  --cache auto \
  --skip-mode standard \
  --formats "GeoJSON,GeoPackage (GPKG),Parquet"
```

#### Option C — Extract All Values Under a Tag (`--subtags all`)

```bash
python auto_runner.py \
  --pbf "D:/mbtiles/planet.osm.pbf" \
  --tags landuse,natural \
  --subtags all \
  --lang tr
```

To extract specific subtag values only:

```bash
python auto_runner.py --pbf ... --tags landuse --subtags forest,residential,military
```

---

### 🧠 Processing Modes

#### Cache / Node Index

| Mode | Description | Best For |
|------|-------------|----------|
| **auto** *(default)* | DISK for files >1.5 GB, RAM otherwise | General use |
| **ram** | In-memory index (fast) + RAM guard | Small / medium files |
| **disk** | `sparse_file_array` on SSD | Planet-scale files |

#### PBF Processing Mode (per file, auto-selected)

| Mode | Trigger | Notes |
|------|---------|-------|
| **pyosmium** | File < 500 MB | Fast, uses libosmium C++ with isolated subprocess |
| **Docker export** | File ≥ 500 MB | `osmium export` → GeoJSON Sequence → pure-Python streaming; zero C++ crash risk |

If a tag crashes with a C++ exit code (Windows `0xC0000374` / `0xC0000005`), the pipeline splits the PBF and retries automatically in Docker mode.

---

### 📁 Output Structure

```
osm_data/
├── filtered_{tag}.pbf            ← osmium tags-filter output
├── filtered_{tag}_part001.pbf    ← split parts (if >1.5 GB)
│   filtered_{tag}_part002.pbf
└── gis_outputs/
    └── {tag}/
        └── {sub_category}/
            ├── {prefix}.parquet
            ├── {prefix}.gpkg
            ├── {prefix}.db
            ├── {prefix}.geojson
            └── shp/
                └── {prefix}_v1.shp
```

---

### 🏷️ Supported OSINT Tags

`boundary` · `place` · `military` · `amenity` · `power` · `telecom` · `highway` · `aeroway` · `railway` · `waterway` · `harbour` · `barrier` · `man_made` · `landuse` · `office` · `building` · `natural` · `emergency` · `industrial` · `route`

Each tag has a built-in strategic subtag whitelist. Use `--subtags all` to bypass the whitelist and extract every value.

---

### 🛡️ Stability Guarantees

- **C++ crash isolation:** Each tag runs in its own Python subprocess. A Windows heap-corruption crash (`0xC0000374`) in one tag is detected and logged; the next tag starts normally.
- **Empty PBF detection:** Split parts and base files under 100 KB are silently skipped.
- **Oversized line protection:** GeoJSON lines >50 MB (massive coastline polygons) are skipped by the binary streaming reader without loading into RAM.
- **Per-format error isolation:** A failure writing GPKG or SHP does not abort Parquet or SQLite output for the same batch.
- **Resume support:** If interrupted, temp JSONL parts remain on disk. Re-running the pipeline picks up and merges them without reprocessing the PBF.

---

### 🔧 Script Reference

| Script | Role |
|--------|------|
| `quick_run.py` | Interactive launcher with menus and drag-and-drop |
| `auto_runner.py` | Main orchestrator — filtering, splitting, exporting |
| `osint_gis_exporter.py` | Per-tag geometry extractor and format writer |
| `pbf_splitter.py` | Splits large PBF files into 1.5 GB longitude slices |
| `osint_filter.ps1` / `.sh` | Auto-generated Docker osmium filter script |
| `export_config.json` | Auto-generated run config (tags, formats, lang, skip mode) |

---

---

## Türkçe Dokümantasyon

🇬🇧 [English](#english-documentation)

Planet boyutundaki OpenStreetMap (OSM) `.pbf` dosyalarını OSINT ve CBS istihbarat iş akışları için işlemek üzere tasarlanmış sağlam, çapraz platform (Windows / Linux) ETL boru hattı.

Ham OSM verilerini stratejik etiketlere (askeri, sınır, enerji, telekomünikasyon vb.) göre filtreler, geometrileri yeniden oluşturur ve dosya boyutundan bağımsız olarak çökmeden birden fazla CBS formatına aktarır.

---

### ✨ Temel Özellikler

| Özellik | Açıklama |
|---------|----------|
| **Sıfır Çöküş Mimarisi** | Her etiket izole bir alt süreçte işlenir. Bir çöküş veya zaman aşımı pipeline'ı durdurmaz. |
| **Çift Modlu İşleme** | Küçük dosyalar (<500 MB) için **pyosmium**, büyük dosyalar için **Docker osmium export** — her dosya için otomatik seçilir. |
| **Otomatik PBF Bölme** | 1,5 GB'ı aşan dosyalar işlenmeden önce boylam dilimlerine ayrılır. Boş dilimler (<100 KB) otomatik silinir. |
| **`--subtags all`** | Yerleşik OSINT beyaz listesiyle sınırlı kalmadan bir etiket altındaki tüm OSM değerlerini çıkarır. |
| **PBF Doğrulama** | İşleme başlamadan önce filtrelenmiş PBF dosyaları isteğe bağlı olarak doğrulanır. Bozuk dosyalar etkileşimli olarak silinip yeniden oluşturulabilir. |
| **Artık Dosya Temizleme** | Çökmüş çalıştırmalardan kalan `.geojsonseq` dosyaları başlangıçta tespit edilir; silinmesi veya önbellek olarak kullanılması önerilir. |
| **24 Saatlik Zaman Aşımı** | Etiket başına alt süreç zaman aşımı 24 saattir; büyük etiketler (highway, natural) tamamen işlenir. |
| **RAM Koruması** | Bellek sürekli izlenir; RAM >%80 olduğunda kayıtlar otomatik diske yazılır. OOM çöküşü yaşanmaz. |
| **Saf Python WKT** | Geometri dönüşümü bağımlılıksız bir WKT yazıcı kullanır — akış yolunda Shapely/GEOS yoktur. |
| **Akıllı Atlama** | Standart (klasör var mı) veya Detaylı (alt etiket başına dosya kontrolü) atlama modları. |

---

### 🗂️ Pipeline Genel Bakış

```
quick_run.py  ──────────────────────────────────────────────┐
                                                            ▼
auto_runner.py                                              │
  [Adım 0] Eski betikler temizlenir                        │
  [Adım 1] osint_filter.ps1 / .sh oluşturulur             │
  [Adım 2] Docker osmium tags-filter çalışır (etiket/etiket)│
  [Ön-Bölme] pbf_splitter.py  ←─── 1,5 GB+ PBF'leri böler │
  [Adım 3] osint_gis_exporter.py (etiket başına alt süreç) │
            ├── pyosmium modu   (dosya < 500 MB)           │
            └── Docker export modu (dosya ≥ 500 MB)        │
                                                            ▼
osm_data/gis_outputs/{etiket}/{alt_kategori}/
    {ön_ek}.parquet  /  .gpkg  /  .db  /  .geojson  /  shp/
```

---

### ⚙️ Gereksinimler

1. **Python 3.8+** *(Python 3.13 ile test edilmiştir)*
2. **Docker Desktop** — `stefda/osmium-tool` imajı yerel olarak mevcut olmalıdır
3. **Python kütüphaneleri:**
   ```bash
   pip install -r requirements.txt
   ```
   veya manuel olarak:
   ```bash
   pip install osmium pandas geopandas shapely pyogrio pyarrow psutil
   ```

> İlk çalıştırmadan önce Docker imajını bir kez indirin:
> ```bash
> docker pull stefda/osmium-tool
> ```

---

### 🚀 Kullanım

#### Seçenek A — Etkileşimli Başlatıcı (Önerilen)

```bash
python quick_run.py
```

PBF yolu, önbellek modu, atlama modu, PBF doğrulama, çıktı formatları ve etiket profili için sizi yönlendirir.

#### Seçenek B — Komut Satırı (CLI)

```bash
python auto_runner.py \
  --pbf "D:/mbtiles/planet.osm.pbf" \
  --tags military,boundary,power \
  --lang tr \
  --cache auto \
  --skip-mode standard \
  --formats "GeoJSON,GeoPackage (GPKG),Parquet"
```

#### Seçenek C — Etiket Altındaki Tüm Değerleri Çıkarma (`--subtags all`)

```bash
python auto_runner.py \
  --pbf "D:/mbtiles/planet.osm.pbf" \
  --tags landuse,natural \
  --subtags all \
  --lang tr
```

Belirli alt etiket değerleri için:

```bash
python auto_runner.py --pbf ... --tags landuse --subtags forest,residential,military
```

---

### 🧠 İşleme Modları

#### Önbellek / Düğüm İndeksi

| Mod | Açıklama | En İyi Kullanım |
|-----|----------|-----------------|
| **auto** *(varsayılan)* | 1,5 GB üzeri dosyalarda DISK, altında RAM | Genel kullanım |
| **ram** | Bellek içi indeks (hızlı) + RAM koruması | Küçük / orta dosyalar |
| **disk** | SSD üzerinde `sparse_file_array` | Planet boyutlu dosyalar |

#### PBF İşleme Modu (dosya başına, otomatik seçilir)

| Mod | Tetikleyici | Notlar |
|-----|-------------|--------|
| **pyosmium** | Dosya < 500 MB | Hızlı, izole alt süreçte libosmium C++ kullanır |
| **Docker export** | Dosya ≥ 500 MB | `osmium export` → GeoJSON Sequence → saf Python akışı; C++ çöküş riski sıfır |

Bir etiket C++ çıkış koduyla çökerse (Windows `0xC0000374` / `0xC0000005`), pipeline PBF'yi böler ve Docker modunda otomatik yeniden dener.

---

### 📁 Çıktı Yapısı

```
osm_data/
├── filtered_{etiket}.pbf              ← osmium tags-filter çıktısı
├── filtered_{etiket}_part001.pbf      ← bölünmüş parçalar (1,5 GB+ ise)
│   filtered_{etiket}_part002.pbf
└── gis_outputs/
    └── {etiket}/
        └── {alt_kategori}/
            ├── {ön_ek}.parquet
            ├── {ön_ek}.gpkg
            ├── {ön_ek}.db
            ├── {ön_ek}.geojson
            └── shp/
                └── {ön_ek}_v1.shp
```

---

### 🏷️ Desteklenen OSINT Etiketleri

`boundary` · `place` · `military` · `amenity` · `power` · `telecom` · `highway` · `aeroway` · `railway` · `waterway` · `harbour` · `barrier` · `man_made` · `landuse` · `office` · `building` · `natural` · `emergency` · `industrial` · `route`

Her etiketin yerleşik bir stratejik alt etiket beyaz listesi vardır. Beyaz listeyi devre dışı bırakıp tüm değerleri çıkarmak için `--subtags all` kullanın.

---

### 🛡️ Kararlılık Garantileri

- **C++ çöküş izolasyonu:** Her etiket kendi Python alt sürecinde çalışır. Bir etiketteki Windows heap-corruption çöküşü (`0xC0000374`) tespit edilip loglanır; bir sonraki etiket normal başlar.
- **Boş PBF tespiti:** 100 KB'ın altındaki bölünmüş parçalar ve base dosyalar sessizce atlanır.
- **Devasa satır koruması:** 50 MB'ı aşan GeoJSON satırları (büyük kıyı çizgisi poligonları) binary akış okuyucu tarafından RAM'e yüklenmeden atlanır.
- **Format başına hata izolasyonu:** GPKG veya SHP yazımındaki bir hata, aynı batch için Parquet veya SQLite çıktısını durdurmaz.
- **Kaldığı yerden devam:** Kesintiye uğrarsa geçici JSONL parçaları diskte kalır. Pipeline yeniden çalıştırıldığında PBF'yi yeniden işlemeden bunları birleştirir.

---

### 🔧 Betik Başvurusu

| Betik | Görev |
|-------|-------|
| `quick_run.py` | Menüler ve sürükle-bırak destekli etkileşimli başlatıcı |
| `auto_runner.py` | Ana orkestratör — filtreleme, bölme, dışa aktarma |
| `osint_gis_exporter.py` | Etiket başına geometri çıkarıcı ve format yazıcı |
| `pbf_splitter.py` | Büyük PBF dosyalarını 1,5 GB'lık boylam dilimlerine böler |
| `osint_filter.ps1` / `.sh` | Otomatik oluşturulan Docker osmium filtre betiği |
| `export_config.json` | Otomatik oluşturulan çalışma yapılandırması |
