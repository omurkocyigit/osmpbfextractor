import os
import sys
import json
import subprocess
import argparse
import platform

# =====================================================================
# ZERO-TOUCH CONFIGURATION
# =====================================================================

RUN_METHOD = "docker"

ALL_TARGET_TAGS = [
    "boundary", "place", "military", "amenity", "power", "telecom", 
    "highway", "aeroway", "railway", "waterway", "harbour", "barrier", 
    "man_made", "landuse", "office", "building", "natural", "emergency"
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

def create_config_and_script(pbf_path, target_tags, lang, cache_type):
    print(MESSAGES[lang]["step1"])
    
    config = {
        "tags": target_tags, 
        "formats": OUTPUT_FORMATS, 
        "lang": lang,
        "cache": cache_type
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"  -> {CONFIG_PATH}{MESSAGES[lang]['generated']}")

    out_dir_docker = "/out"
    source_dir_docker = "/source"
    
    if IS_WINDOWS:
        script_content = "# OSINT PBF Auto-Filter Script\n"
        script_content += "$outDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot \"osm_data\"))\n"
        script_content += "if (-Not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }\n\n"
        script_content += f"$sourcePbf = '{pbf_path}'\n"
        script_content += "$sourceDir = Split-Path $sourcePbf\n"
        script_content += "$sourceFileName = Split-Path $sourcePbf -Leaf\n\n"
        
        for tag in target_tags:
            safe_tag = "".join(c if c.isalnum() else "_" for c in tag)
            output_name = f"filtered_{safe_tag}.pbf"
            script_content += f"if (Test-Path \"$outDir\\{output_name}\") {{\n"
            script_content += f"    Write-Host '{MESSAGES[lang]['skip']}{tag} PBF' -ForegroundColor DarkGray\n"
            script_content += "} else {\n"
            script_content += f"    Write-Host '{MESSAGES[lang]['filter']}{tag} -> $outDir\\{output_name}...' -ForegroundColor Yellow\n"
            script_content += f"    docker run --rm -v \"${{sourceDir}}:{source_dir_docker}\" -v \"${{outDir}}:{out_dir_docker}\" stefda/osmium-tool osmium tags-filter {source_dir_docker}/$sourceFileName nwr/{tag} -o {out_dir_docker}/{output_name}\n"
            # HATA DÜZELTİLDİ: '}' yerine '}}' kullanıldı
            script_content += f"    Write-Host '{tag}{MESSAGES[lang]['extract']}' -ForegroundColor Green\n}}\n\n"
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
            script_content += f"    docker run --rm -v \"$SOURCE_DIR:{source_dir_docker}\" -v \"$OUT_DIR:{out_dir_docker}\" stefda/osmium-tool osmium tags-filter {source_dir_docker}/$SOURCE_FILE nwr/{tag} -o {out_dir_docker}/{output_name}\n"
            script_content += f"    echo -e '\\e[32m{tag}{MESSAGES[lang]['extract']}\\e[0m'\nfi\n\n"

    with open(SCRIPT_PATH, "w", encoding="utf-8") as f:
        f.write(script_content)
    
    if not IS_WINDOWS:
        os.chmod(SCRIPT_PATH, 0o755)
        
    print(f"  -> {SCRIPT_PATH}{MESSAGES[lang]['generated']} (OS: {platform.system()})")

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
    args = parser.parse_args()

    target_tags = ALL_TARGET_TAGS if args.tags.lower() == "all" else [t.strip() for t in args.tags.split(",") if t.strip()]

    print("======================================================")
    print("  ZERO-TOUCH OSINT PIPELINE (Sıfır Temaslı ETL)")
    print(f"  OS: {platform.system()} | Tags: {len(target_tags)} | Lang: {args.lang.upper()}")
    print(f"  Cache: {args.cache.upper()}")
    print("======================================================\n")
    
    clean_old_scripts(args.lang)
    create_config_and_script(args.pbf, target_tags, args.lang, args.cache)
    
    if IS_WINDOWS:
        run_command(["powershell", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH], args.lang, is_docker_step=True)
    else:
        run_command(["bash", SCRIPT_PATH], args.lang, is_docker_step=True)
    
    exporter_path = os.path.join(SCRIPT_DIR, "osint_gis_exporter.py")
    if not os.path.exists(exporter_path):
        print(f"\n{exporter_path}{MESSAGES[args.lang]['err_notfound']}")
        sys.exit(1)
        
    run_command([sys.executable, exporter_path], args.lang)
    print(MESSAGES[args.lang]["success"])

if __name__ == "__main__":
    main()