import sys
import time
import subprocess
import re
from datetime import datetime

import psutil

if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    ORANGE = "\033[38;5;208m"

def c(color, text): return f"{color}{text}{C.RESET}"

def log(msg):
    ts = c(C.GRAY, f"[{datetime.now().strftime('%H:%M:%S')}]")
    print(f"{ts} {msg}")


# ── Claude.exe algılama ──────────────────────────────────────────────────────

def claude_pid():
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "claude.exe":
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


# ── /usage sorgulama ─────────────────────────────────────────────────────────

# "Current session: 29% used · resets Jun 23, 9am (Europe/Istanbul)"
SESSION_RE = re.compile(
    r'current session:\s*(\d+)%\s*used\s*[·•]\s*resets\s+([A-Za-z]+)\s+(\d+),\s*(\d+)(?::(\d+))?\s*(am|pm)',
    re.IGNORECASE,
)
MONTHS = {m: i for i, m in enumerate(
    ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"], 1
)}

def usage_sorgu():
    """
    'claude -p /usage' çıktısından oturum kullanım yüzdesi ve reset zamanını okur.
    Döndürür: (datetime | None, pct: int)
      - datetime None ise limit dolu değil
    """
    try:
        proc = subprocess.run(
            ["claude", "-p", "/usage"],
            capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=15,
        )
        out = proc.stdout + proc.stderr
    except Exception:
        return None, 0

    m = SESSION_RE.search(out)

    if not m:
        return None, 0

    pct  = int(m.group(1))
    ay   = MONTHS.get(m.group(2).lower()[:3], datetime.now().month)
    gun  = int(m.group(3))
    saat = int(m.group(4))
    dak  = int(m.group(5)) if m.group(5) else 0
    ampm = m.group(6).lower()

    if ampm == "pm" and saat < 12:
        saat += 12
    if ampm == "am" and saat == 12:
        saat = 0

    now   = datetime.now()
    hedef = now.replace(month=ay, day=gun, hour=saat, minute=dak, second=30, microsecond=0)
    if hedef < now:
        hedef = hedef.replace(year=now.year + 1)

    if pct < 100:
        return None, pct  # Limit dolu değil

    return hedef, pct


# ── pyautogui enjeksiyonu ────────────────────────────────────────────────────

import ctypes
import ctypes.wintypes as wt

_u32 = ctypes.windll.user32

def _terminal_hwnd(claude_pid):
    """claude.exe process ağacını yukarı tırman, görünür pencere sahibini bul."""
    ENWP = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def window_of(pid):
        found = [None]
        def cb(hwnd, _):
            if _u32.IsWindowVisible(hwnd):
                wpid = wt.DWORD()
                _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value == pid:
                    found[0] = hwnd
                    return False
            return True
        _u32.EnumWindows(ENWP(cb), 0)
        return found[0]

    try:
        proc = psutil.Process(claude_pid)
        visited = set()
        while proc and proc.pid not in visited:
            visited.add(proc.pid)
            hwnd = window_of(proc.pid)
            if hwnd:
                return hwnd
            proc = proc.parent()
    except Exception:
        pass
    return None


def claude_continue(pid, mesaj="continue"):
    try:
        import pyautogui
    except ImportError:
        log(c(C.RED, "pyautogui bulunamadı → pip install pyautogui"))
        return False

    hwnd = _terminal_hwnd(pid)
    if not hwnd:
        log(c(C.RED, f"PID {pid} için terminal penceresi bulunamadı."))
        return False

    log(c(C.CYAN, f"Terminal penceresi bulundu (HWND {hwnd}), '{mesaj}' yazılıyor..."))

    _u32.ShowWindow(hwnd, 9)        # SW_RESTORE
    _u32.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    pyautogui.typewrite(mesaj, interval=0.05)
    pyautogui.press("enter")

    log(c(C.GREEN, "Gönderildi."))
    return True


# ── Ana döngü ────────────────────────────────────────────────────────────────

POLL_INTERVAL   = 60     # saniye — limit yokken ne sıklıkta sorgulansın
RECHECK_AFTER   = 15     # continue sonrası kaç saniye beklensin
NO_PROC_WAIT    = 600    # claude.exe yokken bekleme süresi

def main():
    print(c(C.CYAN + C.BOLD, "\nClaude Auto-Continue — PID İzleyici"))
    print(c(C.GRAY, "Ctrl+C ile durdurulur.\n"))

    while True:
        pid = claude_pid()
        if not pid:
            log(c(C.YELLOW, f"claude.exe bulunamadı. {NO_PROC_WAIT}s sonra tekrar aranacak."))
            time.sleep(NO_PROC_WAIT)
            continue

        log(c(C.GREEN, f"claude.exe aktif (PID {pid}) — /usage sorgulanıyor..."))
        reset_at, pct = usage_sorgu()

        if reset_at is None:
            log(c(C.GRAY, f"Limit yok (%{pct} kullanıldı). {POLL_INTERVAL}s sonra tekrar kontrol."))
            time.sleep(POLL_INTERVAL)
            continue

        bekle = max(0, int((reset_at - datetime.now()).total_seconds()))
        log(c(C.ORANGE, f"Limit dolu (%{pct}). Reset: {reset_at.strftime('%d %b %H:%M:%S')} — {bekle}s bekleniyor."))

        if bekle > 0:
            # Her 60s'de bir kalan süreyi göster
            while True:
                kalan = int((reset_at - datetime.now()).total_seconds())
                if kalan <= 0:
                    break
                log(c(C.GRAY, f"  {kalan}s kaldı..."))
                time.sleep(min(60, kalan))

        log(c(C.GREEN, "Süre doldu, devam mesajı gönderiliyor."))
        claude_continue(pid, "continue")

        log(c(C.GRAY, f"{RECHECK_AFTER}s sonra tekrar kontrol."))
        time.sleep(RECHECK_AFTER)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(C.GRAY, "\nDurduruldu."))
