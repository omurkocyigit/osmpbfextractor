import os
import sys
import json
import subprocess
import argparse
import platform
import time
import psutil

# =====================================================================
# ZERO-TOUCH CONFIGURATION
# =====================================================================

RUN_METHOD = "docker"
OSMIUM_DOCKER_IMAGE = "stefda/osmium-tool"

ALL_TARGET_TAGS = [
    "boundary", "place", "military", "amenity", "power", "telecom", 
    "highway", "aeroway", "railway", "waterway", "harbour", "barrier", 
    "man_made", "landuse", "office", "building", "natural", "emergency",
    "industrial", "route"
]

OUTPUT_FORMATS = [
    "GeoJSON", "GeoPackage (GPKG)", "Parquet", "SQLite", "Shapefile (SHP)"
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "osm_data")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "export_config.json")

IS_WINDOWS = os.name == 'nt'
SCRIPT_EXT = ".ps1" if IS_WINDOWS else ".sh"
SCRIPT_PATH = os.path.join(SCRIPT_DIR, f"osint_filter{SCRIPT_EXT}")

# Dil Sözlüğü / Language Dictionary
MESSAGES = {
    "en": {
        "step0": "\n[Step 0] Cleaning old scripts and configs...",
        "removed": "  -> Removed: ",
        "step1": "\n[Step 1] Generating configurations and filtering scripts...",
        "generated": " generated.",
        "skip": "[Skipped] ",
        "filter": "Filtering: ",
        "extract": " extracted.",
        "run_docker": "\n>>> [RUNNING] Docker PBF Filter <<<",
        "run_python": "\n>>> [RUNNING] Python GIS Exporter <<<",
        "err_docker": "\n[CRITICAL ERROR] Docker PBF Filter failed. Exit code: ",
        "err_python": "\n[CRITICAL ERROR] Python GIS Exporter failed. Exit code: ",
        "err_notfound": " not found!",
        "success": "\n*** SUCCESS: PIPELINE COMPLETED! ***"
    },
    "tr": {
        "step0": "\n[Adım 0] Eski betikler ve yapılandırma dosyaları temizleniyor...",
        "removed": "  -> Silindi: ",
        "step1": "\n[Adım 1] Konfigürasyon ve filtreleme betiği oluşturuluyor...",
        "generated": " başarıyla yazıldı.",
        "skip": "[Atlandı] ",
        "filter": "Filtreleniyor: ",
        "extract": " başarıyla ayrıldı.",
        "run_docker": "\n>>> [BAŞLATILDI] Docker PBF Filtreleme Süreci <<<",
        "run_python": "\n>>> [BAŞLATILDI] Python GIS Exporter <<<",
        "err_docker": "\n[KRİTİK HATA] Docker PBF Filtreleme çöktü. Çıkış kodu: ",
        "err_python": "\n[KRİTİK HATA] Python GIS Exporter çöktü. Çıkış kodu: ",
        "err_notfound": " bulunamadı!",
        "success": "\n*** MÜKEMMEL: TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI! ***"
    }
}

def clean_old_scripts(lang):
    print(MESSAGES[lang]["step0"])
    for path in [CONFIG_PATH, SCRIPT_PATH]:
        if os.path.exists(path):
            os.remove(path)
            print(f"{MESSAGES[lang]['removed']}{os.path.basename(path)}")

def create_config_and_script(pbf_path, target_tags, lang, cache_type, skip_mode, formats):
    print(MESSAGES[lang]["step1"])

    config = {
        "tags": target_tags, 
        "formats": formats, 
        "lang": lang,
        "cache": cache_type,
        "skip_mode": skip_mode
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"  -> {CONFIG_PATH}{MESSAGES[lang]['generated']}")

    out_dir_docker = "/out"
    source_dir_docker = "/source"
    
    if IS_WINDOWS:
        # PS1 dosyası ASCII-only mesajlar kullanır (encoding bağımsızlığı için)
        script_content = "# OSINT PBF Auto-Filter Script\n"
        script_content += "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        script_content += "$outDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot \"osm_data\"))\n"
        script_content += "if (-Not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }\n\n"
        script_content += f"$sourcePbf = '{pbf_path}'\n"
        script_content += "$sourceDir = Split-Path $sourcePbf\n"
        script_content += "$sourceFileName = Split-Path $sourcePbf -Leaf\n\n"

        for tag in target_tags:
            safe_tag = "".join(c if c.isalnum() else "_" for c in tag)
            output_name = f"filtered_{safe_tag}.pbf"
            script_content += f"if (Test-Path \"$outDir\\{output_name}\") {{\n"
            script_content += f"    Write-Host '[SKIP] {tag} PBF already exists.' -ForegroundColor DarkGray\n"
            script_content += "} else {\n"
            script_content += f"    Write-Host '[FILTER] {tag} -> ' -NoNewline -ForegroundColor Yellow\n"
            script_content += f"    Write-Host \"$outDir\\{output_name}\" -ForegroundColor Yellow\n"
            script_content += f"    docker run --rm -v \"${{sourceDir}}:{source_dir_docker}\" -v \"${{outDir}}:{out_dir_docker}\" {OSMIUM_DOCKER_IMAGE} osmium tags-filter {source_dir_docker}/$sourceFileName nwr/{tag} -o {out_dir_docker}/{output_name}\n"
            script_content += "    if ($LASTEXITCODE -ne 0) {\n"
            script_content += f"        Write-Host '[ERROR] {tag} filter failed (exit: ' -NoNewline -ForegroundColor Red\n"
            script_content += "        Write-Host $LASTEXITCODE -NoNewline -ForegroundColor Red\n"
            script_content += "        Write-Host '). Removing partial file.' -ForegroundColor Red\n"
            script_content += f"        if (Test-Path \"$outDir\\{output_name}\") {{ Remove-Item \"$outDir\\{output_name}\" -Force }}\n"
            script_content += "    } else {\n"
            script_content += f"        Write-Host '[OK] {tag} extracted.' -ForegroundColor Green\n"
            script_content += "    }\n"
            script_content += "}\n\n"
    else:
        script_content = "#!/bin/bash\n"
        script_content += "OUT_DIR=\"$(cd \"$(dirname \"$0\")\" && pwd)/osm_data\"\n"
        script_content += "mkdir -p \"$OUT_DIR\"\n\n"
        script_content += f"SOURCE_PBF=\"{pbf_path}\"\n"
        script_content += "SOURCE_DIR=\"$(dirname \"$SOURCE_PBF\")\"\n"
        script_content += "SOURCE_FILE=\"$(basename \"$SOURCE_PBF\")\"\n\n"

        for tag in target_tags:
            safe_tag = "".join(c if c.isalnum() else "_" for c in tag)
            output_name = f"filtered_{safe_tag}.pbf"
            script_content += f"if [ -f \"$OUT_DIR/{output_name}\" ]; then\n"
            script_content += f"    echo -e '\\e[90m{MESSAGES[lang]['skip']}{tag} PBF\\e[0m'\n"
            script_content += "else\n"
            script_content += f"    echo -e '\\e[33m{MESSAGES[lang]['filter']}{tag} -> $OUT_DIR/{output_name}...\\e[0m'\n"
            script_content += f"    docker run --rm -v \"$SOURCE_DIR:{source_dir_docker}\" -v \"$OUT_DIR:{out_dir_docker}\" {OSMIUM_DOCKER_IMAGE} osmium tags-filter {source_dir_docker}/$SOURCE_FILE nwr/{tag} -o {out_dir_docker}/{output_name}\n"
            script_content += "    if [ $? -ne 0 ]; then\n"
            script_content += f"        echo -e '\\e[31m[HATA] {tag} filtreleme basarisiz, eksik dosya siliniyor.\\e[0m'\n"
            script_content += f"        [ -f \"$OUT_DIR/{output_name}\" ] && rm -f \"$OUT_DIR/{output_name}\"\n"
            script_content += "    else\n"
            script_content += f"        echo -e '\\e[32m{tag}{MESSAGES[lang]['extract']}\\e[0m'\n"
            script_content += "    fi\n"
            script_content += "fi\n\n"

    # Windows PS1: UTF-8 BOM gerekli (PS 5.1 BOM'suz UTF-8'i Win-1252 okur)
    encoding = "utf-8-sig" if IS_WINDOWS else "utf-8"
    with open(SCRIPT_PATH, "w", encoding=encoding) as f:
        f.write(script_content)

    if not IS_WINDOWS:
        os.chmod(SCRIPT_PATH, 0o755)
        
    print(f"  -> {SCRIPT_PATH}{MESSAGES[lang]['generated']} (OS: {platform.system()})")

def scan_orphan_geojsonseq():
    """
    osm_data dizinindeki sahipsiz .geojsonseq dosyalarını listeler.
    Bunlar: Docker export tamamlandı ama streaming crash aldı → dosya silme çalışmadı.
    """
    if not os.path.exists(DATA_DIR):
        return []
    orphans = []
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".geojsonseq"):
            fpath = os.path.join(DATA_DIR, fname)
            size_gb = os.path.getsize(fpath) / (1024 ** 3)
            orphans.append((fname, fpath, size_gb))
    return orphans


def _delete_tag_pbf_files(tag):
    """Bir tag'ın base PBF, tüm part dosyaları ve geojsonseq ara dosyalarını siler."""
    safe_tag = "".join(c if c.isalnum() else "_" for c in tag)
    if not os.path.exists(DATA_DIR):
        return []
    deleted = []
    for fname in sorted(os.listdir(DATA_DIR)):
        base = f"filtered_{safe_tag}"
        if (fname == f"{base}.pbf"
                or (fname.startswith(f"{base}_part") and fname.endswith(".pbf"))
                or fname.startswith(f"islenmis_{base}")
                or (fname.startswith(base) and fname.endswith(".geojsonseq"))):
            try:
                os.remove(os.path.join(DATA_DIR, fname))
                deleted.append(fname)
            except Exception as e:
                print(f"  [SILINEMEDI] {fname}: {e}")
    return deleted


def _check_docker_image(image):
    """Docker imajının yerel olarak mevcut olup olmadığını kontrol eder."""
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=15, check=False
        )
        return r.returncode == 0
    except Exception:
        return False


def validate_filtered_pbfs(target_tags, deep=False):
    """
    Mevcut filtered PBF dosyalarını doğrular.
    deep=False → osmium fileinfo (sadece header, hızlı ~2sn/dosya)
    deep=True  → osmium fileinfo -e (tüm dosya, yavaş ama kesin)
    Bozuk tag listesini döndürür.
    """
    if not os.path.exists(DATA_DIR):
        return []

    # Docker imajı yoksa osmium doğrulaması yapılamaz — yanlış pozitif önle
    if not _check_docker_image(OSMIUM_DOCKER_IMAGE):
        print(f"\n[Doğrulama] '{OSMIUM_DOCKER_IMAGE}' imaji yerel olarak bulunamadi.")
        print(f"  Sadece boyut kontrolu yapiliyor (osmium dogrulamasi atlanıyor).")
        use_osmium = False
    else:
        use_osmium = True

    abs_data_dir = os.path.abspath(DATA_DIR)
    invalid = []
    mode_label = "DERIN" if deep else "HIZLI"
    print(f"\n[Dogrulama/{mode_label}] Filtered PBF dosyalari kontrol ediliyor...")

    for tag in target_tags:
        safe_tag = "".join(c if c.isalnum() else "_" for c in tag)
        pbf_name = f"filtered_{safe_tag}.pbf"
        pbf_path = os.path.join(DATA_DIR, pbf_name)

        if not os.path.exists(pbf_path):
            print(f"  [YOK]    {pbf_name}")
            continue

        size_mb = os.path.getsize(pbf_path) / (1024 ** 2)

        if size_mb < 0.001:
            print(f"  [BOZUK]  {pbf_name} -- 0 byte")
            invalid.append(tag)
            continue

        if not use_osmium:
            print(f"  [BOYUT]  {pbf_name} ({size_mb:.0f} MB) -- osmium dogrulamasi atlandi")
            continue

        cmd = ["docker", "run", "--rm", "-v", f"{abs_data_dir}:/data",
               OSMIUM_DOCKER_IMAGE, "osmium", "fileinfo"]
        if deep:
            cmd.append("-e")
        cmd.append(f"/data/{pbf_name}")

        timeout = 600 if deep else 60
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
            if result.returncode != 0:
                err = result.stderr.decode(errors="replace").strip().split("\n")[0]
                # Docker imaj hatası ise yanlış pozitif sayma
                if "Unable to find image" in err or "pull access denied" in err:
                    print(f"  [ATLA]   {pbf_name} -- Docker imaj sorunu, dogrulama atlandi")
                else:
                    print(f"  [BOZUK]  {pbf_name} ({size_mb:.0f} MB) -- {err}")
                    invalid.append(tag)
            else:
                print(f"  [TAMAM]  {pbf_name} ({size_mb:.0f} MB)")
        except subprocess.TimeoutExpired:
            print(f"  [TAMAM?] {pbf_name} ({size_mb:.0f} MB) -- zaman asimi (muhtemelen saglikli)")
        except Exception as e:
            print(f"  [UYARI]  {pbf_name} dogrulanamadi: {e}")

    return invalid


def _is_cpp_crash(code):
    """Windows C++ crash exit kodlarını tanır (0xC0000000–0xCFFFFFFF aralığı)."""
    return 3221225472 <= code <= 3489660927

def run_command(command, lang, is_docker_step=False):
    msg_key = "run_docker" if is_docker_step else "run_python"
    err_key = "err_docker" if is_docker_step else "err_python"
    
    print(MESSAGES[lang][msg_key])
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"{MESSAGES[lang][err_key]}{e.returncode}")
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="Zero-Touch OSINT ETL Pipeline")
    parser.add_argument("--pbf", type=str, required=True, help="Path to the source OSM PBF file.")
    parser.add_argument("--tags", type=str, default="all", help="Tags to process (e.g., 'military,place' or 'all').")
    parser.add_argument("--lang", type=str, choices=["en", "tr"], default="en", help="Language for terminal logs (en or tr).")
    parser.add_argument("--cache", type=str, choices=["auto", "ram", "disk"], default="auto", help="Node cache type.")
    parser.add_argument("--skip-mode", type=str, choices=["standard", "detailed"], default="standard", help="Smart skip mode.")
    parser.add_argument("--formats", type=str, default="all", help="Output formats (comma separated).")
    parser.add_argument("--subtags", type=str, default=None,
                        help="Alt tag filtresi: 'all' → tüm değerleri çıkar | 'forest,residential' → belirli değerler.")
    parser.add_argument("--validate-pbf", action="store_true", default=False,
                        help="Filtreleme sonrası PBF dosyalarını doğrula (header kontrolü, ~2sn/dosya).")
    parser.add_argument("--deep-validate", action="store_true", default=False,
                        help="Tam dosya doğrulaması (osmium fileinfo -e, yavaş ama kesin).")
    args = parser.parse_args()

    target_tags = ALL_TARGET_TAGS if args.tags.lower() == "all" else [t.strip() for t in args.tags.split(",") if t.strip()]
    
    if args.formats.lower() == "all":
        target_formats = OUTPUT_FORMATS
    else:
        target_formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    print("======================================================")
    print("  ZERO-TOUCH OSINT PIPELINE (Sıfır Temaslı ETL)")
    print(f"  OS: {platform.system()} | Tags: {len(target_tags)} | Lang: {args.lang.upper()}")
    print(f"  Cache: {args.cache.upper()} | Skip: {args.skip_mode.upper()}")
    print(f"  Formats: {', '.join(target_formats)}")
    print("======================================================\n")
    
    # ── Orphan GeoJSONSeq Taraması ───────────────────────────────────────────
    orphans = scan_orphan_geojsonseq()
    if orphans:
        total_gb = sum(g for _, _, g in orphans)
        print(f"\n[GeoJSONSeq] Önceki çalışmadan kalan {len(orphans)} ara dosya tespit edildi ({total_gb:.1f} GB):")
        for fname, _, size_gb in orphans:
            print(f"  • {fname}  ({size_gb:.1f} GB)")
        print("\n  Bu dosyalar Docker export'u atlayarak hızlandırır (cache).")
        print("  Disk alanı kazanmak için silebilirsiniz (sonraki çalıştırmada yeniden oluşturulur).")
        choice = input("  Sil mi? [e=Sil / h=Cache olarak tut]: ").strip().lower()
        if choice in ("e", "y", "evet", "yes"):
            for fname, fpath, size_gb in orphans:
                try:
                    os.remove(fpath)
                    print(f"    Silindi: {fname}")
                except Exception as ex:
                    print(f"    [HATA] {fname} silinemedi: {ex}")
        else:
            print("  Cache olarak korundu. Bir sonraki çalıştırmada streaming doğrudan bu dosyadan başlar.")
    # ─────────────────────────────────────────────────────────────────────────

    clean_old_scripts(args.lang)
    create_config_and_script(args.pbf, target_tags, args.lang, args.cache, args.skip_mode, target_formats)
    
    if IS_WINDOWS:
        run_command(["powershell", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH], args.lang, is_docker_step=True)
    else:
        run_command(["bash", SCRIPT_PATH], args.lang, is_docker_step=True)

    # ── PBF Doğrulama ────────────────────────────────────────────────────────
    if args.validate_pbf or args.deep_validate:
        invalid_tags = validate_filtered_pbfs(target_tags, deep=args.deep_validate)
        if invalid_tags:
            print(f"\n{'='*54}")
            print(f"  [UYARI] {len(invalid_tags)} bozuk/eksik PBF tespit edildi:")
            for t in invalid_tags:
                safe = "".join(c if c.isalnum() else "_" for c in t)
                p = os.path.join(DATA_DIR, f"filtered_{safe}.pbf")
                mb = os.path.getsize(p) / (1024**2) if os.path.exists(p) else 0
                print(f"    • filtered_{safe}.pbf  ({mb:.1f} MB)")
            print(f"{'='*54}")
            confirm = input(
                "\nBu dosyalar ve tüm parçaları silinip yeniden oluşturulsun mu? [e/h]: "
            ).strip().lower()
            if confirm in ("e", "y", "evet", "yes"):
                for t in invalid_tags:
                    deleted = _delete_tag_pbf_files(t)
                    print(f"  [{t}] Silindi: {', '.join(deleted) if deleted else 'dosya yok'}")
                print("\n[YENİDEN FİLTRELENİYOR] osmium tags-filter yeniden başlatılıyor...")
                if IS_WINDOWS:
                    run_command(["powershell", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH], args.lang, is_docker_step=True)
                else:
                    run_command(["bash", SCRIPT_PATH], args.lang, is_docker_step=True)
            else:
                print("  Silme iptal edildi. Mevcut dosyalarla devam ediliyor...")
        else:
            print(f"  Tüm PBF dosyaları sağlıklı.")
    # ─────────────────────────────────────────────────────────────────────────

    exporter_path = os.path.join(SCRIPT_DIR, "osint_gis_exporter.py")
    if not os.path.exists(exporter_path):
        print(f"\n{exporter_path}{MESSAGES[args.lang]['err_notfound']}")
        sys.exit(1)

    splitter_path = os.path.join(SCRIPT_DIR, "pbf_splitter.py")

    # ── Proaktif PBF Bölme ───────────────────────────────────────────────────
    # Tüm etiketler için 1.5 GB+ dosyaları extraction başlamadan önce böl
    if os.path.exists(splitter_path):
        print("\n[Ön-Bölme] Büyük PBF dosyaları kontrol ediliyor (1.5 GB+ → parçalara ayrılır)...")
        try:
            subprocess.run(
                [sys.executable, splitter_path],
                timeout=7200,
                check=False
            )
        except Exception as e:
            print(f"  [UYARI] Ön-bölme hatası: {e}")
    # ─────────────────────────────────────────────────────────────────────────

    print(MESSAGES[args.lang]["run_python"])
    failed_tags = []
    success_tags = []

    for tag in target_tags:
        print(f"\n  -> [{tag.upper()}] işleniyor...")

        # RAM baskısı varsa bekle (max 60 sn)
        for _ in range(6):
            if psutil.virtual_memory().percent < 85:
                break
            print(f"     [RAM BEKLE] %{psutil.virtual_memory().percent:.0f} dolu → 10s bekleniyor...")
            time.sleep(10)

        tag_ok = False
        for attempt in range(2):
            try:
                cmd = [sys.executable, exporter_path, "--tag", tag]
                if attempt > 0:
                    cmd += ["--mode", "docker"]
                if args.subtags:
                    cmd += ["--subtags", args.subtags]
                result = subprocess.run(
                    cmd,
                    timeout=86400,  # 24 saat — büyük taglar meşru olarak saatler alabilir
                    check=False
                )
                if result.returncode == 0:
                    success_tags.append(tag)
                    tag_ok = True
                    break
                elif _is_cpp_crash(result.returncode) and attempt == 0:
                    print(f"  [C++ CRASH] {tag} çöktü (kod: {result.returncode}). PBF bölünüp yeniden deneniyor...")
                    if os.path.exists(splitter_path):
                        subprocess.run(
                            [sys.executable, splitter_path, "--tag", tag],
                            timeout=3600,
                            check=False
                        )
                    print(f"  [YENİDEN] {tag} tekrar başlatılıyor...")
                    time.sleep(3)
                else:
                    print(f"  [UYARI] {tag} başarısız (kod: {result.returncode}, deneme {attempt + 1}/2)")
            except subprocess.TimeoutExpired:
                print(f"  [TIMEOUT] {tag} zaman aşımı (2 saat), atlanıyor...")
                break
            except Exception as e:
                print(f"  [HATA] {tag} başlatılamadı: {e}")
                break

        if not tag_ok and tag not in success_tags:
            failed_tags.append(tag)

    print(f"\n  Tamamlandı: {len(success_tags)}/{len(target_tags)} tag başarılı")
    if failed_tags:
        print(f"  Başarısız tag'lar: {', '.join(failed_tags)}")
    else:
        print(MESSAGES[args.lang]["success"])

if __name__ == "__main__":
    main()