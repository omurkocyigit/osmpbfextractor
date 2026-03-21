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

    # 4. auto_runner.py'yi Çağır
    runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_runner.py")
    
    if not os.path.exists(runner_path):
        print("\n[HATA/ERROR] auto_runner.py bulunamadı! Lütfen aynı klasörde olduklarından emin olun.")
        sys.exit(1)

    cmd = [sys.executable, runner_path, "--pbf", pbf_path, "--tags", tags, "--lang", lang, "--cache", cache_type]
    
    print("\n" + "="*54)
    print(f" >>> Executing: python auto_runner.py --tags {tags} --cache {cache_type}")
    print("="*54 + "\n")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[İptal Edildi / Cancelled]")
    except Exception as e:
        print(f"\n[Hata / Error] {e}")

if __name__ == "__main__":
    main()