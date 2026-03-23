# 🌍 OvertureMaps DuckDB Extractor

🇬🇧 English | [🇹🇷 Türkçe](#türkçe-dokümantasyon)

A lightweight tool that queries **Overture Maps** open data directly from AWS S3
using **DuckDB**, filters by a bounding box (bbox), and exports the result to
**GeoJSON**, **GeoPackage**, **Shapefile**, and **Parquet** —
with geometry types (Points / Lines / Polygons) kept in separate files.

No full dataset download required — only the records inside your bbox are fetched.

---

## ✨ Features

* **Auto-detects the latest Overture release** via the STAC catalog (`stac.overturemaps.org`).
* **DuckDB + S3 streaming** — only data inside the bbox is transferred over the network.
* **All 6 themes supported:** `places`, `buildings`, `transportation`, `base`, `divisions`, `addresses`.
* **Geometry separation:** Points, Lines and Polygons are written to separate sub-folders.
* **4 export formats:** GeoJSON, GeoPackage (GPKG), Shapefile (SHP), Parquet.
* **4 GB protection:** GeoJSON and Shapefile files are automatically split into `_part2`, `_part3`… when they approach the 4 GB limit.
* **RAM guard:** `psutil` monitors memory usage; switches to disk-spill mode automatically when free RAM drops below 4 GB (AUTO mode) or when RAM pressure is detected (≥ 75% used / < 2 GB free).
* **Bilingual UI:** All messages available in English and Turkish (`--lang en/tr`).

---

## ⚙️ Prerequisites

```bash
pip install duckdb geopandas pyogrio pyarrow psutil
```

> DuckDB's `httpfs` and `spatial` extensions are installed automatically at first run.

---

## 🚀 Usage

### Option A — Interactive Launcher (Recommended)

```bash
cd overturemaps
python quick_run_overture.py
```

The launcher will guide you through:
1. Language selection
2. BBox selection (presets or custom coordinates)
3. Theme selection (all or specific)
4. Export format selection
5. Memory mode selection (AUTO / RAM / DISK)

### Option B — Command Line Interface

```bash
python overture_extractor.py \
  --bbox 28.974,41.035,28.982,41.040 \
  --themes places,buildings \
  --formats geojson,gpkg,shp,parquet \
  --lang en
```

#### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--bbox` | *(required)* | `min_lon,min_lat,max_lon,max_lat` |
| `--themes` | `all` | Comma-separated: `places,buildings,transportation,base,divisions,addresses` |
| `--formats` | `geojson,gpkg,shp,parquet` | Comma-separated export formats |
| `--lang` | `en` | Interface language: `en` or `tr` |
| `--version` | *(auto-detected)* | Override Overture release, e.g. `2025-05-21.0` |
| `--disk` | off | Enable disk-spill mode for large areas |
| `--output` | `./output` | Custom output directory |

---

## 📦 Available Themes & Types

| Theme | Types | Geometry |
|-------|-------|----------|
| `places` | `place` | Point |
| `buildings` | `building`, `building_part` | Polygon |
| `transportation` | `segment`, `connector` | LineString, Point |
| `addresses` | `address` | Point |
| `base` | `land`, `water`, `land_use`, `infrastructure` | Polygon |
| `divisions` | `division_area`, `division_boundary` | Polygon, LineString |

---

## 📁 Output Structure

```
overturemaps/output/{release_version}/
└── {theme}/
    └── {type}/
        ├── points/
        │   ├── {theme}_{type}_points.gpkg
        │   ├── {theme}_{type}_points.parquet
        │   ├── {theme}_{type}_points.geojson
        │   └── shp/
        │       └── {theme}_{type}_points.shp
        ├── lines/
        │   └── ...
        └── polygons/
            └── ...
```

---

## 🔖 Test Example (Small Area)

Istanbul — Taksim Square (~0.008° × 0.005°):

```bash
python overture_extractor.py \
  --bbox 28.974,41.035,28.982,41.040 \
  --themes places,buildings \
  --lang en
```

---

---

# 🇹🇷 Türkçe Dokümantasyon

[🇬🇧 English](#-overturemaps-duckdb-extractor)

**DuckDB** kullanarak **Overture Maps** açık verisini AWS S3'ten doğrudan sorgulayan,
belirlenen bbox içindeki kayıtları **GeoJSON**, **GeoPackage**, **Shapefile** ve **Parquet**
formatlarında dışa aktaran hafif bir araçtır.

Tam veri seti indirmeye gerek yoktur — yalnızca bbox içine düşen kayıtlar ağ üzerinden çekilir.

---

## ✨ Özellikler

* **En güncel Overture sürümü otomatik tespit edilir** (STAC kataloğu: `stac.overturemaps.org`).
* **DuckDB + S3 akışı** — yalnızca bbox içindeki veriler ağ üzerinden aktarılır.
* **6 tema desteği:** `places`, `buildings`, `transportation`, `base`, `divisions`, `addresses`.
* **Geometri ayrımı:** Noktalar, Çizgiler ve Poligonlar ayrı alt klasörlere yazılır.
* **4 dışa aktarım formatı:** GeoJSON, GeoPackage (GPKG), Shapefile (SHP), Parquet.
* **4 GB koruması:** GeoJSON ve Shapefile dosyaları 4 GB limitine yaklaşınca otomatik olarak `_part2`, `_part3`… şeklinde bölünür.
* **RAM koruması:** `psutil` bellek kullanımını izler; boş RAM 4 GB'ın altına düşünce otomatik disk moduna geçer (OTOMATİK mod). RAM kullanımı ≥ %75 veya boş RAM < 2 GB olduğunda erken uyarı verilir.
* **Çift dilli arayüz:** Tüm mesajlar Türkçe ve İngilizce (`--lang en/tr`).

---

## ⚙️ Gereksinimler

```bash
pip install duckdb geopandas pyogrio pyarrow psutil
```

> DuckDB'nin `httpfs` ve `spatial` eklentileri ilk çalıştırmada otomatik yüklenir.

---

## 🚀 Kullanım

### Seçenek A — Etkileşimli Başlatıcı (Önerilen)

```bash
cd overturemaps
python quick_run_overture.py
```

Başlatıcı sizi şu adımlardan geçirir:
1. Dil seçimi
2. BBox seçimi (hazır önayarlar veya özel koordinatlar)
3. Tema seçimi (tümü veya belirli temalar)
4. Dışa aktarım formatı seçimi
5. Bellek modu seçimi (OTOMATİK / RAM / DİSK)

### Seçenek B — Komut Satırı (CLI)

```bash
python overture_extractor.py \
  --bbox 28.974,41.035,28.982,41.040 \
  --themes places,buildings \
  --formats geojson,gpkg,shp,parquet \
  --lang tr
```

#### CLI Argümanları

| Argüman | Varsayılan | Açıklama |
|---------|------------|----------|
| `--bbox` | *(zorunlu)* | `min_lon,min_lat,max_lon,max_lat` |
| `--themes` | `all` | Virgülle ayrılmış: `places,buildings,transportation,base,divisions,addresses` |
| `--formats` | `geojson,gpkg,shp,parquet` | Virgülle ayrılmış dışa aktarım formatları |
| `--lang` | `en` | Arayüz dili: `en` veya `tr` |
| `--version` | *(otomatik)* | Overture sürümünü elle belirle, örn. `2025-05-21.0` |
| `--disk` | kapalı | Büyük alanlar için disk yazma modunu etkinleştir |
| `--output` | `./output` | Özel çıktı dizini |

---

## 📦 Kullanılabilir Temalar ve Tipler

| Tema | Tipler | Geometri |
|------|--------|----------|
| `places` | `place` | Nokta |
| `buildings` | `building`, `building_part` | Poligon |
| `transportation` | `segment`, `connector` | Çizgi, Nokta |
| `addresses` | `address` | Nokta |
| `base` | `land`, `water`, `land_use`, `infrastructure` | Poligon |
| `divisions` | `division_area`, `division_boundary` | Poligon, Çizgi |

---

## 📁 Çıktı Yapısı

```
overturemaps/output/{sürüm}/
└── {tema}/
    └── {tip}/
        ├── points/
        │   ├── {tema}_{tip}_points.gpkg
        │   ├── {tema}_{tip}_points.parquet
        │   ├── {tema}_{tip}_points.geojson
        │   └── shp/
        │       └── {tema}_{tip}_points.shp
        ├── lines/
        │   └── ...
        └── polygons/
            └── ...
```

---

## 🔖 Test Örneği (Küçük Alan)

İstanbul — Taksim Meydanı (~0,008° × 0,005°):

```bash
python overture_extractor.py \
  --bbox 28.974,41.035,28.982,41.040 \
  --themes places,buildings \
  --lang tr
```
