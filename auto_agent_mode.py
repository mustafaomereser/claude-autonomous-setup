import sys
import os
import base64
import time
import subprocess
import re
import ctypes
import ctypes.wintypes as wt
from datetime import datetime

import threading
import psutil

if sys.platform == "win32":
    ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    ORANGE = "\033[38;5;208m"


def c(color, text): return f"{color}{text}{C.RESET}"


def log(msg):
    ts = c(C.GRAY, f"[{datetime.now().strftime('%H:%M:%S')}]")
    print(f"{ts} {msg}")


# ── Clipboard (uzun prompt için güvenli yapıştırma) ───────────────────────────

_k32 = ctypes.windll.kernel32
_u32 = ctypes.windll.user32


def clipboard_set(text):
    import pyperclip
    pyperclip.copy(text)


# ── Terminal penceresi bulma ──────────────────────────────────────────────────

def _terminal_hwnd(claude_pid):
    """claude.exe → parent zincirini tırmanarak görünür pencereyi bul."""
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


def focus_window(hwnd):
    _u32.ShowWindow(hwnd, 9)   # SW_RESTORE
    _u32.SetForegroundWindow(hwnd)
    time.sleep(0.5)


# ── Claude başlatma ───────────────────────────────────────────────────────────

PROMPT_FILE = "prompt.txt"
LOG_FILE = "agent.log"
DONE_MARKER = "### AGENT_TASK_COMPLETED ###"
CLAUDE_START_WAIT = 6   # saniye — claude UI'sinin yüklenmesini bekle


def read_prompt():
    try:
        with open(PROMPT_FILE, encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            log(c(C.RED, f"'{PROMPT_FILE}' boş."))
            return None
        return content
    except FileNotFoundError:
        log(c(C.RED, f"'{PROMPT_FILE}' bulunamadı."))
        return None


def _all_claude_pids():
    pids = set()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info["name"] and p.info["name"].lower() == "claude.exe":
                pids.add(p.info["pid"])
        except Exception:
            pass
    return pids


def launch_claude():
    """Yeni bir terminalde claude açar (Start-Transcript ile log'a yazar), yeni PID'i döndürür."""
    before = _all_claude_pids()

    # Log dosyasını sıfırla
    open(LOG_FILE, "w", encoding="utf-8").close()

    cwd = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
    log_abs = os.path.join(cwd, LOG_FILE)

    # Start-Transcript: piping yok → claude TTY modunda kalır
    ps_cmd = (
        f'Set-Location \'{cwd}\'; '
        f'Start-Transcript -Path \'{log_abs}\'; '
        f'claude; '
        f'Stop-Transcript'
    )
    # -EncodedCommand ile tırnak/semicolon sorununu tamamen ortadan kaldır
    enc = base64.b64encode(ps_cmd.encode("utf-16-le")).decode("ascii")

    starters = [
        (["wt", "new-tab", "--startingDirectory", cwd, "--", "powershell", "-NoExit", "-EncodedCommand", enc], {}),
        (["wt", "-w", "new", "new-tab", "--startingDirectory", cwd, "--", "powershell", "-NoExit", "-EncodedCommand", enc], {}),
        (["powershell", "-NoExit", "-EncodedCommand", enc], {"creationflags": subprocess.CREATE_NEW_CONSOLE, "cwd": cwd}),
    ]

    started = False
    for cmd, kwargs in starters:
        try:
            subprocess.Popen(cmd, **kwargs)
            started = True
            break
        except Exception as e:
            log(c(C.YELLOW, f"Starter denendi: {e}"))

    if not started:
        log(c(C.RED, "claude başlatılamadı."))
        return None

    log(c(C.CYAN, "claude başlatıldı, PID bekleniyor..."))
    for _ in range(20):
        time.sleep(0.5)
        new_pids = _all_claude_pids() - before
        if new_pids:
            pid = list(new_pids)[0]
            log(c(C.GREEN, f"claude PID: {pid}"))
            return pid

    log(c(C.RED, "Yeni claude PID'i bulunamadı."))
    return None


def send_prompt(hwnd, text, pyautogui):
    """Auto mode aç (3x Shift+Tab), clipboard'dan yapıştır, Enter."""
    focus_window(hwnd)

    # Auto mode: 3x Shift+Tab
    for _ in range(3):
        pyautogui.hotkey("shift", "tab")
        time.sleep(0.2)
    time.sleep(0.3)

    clipboard_set(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyautogui.press("enter")


# ── /usage sorgulama ──────────────────────────────────────────────────────────

SESSION_RE = re.compile(
    r"current session:\s*(\d+)%\s*used\s*[·•]\s*resets\s+([A-Za-z]+)\s+(\d+),\s*(\d+)(?::(\d+))?\s*(am|pm)",
    re.IGNORECASE,
)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
)}


def usage_sorgu():
    """
    Döndürür: (reset_datetime | None, pct: int)
    None → limit dolu değil
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

    pct = int(m.group(1))
    ay = MONTHS.get(m.group(2).lower()[:3], datetime.now().month)
    gun = int(m.group(3))
    saat = int(m.group(4))
    dak = int(m.group(5)) if m.group(5) else 0
    ampm = m.group(6).lower()

    if ampm == "pm" and saat < 12:
        saat += 12
    if ampm == "am" and saat == 12:
        saat = 0

    now = datetime.now()
    hedef = now.replace(month=ay, day=gun, hour=saat, minute=dak, second=30, microsecond=0)
    if hedef < now:
        hedef = hedef.replace(year=now.year + 1)

    if pct < 100:
        return None, pct

    return hedef, pct


# ── Log izleyici ─────────────────────────────────────────────────────────────

def start_log_watcher(stop_event, done_event):
    """agent.log'u tail eder, DONE_MARKER görününce done_event'i set eder."""
    def _watch():
        # Dosya oluşana kadar bekle
        log(c(C.GRAY, f"Log watcher başladı — '{LOG_FILE}' bekleniyor..."))
        while not stop_event.is_set():
            if os.path.exists(LOG_FILE):
                break
            time.sleep(0.5)

        # PowerShell 5.1 Start-Transcript UTF-16 LE yazar; utf-16 BOM'u otomatik çözer
        encodings = ["utf-16", "utf-8-sig", "utf-8"]
        f = None
        for enc in encodings:
            try:
                f = open(LOG_FILE, "r", encoding=enc, errors="ignore")
                log(c(C.GRAY, f"Log watcher açıldı (encoding: {enc})."))
                break
            except Exception:
                pass

        if f is None:
            log(c(C.RED, "Log dosyası açılamadı."))
            return

        lines_read = 0
        with f:
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                lines_read += 1
                if lines_read % 20 == 0:
                    log(c(C.GRAY, f"[log] {lines_read} satır okundu..."))
                if DONE_MARKER in line:
                    log(c(C.GREEN + C.BOLD, "✓ AGENT_TASK_COMPLETED algılandı — izleme durduruluyor."))
                    done_event.set()
                    return

    t = threading.Thread(target=_watch, daemon=True)
    t.start()
    return t


# ── Ana döngü ─────────────────────────────────────────────────────────────────

POLL_INTERVAL = 60    # limit yokken kaç saniyede bir sorgulansın
RECHECK_AFTER = 15    # continue sonrası kaç saniye beklensin
IDLE_THRESHOLD = 45    # pct kaç tur üst üste aynı kalırsa görev bitti sayılır


def main():
    try:
        import pyautogui
    except ImportError:
        print(c(C.RED, "pip install pyautogui"))
        sys.exit(1)

    prompt = read_prompt()
    if not prompt:
        sys.exit(1)

    print(c(C.CYAN + C.BOLD, "\nClaude Auto-Agent"))
    print(c(C.GRAY, f"Prompt: {PROMPT_FILE} ({len(prompt)} karakter) — Ctrl+C ile durdur\n"))

    # Claude'u aç
    pid = launch_claude()
    if not pid:
        sys.exit(1)

    # UI yüklensin
    log(c(C.GRAY, f"{CLAUDE_START_WAIT}s bekleniyor (UI yüklensin)..."))
    time.sleep(CLAUDE_START_WAIT)

    # Pencereyi bul
    hwnd = _terminal_hwnd(pid)
    if not hwnd:
        log(c(C.RED, "Terminal penceresi bulunamadı."))
        sys.exit(1)

    # Prompt'u gönder
    log(c(C.CYAN, "Prompt gönderiliyor..."))
    send_prompt(hwnd, prompt, pyautogui)
    log(c(C.GREEN, "Prompt gönderildi. İzleme başlıyor...\n"))

    # Log watcher başlat
    stop_event = threading.Event()
    done_event = threading.Event()
    start_log_watcher(stop_event, done_event)

    # İzleme döngüsü
    last_pct = None
    same_pct_count = 0

    while True:
        # Görev tamamlandı mı? (log marker)
        if done_event.is_set():
            stop_event.set()
            break

        time.sleep(POLL_INTERVAL)

        if done_event.is_set():
            stop_event.set()
            break

        # claude hâlâ çalışıyor mu?
        if pid not in _all_claude_pids():
            log(c(C.YELLOW, "claude.exe kapandı."))
            stop_event.set()
            break

        reset_at, pct = usage_sorgu()

        if reset_at is None:
            # Token değişmedi mi say
            if pct == last_pct:
                same_pct_count += 1
                log(c(C.GRAY, f"Limit yok (%{pct}, {same_pct_count}/{IDLE_THRESHOLD} tur sabit)."))
                if same_pct_count >= IDLE_THRESHOLD:
                    log(c(C.GREEN + C.BOLD, f"✓ Token {IDLE_THRESHOLD} tur değişmedi — görev tamamlandı sayılıyor."))
                    stop_event.set()
                    break
            else:
                same_pct_count = 0
                log(c(C.GRAY, f"Limit yok (%{pct}). {POLL_INTERVAL}s sonra tekrar."))
            last_pct = pct
            continue

        bekle = max(0, int((reset_at - datetime.now()).total_seconds()))
        log(c(C.ORANGE, f"Limit dolu (%{pct}). Reset: {reset_at.strftime('%d %b %H:%M:%S')} — {bekle}s bekleniyor."))

        while True:
            if done_event.is_set():
                break
            kalan = int((reset_at - datetime.now()).total_seconds())
            if kalan <= 0:
                break
            log(c(C.GRAY, f"  {kalan}s kaldı..."))
            time.sleep(min(60, kalan))

        if done_event.is_set():
            stop_event.set()
            break

        hwnd = _terminal_hwnd(pid)
        if not hwnd:
            log(c(C.RED, "Terminal penceresi kayboldu."))
            stop_event.set()
            break

        log(c(C.GREEN, "Süre doldu, 'continue' gönderiliyor."))
        focus_window(hwnd)
        pyautogui.typewrite("continue", interval=0.05)
        pyautogui.press("enter")
        log(c(C.GREEN, "continue gönderildi."))

        # Continue sonrası token değişeceğinden sayacı sıfırla
        same_pct_count = 0
        last_pct = None

        time.sleep(RECHECK_AFTER)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(C.GRAY, "\nDurduruldu."))
