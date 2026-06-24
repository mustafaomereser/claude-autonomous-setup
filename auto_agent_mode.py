import sys
import os
import base64
import time
import subprocess
import re
import json
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

PROMPT_FILE = "prompt.md"
LOG_FILE = "agent.log"
DONE_MARKER = "### AGENT_TASK_COMPLETED ###"
RESUME_MARKER = "### AGENT_TASK_STARTED ###"   # Claude yeni göreve başlarken bunu yazdığında sayma döngüsüne dön
CLAUDE_START_WAIT = 6   # saniye — claude UI'sinin yüklenmesini bekle


def _claude_projects_dir(cwd):
    """cwd → ~/.claude/projects/<slug> yolunu döndürür."""
    slug = cwd.replace(":", "-").replace("\\", "-").replace("/", "-").replace(".", "-")
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", slug)


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
    """Yeni bir terminalde claude açar; (pid, projects_dir, existing_jsonls) döndürür."""
    before = _all_claude_pids()
    cwd = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))

    # Mevcut JSONL dosyalarını başlatmadan önce kaydet
    projects_dir = _claude_projects_dir(cwd)
    try:
        existing_jsonls = set(os.listdir(projects_dir))
    except FileNotFoundError:
        existing_jsonls = set()

    ps_cmd = f'Set-Location \'{cwd}\'; claude'
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
        return None, None, None

    log(c(C.CYAN, "claude başlatıldı, PID bekleniyor..."))
    for _ in range(20):
        time.sleep(0.5)
        new_pids = _all_claude_pids() - before
        if new_pids:
            pid = list(new_pids)[0]
            log(c(C.GREEN, f"claude PID: {pid}"))
            return pid, projects_dir, existing_jsonls

    log(c(C.RED, "Yeni claude PID'i bulunamadı."))
    return None, None, None


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

def _agent_log(msg):
    """agent.log'a timestamp ile satır yaz."""
    ts = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _fmt_tokens(usage):
    """usage dict'inden okunabilir token özeti üret."""
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cache_r = usage.get("cache_read_input_tokens", 0)
    cache_w = usage.get("cache_creation_input_tokens", 0)
    total = inp + out + cache_r + cache_w
    parts = [f"in={inp}", f"out={out}"]
    if cache_r:
        parts.append(f"cache_read={cache_r}")
    if cache_w:
        parts.append(f"cache_write={cache_w}")
    parts.append(f"total={total}")
    return "  ".join(parts)


def start_log_watcher(stop_event, done_event, resume_event, projects_dir, existing_jsonls):
    """
    Yeni JSONL oturum dosyasını tail eder; her assistant mesajını agent.log'a yazar.
    DONE_MARKER görününce done_event, RESUME_MARKER görününce resume_event set eder.
    """
    def _watch():
        open(LOG_FILE, "w", encoding="utf-8").close()
        _agent_log("=== OTURUM BAŞLADI ===")
        log(c(C.GRAY, "JSONL watcher başladı — yeni oturum dosyası bekleniyor..."))

        session_file = None
        while not stop_event.is_set():
            try:
                current = set(os.listdir(projects_dir))
            except Exception:
                time.sleep(1)
                continue
            new_files = [f for f in (current - existing_jsonls) if f.endswith(".jsonl")]
            if new_files:
                session_file = os.path.join(
                    projects_dir,
                    max(new_files, key=lambda f: os.path.getmtime(os.path.join(projects_dir, f)))
                )
                _agent_log(f"Oturum: {os.path.basename(session_file)}")
                log(c(C.GRAY, f"Oturum dosyası: {os.path.basename(session_file)}"))
                break
            time.sleep(1)

        if not session_file:
            return

        msg_count = 0
        with open(session_file, "r", encoding="utf-8", errors="ignore") as f:
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue

                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                obj_type = obj.get("type")

                if obj_type == "assistant":
                    msg_count += 1
                    msg = obj.get("message", {})
                    model = msg.get("model", "?")
                    usage = msg.get("usage", {})
                    stop_reason = msg.get("stop_reason", "?")

                    texts = []
                    tool_calls = []
                    for block in msg.get("content", []):
                        btype = block.get("type")
                        if btype == "text":
                            t = block.get("text", "").strip()
                            if t:
                                texts.append(t)
                        elif btype == "tool_use":
                            tool_calls.append(block.get("name", "?"))

                    _agent_log(f"── MESAJ #{msg_count} [{model}] stop={stop_reason} ──")
                    _agent_log(f"   Tokenlar: {_fmt_tokens(usage)}")
                    if texts:
                        for t in texts:
                            preview = t[:300].replace("\n", " ")
                            _agent_log(f"   Yanıt: {preview}")
                    if tool_calls:
                        _agent_log(f"   Araçlar: {', '.join(tool_calls)}")

                    tok_str = f"in={usage.get('input_tokens',0)} out={usage.get('output_tokens',0)}"
                    log(c(C.GRAY, f"[{model}] #{msg_count} {tok_str}  stop={stop_reason}"))

                    # Sadece asistan yanıtlarında marker'ları ara (kullanıcı prompt'unu atla)
                    for t in texts:
                        if DONE_MARKER in t:
                            _agent_log(f"=== {DONE_MARKER} ===")
                            log(c(C.GREEN + C.BOLD, "✓ AGENT_TASK_COMPLETED algılandı."))
                            done_event.set()
                        if RESUME_MARKER in t:
                            _agent_log(f"=== {RESUME_MARKER} ===")
                            log(c(C.GREEN + C.BOLD, "✓ AGENT_TASK_STARTED algılandı — sayma döngüsüne dönülüyor."))
                            resume_event.set()

    t = threading.Thread(target=_watch, daemon=True)
    t.start()
    return t


def start_resume_watcher(resume_event, projects_dir):
    """
    Backlog modunda çalışır: mevcut JSONL'ın sonunu VE yeni oluşan JSONL dosyalarını izler.
    RESUME_MARKER görününce resume_event set eder.
    """
    def _watch():
        # Başlangıçtaki dosya listesini kaydet (yeni dosyaları tespit için)
        try:
            known_files = set(os.listdir(projects_dir))
        except Exception:
            known_files = set()

        # Mevcut en güncel JSONL'ın sonuna konumlan
        current_fh = None
        try:
            jsonls = [f for f in known_files if f.endswith(".jsonl")]
            if jsonls:
                fname = max(jsonls, key=lambda f: os.path.getmtime(os.path.join(projects_dir, f)))
                current_fh = open(os.path.join(projects_dir, fname), "r", encoding="utf-8", errors="ignore")
                current_fh.seek(0, 2)
                log(c(C.GRAY, f"Resume watcher: {fname}"))
        except Exception:
            pass

        def _check_line(line):
            try:
                obj = json.loads(line)
            except Exception:
                return False
            if obj.get("type") == "assistant":
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") == "text" and RESUME_MARKER in block.get("text", ""):
                        _agent_log(f"=== {RESUME_MARKER} (resume watcher) ===")
                        log(c(C.GREEN + C.BOLD, "✓ AGENT_TASK_STARTED algılandı (resume watcher)."))
                        resume_event.set()
                        return True
            return False

        while not resume_event.is_set():
            # Mevcut dosyada yeni satır var mı?
            if current_fh:
                line = current_fh.readline()
                if line:
                    if _check_line(line):
                        current_fh.close()
                        return
                    continue  # daha fazla satır olabilir, sleep'e geçme

            # Yeni JSONL dosyası oluştu mu?
            try:
                all_files = set(os.listdir(projects_dir))
            except Exception:
                time.sleep(0.5)
                continue

            new_jsonls = [f for f in (all_files - known_files) if f.endswith(".jsonl")]
            if new_jsonls:
                fname = max(new_jsonls, key=lambda f: os.path.getmtime(os.path.join(projects_dir, f)))
                log(c(C.GRAY, f"Resume watcher: yeni dosya → {fname}"))
                if current_fh:
                    current_fh.close()
                current_fh = open(os.path.join(projects_dir, fname), "r", encoding="utf-8", errors="ignore")
                known_files = all_files
                continue

            time.sleep(0.5)

        if current_fh:
            current_fh.close()

    t = threading.Thread(target=_watch, daemon=True)
    t.start()
    return t


# ── Ana döngü ─────────────────────────────────────────────────────────────────

POLL_INTERVAL = 60    # limit yokken kaç saniyede bir sorgulansın
RECHECK_AFTER = 15    # continue sonrası kaç saniye beklensin
IDLE_THRESHOLD = 30    # pct kaç tur üst üste aynı kalırsa görev bitti sayılır
BACKLOG_FILE = os.path.join(".ai", "backlog.md")
BACKLOG_MSG = "Backlog güncellendi. Dosyayı oku ve kaldığın yerden devam et."
BACKLOG_POLL = 15    # backlog izleme aralığı (saniye) — resume_event de bu aralıkta kontrol edilir


def _backlog_mtime():
    try:
        return os.path.getmtime(BACKLOG_FILE)
    except OSError:
        return 0


def run_monitoring_loop(pid, pyautogui, done_event, resume_event, stop_event):
    """
    Token kullanımını izler, limit dolunca 'continue' gönderir.
    done_event veya resume_event set edilince durur.
    pid kapanınca durur.
    """
    last_pct = None
    same_pct_count = 0

    while True:
        if done_event.is_set() or resume_event.is_set():
            stop_event.set()
            return

        time.sleep(POLL_INTERVAL)

        if done_event.is_set() or resume_event.is_set():
            stop_event.set()
            return

        if pid not in _all_claude_pids():
            log(c(C.YELLOW, "claude.exe kapandı."))
            stop_event.set()
            return

        reset_at, pct = usage_sorgu()

        if reset_at is None:
            if pct == last_pct:
                same_pct_count += 1
                log(c(C.GRAY, f"Limit yok (%{pct}, {same_pct_count}/{IDLE_THRESHOLD} tur sabit)."))
                if same_pct_count >= IDLE_THRESHOLD:
                    log(c(C.GREEN + C.BOLD, f"✓ Token {IDLE_THRESHOLD} tur değişmedi — görev tamamlandı sayılıyor."))
                    stop_event.set()
                    return
            else:
                same_pct_count = 0
                log(c(C.GRAY, f"Limit yok (%{pct}). {POLL_INTERVAL}s sonra tekrar."))
            last_pct = pct
            continue

        bekle = max(0, int((reset_at - datetime.now()).total_seconds()))
        log(c(C.ORANGE, f"Limit dolu (%{pct}). Reset: {reset_at.strftime('%d %b %H:%M:%S')} — {bekle}s bekleniyor."))

        while True:
            if done_event.is_set() or resume_event.is_set():
                break
            kalan = int((reset_at - datetime.now()).total_seconds())
            if kalan <= 0:
                break
            log(c(C.GRAY, f"  {kalan}s kaldı..."))
            time.sleep(min(60, kalan))

        if done_event.is_set() or resume_event.is_set():
            stop_event.set()
            return

        hwnd = _terminal_hwnd(pid)
        if not hwnd:
            log(c(C.RED, "Terminal penceresi kayboldu."))
            stop_event.set()
            return

        log(c(C.GREEN, "Süre doldu, 'continue' gönderiliyor."))
        focus_window(hwnd)
        pyautogui.typewrite("continue", interval=0.05)
        pyautogui.press("enter")
        log(c(C.GREEN, "continue gönderildi."))

        same_pct_count = 0
        last_pct = None
        time.sleep(RECHECK_AFTER)


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
    pid, projects_dir, existing_jsonls = launch_claude()
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

    # ── İzleme döngüsü (ilk görev) ───────────────────────────────────────────
    stop_event = threading.Event()
    done_event = threading.Event()
    resume_event = threading.Event()
    start_log_watcher(stop_event, done_event, resume_event, projects_dir, existing_jsonls)
    run_monitoring_loop(pid, pyautogui, done_event, resume_event, stop_event)

    # ── Backlog izleme ────────────────────────────────────────────────────────
    log(c(C.CYAN + C.BOLD, "Backlog izleniyor... (.ai/backlog.md)"))
    last_mtime = _backlog_mtime()

    # Backlog moduna ilk girişte hemen resume watcher başlat
    resume_event = threading.Event()
    start_resume_watcher(resume_event, projects_dir)

    while True:
        time.sleep(BACKLOG_POLL)

        if pid not in _all_claude_pids():
            log(c(C.YELLOW, "claude.exe kapandı, backlog izleme durdu."))
            break

        # resume_event: Claude custom prompt'tan RESUME_MARKER çıkardı
        new_task_from_resume = resume_event.is_set()
        # backlog.md değişti mi?
        mtime = _backlog_mtime()
        new_task_from_backlog = mtime > last_mtime

        if not new_task_from_resume and not new_task_from_backlog:
            # Hiç olay yok; resume watcher çalışıyor mu kontrol et (ilk turda başlat)
            continue

        if new_task_from_resume:
            log(c(C.CYAN, "RESUME_MARKER algılandı — yeni görev izleniyor."))

        if new_task_from_backlog:
            last_mtime = mtime
            log(c(C.CYAN, "Backlog değişti, claude'a bildiriliyor..."))
            hwnd = _terminal_hwnd(pid)
            if hwnd:
                focus_window(hwnd)
                clipboard_set(BACKLOG_MSG)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)
                pyautogui.press("enter")
                log(c(C.GREEN, "Backlog mesajı gönderildi."))
            else:
                log(c(C.RED, "Terminal penceresi bulunamadı."))

        # Yeni izleme döngüsü başlat
        try:
            existing_jsonls = set(os.listdir(projects_dir))
        except Exception:
            existing_jsonls = set()

        stop_event = threading.Event()
        done_event = threading.Event()
        resume_event = threading.Event()
        start_log_watcher(stop_event, done_event, resume_event, projects_dir, existing_jsonls)

        log(c(C.CYAN, "Yeni görev izleniyor..."))
        run_monitoring_loop(pid, pyautogui, done_event, resume_event, stop_event)

        # Döngü bitti; backlog beklemeye devam et
        log(c(C.CYAN + C.BOLD, "Backlog izleniyor..."))
        last_mtime = _backlog_mtime()

        # Yeni resume watcher başlat (bir önceki görevin JSONL'ının sonundan izle)
        resume_event = threading.Event()
        start_resume_watcher(resume_event, projects_dir)
        log(c(C.GRAY, "Resume watcher yeniden başlatıldı."))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(C.GRAY, "\nDurduruldu."))
