import os
import re
import sys
import time
import subprocess
from datetime import datetime, timedelta

PROMPT_FILE_NAME = "prompt.txt"


def get_quota_and_reset_time():
    """Dinamik olarak Claude CLI üzerinden kota durumunu ve reset saatini ayıklar."""
    print("🔍 [SİSTEM] Güncel kota durumu sorgulanıyor (/usage)...")
    output = ""
    try:
        process = subprocess.Popen(
            'claude -p "/usage"',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        stdout, stderr = process.communicate(timeout=8)
        output = stdout + "\n" + stderr
    except Exception as e:
        print(f"❌ [HATA] Kota sorgusu sırasında bir aksaklık oluştu: {e}")
        pass

    # Dinamik zaman formatlarını yakalar (Örn: Jun 20, 8:59am veya 9am)
    match = re.search(r'resets\s+([A-Za-z]+)\s+(\d+),\s+(\d+):?(\d*)(am|pm)', output, re.IGNORECASE)

    if not match:
        match = re.search(r'resets\s+(\d+):?(\d*)(am|pm)', output, re.IGNORECASE)
        if match:
            return datetime.now().strftime('%b'), datetime.now().day, int(match.group(1)), int(match.group(2)) if match.group(2) else 0, match.group(3).lower()

    if match:
        return match.group(1), int(match.group(2)), int(match.group(3)), int(match.group(4)) if match.group(4) else 0, match.group(5).lower()

    if "limit" in output.lower() or "session" in output.lower():
        return datetime.now().strftime('%b'), datetime.now().day, 9, 0, "am"

    return None


def calculate_sleep_seconds(month_str, day, hour, minute, ampm):
    """Hedef sıfırlanma saati ile şu anki bilgisayar saati arasındaki farkı saniye cinsinden bulur."""
    if ampm == 'pm' and hour < 12:
        hour += 12
    if ampm == 'am' and hour == 12:
        hour = 0

    months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
    month_num = months.get(month_str.lower()[:3], datetime.now().month)

    now = datetime.now()
    target = now.replace(month=month_num, day=day, hour=hour, minute=minute, second=30, microsecond=0)

    if now >= target:
        target += timedelta(days=1)

    return int((target - now).total_seconds())


def read_agent_prompt_from_file():
    """Belirtilen prompt dosyasını okur ve içeriğini doğrular."""
    if not os.path.exists(PROMPT_FILE_NAME):
        # Kullanıcıya kolaylık olsun diye dosya yoksa otomatik şablon oluşturuyoruz
        with open(PROMPT_FILE_NAME, "w", encoding="utf-8") as f:
            f.write("/loop Sen kıdemli bir autonomous software engineer'sin.\n\nKurallarını buraya yaz...")
        print(f"📁 [DOSYA] '{PROMPT_FILE_NAME}' bulunamadı. Boş bir şablon oluşturuldu!")
        print(f"👉 Lütfen '{PROMPT_FILE_NAME}' dosyasının içini doldurup programı tekrar çalıştırın.")
        sys.exit()

    with open(PROMPT_FILE_NAME, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"❌ [HATA] '{PROMPT_FILE_NAME}' dosyasının içi tamamen boş!")
        sys.exit()

    return content


def run_autonomous_agent_loop():
    print("=" * 60)
    print("🤖 CLAUDE AUTONOMOUS AGENT FILE-BASED ENGINE STARTED")
    print("🛡️  Tüm süreç imleç konumundan ve pencerelerden bağımsız yürütülür.")
    print("=" * 60)

    # Promptu doğrudan text dosyasından çekiyoruz
    agent_prompt = read_agent_prompt_from_file()
    print(f"✅ [BAŞARILI] '{PROMPT_FILE_NAME}' başarıyla yüklendi. (Karakter Sayısı: {len(agent_prompt)})")

    is_first_run = True

    while True:
        if is_first_run:
            cmd_command = f'start "Claude Ajan Oturumu" cmd /c "claude -p \\"{agent_prompt}\\" --dangerously-skip-permissions"'
            is_first_run = False
        else:
            cmd_command = 'start "Claude Ajan Oturumu" cmd /c "claude -p \\"continue\\" --continue --dangerously-skip-permissions"'

        print(f"\n🚀 [AKIŞ] Canlı Ajan ekranı fırlatılıyor...")
        subprocess.Popen(cmd_command, shell=True)

        time.sleep(8)

        time_data = get_quota_and_reset_time()

        if time_data:
            month_str, day, hour, minute, ampm = time_data
            sleep_duration = calculate_sleep_seconds(month_str, day, hour, minute, ampm)

            print(f"\n⚠️  [LİMİT DETAYI] Sınır %100 Dolu. Sıfırlanma Zamanı: {month_str} {day}, {hour}:{minute:02d}{ampm}")
            print(f"💤 [PUSU] {sleep_duration} saniye boyunca DERİN UYKUYA GEÇİLİYOR (Sıfır İstek)...")

            if sleep_duration > 0:
                time.sleep(sleep_duration)

            print("\n⏰ [UYANIŞ] Süre doldu! Sunucu kilitleri açıldı. Ajan canlandırılıyor...")
        else:
            print("🟢 [DURUM] Şu an limit algılanamadı veya ajan aktif çalışıyor. 10 dakika beklenecek...")
            time.sleep(600)


if __name__ == "__main__":
    try:
        run_autonomous_agent_loop()
    except KeyboardInterrupt:
        print("\n👋 [ÇIKIŞ] Otomasyon kullanıcı tarafından durduruldu. İyi çalışmalar!")
