import os
import sys
import subprocess

# =====================================================================
# [TR] OSINT PIPELINE QUICK LAUNCHER / [EN] INTERACTIVE LAUNCHER
# =====================================================================

def get_input(prompt_text):
    """
    [TR] Kullanıcı girişini alır. Sürükle-bırak yapıldığında oluşan 
         fazladan tırnak işaretlerini (Windows) otomatik temizler.
    """
    return input(prompt_text).strip().strip('"').strip("'")

def main():
    print("======================================================")
    print(" 🚀 OSINT PIPELINE - QUICK LAUNCHER / HIZLI BAŞLATICI")
    print("======================================================")

    # 1. Dil Seçimi
    lang = get_input("Select Language / Dil Seçin (en/tr) [Default: tr]: ").lower() or "tr"
    if lang not in ["en", "tr"]: 
        lang = "tr"

    # Dil Sözlüğü
    msg = {
        "en": {
            "pbf": "Drag and drop your PBF file here (or type the path): ",
            "cache_menu": "\nSelect Node Cache Type (RAM is fast, Disk is safe for Planet files):\n  [1] AUTO (Recommended: {})\n  [2] RAM (Fast, needs lots of RAM)\n  [3] DISK (Safe, uses SSD, prevents RAM crashes)\nChoice [1/2/3]: ",
            "menu": "\nSelect an extraction profile:\n  [1] FULL OSINT (All 18 tags - Heavy Process)\n  [2] CORE STRATEGIC (military, boundary, telecom, power, amenity)\n  [3] INFRASTRUCTURE (highway, railway, aeroway, harbour, barrier)\n  [4] CUSTOM (Type your own tags)\nChoice [1/2/3/4]: ",
            "custom": "Enter tags separated by comma (e.g., military,place): ",
            "err": "Invalid choice! Defaulting to [1] FULL OSINT.",
            "not_found": "File not found: "
        },
        "tr": {
            "pbf": "PBF dosyanızı sürükleyip bırakın (veya yolunu yazın): ",
            "cache_menu": "\nÖnbellek (Cache) Tipi Seçin (RAM hızlıdır, Disk devasa dosyalar için güvenlidir):\n  [1] OTOMATİK (Önerilen: {})\n  [2] RAM (Hızlı, yüksek bellek ister)\n  [3] DİSK (Güvenli, SSD kullanır, RAM patlamasını önler)\nSeçiminiz [1/2/3]: ",
            "menu": "\nBir veri çıkarma profili seçin:\n  [1] FULL OSINT (Tüm 18 etiket - Ağır İşlem)\n  [2] TEMEL STRATEJİK (military, boundary, telecom, power, amenity)\n  [3] ULAŞIM VE ALTYAPI (highway, railway, aeroway, harbour, barrier)\n  [4] ÖZEL (Kendi etiketlerinizi yazın)\nSeçiminiz [1/2/3/4]: ",
            "custom": "Etiketleri virgülle ayırarak yazın (Örn: military,place): ",
            "err": "Geçersiz seçim! Varsayılan olarak [1] FULL OSINT başlatılıyor.",
            "not_found": "Dosya bulunamadı: "
        }
    }

    # 2. PBF Dosyası Yolu
    pbf_path = get_input(msg[lang]["pbf"])
    while not os.path.exists(pbf_path):
        print(f"{msg[lang]['not_found']}{pbf_path}")
        pbf_path = get_input(msg[lang]["pbf"])

    # 2.1 Cache Tipi Seçimi
    pbf_size_gb = os.path.getsize(pbf_path) / (1024**3)
    recommendation = "DISK" if pbf_size_gb > 1.5 else "RAM"
    cache_choice = get_input(msg[lang]["cache_menu"].format(recommendation))
    
    if cache_choice == "2":
        cache_type = "ram"
    elif cache_choice == "3":
        cache_type = "disk"
    else:
        cache_type = "auto"

    # 2.2 Smart Skip Modu Seçimi
    skip_msg = {
        "en": "\nSelect Smart Skip Mode:\n  [1] STANDARD (Skip if folder exists - Fast)\n  [2] DETAILED (Check every sub-tag, process if anything is missing - Safe)\nChoice [1/2]: ",
        "tr": "\nAkıllı Atlama (Smart Skip) Modu Seçin:\n  [1] STANDART (Klasör varsa atla - Hızlı)\n  [2] DETAYLI (Her alt etiketi kontrol et, eksik varsa işle - Güvenli)\nSeçiminiz [1/2]: "
    }
    skip_choice = get_input(skip_msg[lang])
    skip_mode = "detailed" if skip_choice == "2" else "standard"

    # 2.2b PBF Doğrulama Seçimi
    validate_msg = {
        "en": "\nValidate existing filtered PBF files before processing?\n  [1] NO (Skip validation - Fast)\n  [2] QUICK (Header check, ~2s/file)\n  [3] DEEP (Full file scan, slow but thorough)\nChoice [1/2/3]: ",
        "tr": "\nMevcut filtered PBF dosyaları işlenmeden önce doğrulansın mı?\n  [1] HAYIR (Doğrulama atla - Hızlı)\n  [2] HIZLI (Header kontrolü, ~2sn/dosya)\n  [3] DERİN (Tam dosya tarama, yavaş ama kesin)\nSeçiminiz [1/2/3]: "
    }
    validate_choice = get_input(validate_msg[lang])
    validate_flag = ""
    if validate_choice == "2":
        validate_flag = "--validate-pbf"
    elif validate_choice == "3":
        validate_flag = "--deep-validate"

    # 2.3 Çıktı Formatı Seçimi
    format_msg = {
        "en": "\nSelect Output Formats (Parquet is mandatory):\n  [1] ALL (GeoJSON, GPKG, SQLite, SHP, Parquet)\n  [2] ONLY GEOMETRY (GeoJSON, GPKG, Parquet)\n  [3] CUSTOM (Select one or more)\nChoice [1/2/3]: ",
        "tr": "\nÇıktı Formatlarını Seçin (Parquet mecburidir):\n  [1] TÜMÜ (GeoJSON, GPKG, SQLite, SHP, Parquet)\n  [2] SADECE GEOMETRİ (GeoJSON, GPKG, Parquet)\n  [3] ÖZEL SEÇİM (Bir veya daha fazla)\nSeçiminiz [1/2/3]: "
    }
    format_choice = get_input(format_msg[lang])
    
    formats = "Parquet"
    if format_choice == "1" or format_choice == "":
        formats = "GeoJSON,GeoPackage (GPKG),SQLite,Shapefile (SHP),Parquet"
    elif format_choice == "2":
        formats = "GeoJSON,GeoPackage (GPKG),Parquet"
    elif format_choice == "3":
        custom_fmt_msg = {
            "en": "Select (comma separated): [1] GeoJSON, [2] GPKG, [3] SQLite, [4] SHP: ",
            "tr": "Seçin (virgülle ayırın): [1] GeoJSON, [2] GPKG, [3] SQLite, [4] SHP: "
        }
        cf = get_input(custom_fmt_msg[lang])
        if "1" in cf: formats += ",GeoJSON"
        if "2" in cf: formats += ",GeoPackage (GPKG)"
        if "3" in cf: formats += ",SQLite"
        if "4" in cf: formats += ",Shapefile (SHP)"
    else:
        formats = "GeoJSON,GeoPackage (GPKG),SQLite,Shapefile (SHP),Parquet"

    # 3. Profil Seçimi
    choice = get_input(msg[lang]["menu"])
    
    if choice == "1" or choice == "":
        tags = "all"
    elif choice == "2":
        tags = "military,boundary,telecom,power,amenity"
    elif choice == "3":
        tags = "highway,railway,aeroway,harbour,barrier"
    elif choice == "4":
        tags = get_input(msg[lang]["custom"])
        if not tags: tags = "all"
    else:
        print(msg[lang]["err"])
        tags = "all"

    # --- ADIM 1: Filtreleme (osint_filter.ps1) ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filter_script = os.path.join(script_dir, "osint_filter.ps1")
    
    if os.path.exists(filter_script):
        try:
            ps_cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", filter_script, "-sourcePbf", pbf_path]
            subprocess.run(ps_cmd, check=True)
        except Exception as e:
            print(f"\n[UYARI] Filtreleme hatası: {e}")

    # --- ADIM 2: Otomatik Parçalama (pbf_splitter.py) ---
    splitter_script = os.path.join(script_dir, "pbf_splitter.py")
    if os.path.exists(splitter_script):
        print("\n[🛠️] Büyük dosyalar (1.5GB+) kontrol ediliyor, gerekenleri bölüyor...")
        try:
            subprocess.run([sys.executable, splitter_script], check=True)
        except Exception as e:
            print(f"[UYARI] Parçalama hatası: {e}")

    # --- ADIM 3: Veri Çıkarımı (auto_runner.py) ---
    runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_runner.py")
    
    if not os.path.exists(runner_path):
        print("\n[HATA/ERROR] auto_runner.py bulunamadı! Lütfen aynı klasörde olduklarından emin olun.")
        sys.exit(1)

    cmd = [sys.executable, runner_path, "--pbf", pbf_path, "--tags", tags, "--lang", lang, "--cache", cache_type, "--skip-mode", skip_mode, "--formats", formats]
    if validate_flag:
        cmd.append(validate_flag)

    print("\n" + "="*54)
    print(f" >>> Executing: python auto_runner.py --tags {tags} --cache {cache_type} --skip-mode {skip_mode} --formats {formats} {validate_flag}")
    print("="*54 + "\n")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[İptal Edildi / Cancelled]")
    except Exception as e:
        print(f"\n[Hata / Error] {e}")

if __name__ == "__main__":
    main()