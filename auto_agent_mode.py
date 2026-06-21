import json
import os
import re
import sys
import time
import subprocess
from datetime import datetime

# Windows'ta ANSI renk desteğini etkinleştir
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    ORANGE  = "\033[38;5;208m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"

def c(color, text):
    return f"{color}{text}{C.RESET}"

PROMPT_FILE    = "prompt.txt"
LOG_FILE       = "agent_output.log"
DONE_MARKER    = "### AGENT_TASK_COMPLETED ###"
AI_DIR         = ".ai"
CONTEXT_FILES  = ["rules.md", "backlog.md", "progress.md", "decisions.md"]



_log_file = None

def _get_log():
    global _log_file
    if _log_file is None:
        _log_file = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    return _log_file


def emit(text):
    """Her ikisine de yaz — log dosyası her write'ta flush'lanır (buffering=1)."""
    sys.stdout.write(text)
    sys.stdout.flush()
    _get_log().write(text)


def log(msg):
    ts = c(C.GRAY, f"[{datetime.now().strftime('%H:%M:%S')}]")
    emit(f"{ts} {msg}\n")


def _compress(fname, content):
    lines = content.splitlines()
    if fname == "backlog.md":
        filtered = []
        skip = False
        for l in lines:
            if re.match(r'\s*-\s*\[x\]', l, re.I):
                skip = True
                continue
            if skip:
                # Boş satır veya girintili satır → hâlâ devam içeriği, atla
                if l == "" or re.match(r'\s+\S', l):
                    continue
                # Girintisiz yeni içerik → bu [x] bloğu bitti
                skip = False
            filtered.append(l)
        lines = filtered
    lines = [l.rstrip() for l in lines]
    lines = [l for l in lines if not re.fullmatch(r'[-=]{3,}', l)]
    result, prev_blank = [], False
    for l in lines:
        blank = l == ""
        if blank and prev_blank:
            continue
        result.append(l)
        prev_blank = blank
    return "\n".join(result).strip()


def build_context():
    parts = []
    for fname in CONTEXT_FILES:
        path = os.path.join(AI_DIR, fname)
        if not os.path.exists(path):
            continue
        content = open(path, encoding="utf-8").read().strip()
        if content:
            compressed = _compress(fname, content)
            if compressed:
                parts.append(f"### {fname}\n{compressed}")
    if not parts:
        return ""
    return "\n\n---\n# MEVCUT BAĞLAM (.ai/ dosyaları)\n\n" + "\n\n".join(parts)


def read_prompt():
    if not os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(
                "Sen kıdemli bir autonomous software engineer'sin.\n\n"
                "Görevini buraya yaz...\n\n"
                f"Görevi tamamen bitirdiğinde terminale '{DONE_MARKER}' yaz."
            )
        log(f"'{PROMPT_FILE}' bulunamadi, sablon olusturuldu. Doldurup tekrar calistir.")
        sys.exit(1)

    content = open(PROMPT_FILE, encoding="utf-8").read().strip()
    if not content:
        log(f"'{PROMPT_FILE}' bos!")
        sys.exit(1)
    return content


def _tool_detail(inp):
    """Tool input dict'ten kısa açıklama üret."""
    for key in ("file_path", "path", "pattern", "command", "query", "description"):
        v = inp.get(key)
        if v:
            return str(v)[:120]
    return ""


def handle_event(obj):
    """
    JSON event'i okunabilir metne çevirir.
    Döndürür: (metin_veya_None, limit_vurdu:bool, resets_at_ts:int|None)
    """
    t   = obj.get("type")
    sub = obj.get("subtype", "")

    # --- Asistan yanıtı ---
    if t == "assistant":
        msg     = obj.get("message", {})
        content = msg.get("content", [])
        usage   = msg.get("usage", {})
        parts   = []
        for block in content:
            bt = block.get("type")
            if bt == "text":
                text = block["text"].strip()
                if text:
                    parts.append(c(C.WHITE, text) + "\n")
            elif bt == "tool_use":
                name   = block.get("name", "?")
                detail = _tool_detail(block.get("input", {}))
                call   = f"{c(C.YELLOW, '->')} {c(C.BOLD, name)}{c(C.DIM, f'({detail})')}" if detail else f"{c(C.YELLOW, '->')} {c(C.BOLD, name)}{c(C.DIM, '()')}"
                parts.append(f"  {call}\n")
            elif bt == "thinking":
                pass
        if usage:
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            if inp or out:
                parts.append(f"  {c(C.GRAY, f'[in:{inp:,} out:{out:,}]')}\n")
        return "".join(parts) or None, False, None

    # --- Tool sonucu (user mesajı olarak gelir) ---
    if t == "user":
        result = obj.get("tool_use_result", {})
        if not isinstance(result, dict):
            return None, False, None
        rtype  = result.get("type", "")
        if rtype == "text":
            finfo = result.get("file")
            if finfo:
                path   = finfo.get("filePath", "")
                nlines = finfo.get("numLines", "?")
                return f"  {c(C.GREEN, '<-')} {c(C.DIM, f'Read({path}) [{nlines} satır]')}\n", False, None
            content = result.get("content", "")
            snippet = str(content)[:80].replace("\n", " ")
            return f"  {c(C.GREEN, '<-')} {c(C.DIM, snippet)}\n", False, None
        if rtype == "error":
            msg = result.get("message", "")
            return f"  {c(C.RED+C.BOLD, '<- ERROR:')} {c(C.RED, msg)}\n", False, None
        if rtype == "base64":
            return f"  {c(C.GREEN, '<-')} {c(C.DIM, '[binary data]')}\n", False, None
        return None, False, None

    # --- Rate limit ---
    if t == "rate_limit_event":
        info   = obj.get("rate_limit_info", {})
        status = info.get("status")
        ts     = info.get("resetsAt")

        # Yüzde hesapla — hangi alan gelirse
        pct = None
        for used_key, limit_key in [
            ("tokensUsed",    "tokensLimit"),
            ("requestsUsed",  "requestsLimit"),
            ("messagesUsed",  "messagesLimit"),
        ]:
            used  = info.get(used_key)
            limit = info.get(limit_key)
            if used is not None and limit:
                pct = int(used / limit * 100)
                break
        pct_str = f" {pct}% kullanıldı" if pct is not None else ""

        if status == "allowed":
            return None, False, None
        if status == "allowed_warning":
            return f"\n{c(C.ORANGE, f'[rate_limit: uyarı{pct_str} — devam ediliyor]')}\n", False, None
        return f"\n{c(C.RED+C.BOLD, f'[rate_limit: bloke{pct_str} — bekleniyor]')}\n", True, ts

    # --- Hata ---
    if t == "error":
        err = obj.get("error", {})
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return f"\n{c(C.RED+C.BOLD, f'[error: {msg}]')}\n", False, None

    # --- Oturum sonu ---
    if t == "result":
        cost = obj.get("total_cost_usd")
        if sub == "error_max_turns":
            return f"\n{c(C.YELLOW, '[max turns]')}\n", False, None
        if cost is not None:
            turns = obj.get("num_turns", "?")
            usage = obj.get("usage", {})
            inp   = usage.get("input_tokens", 0)
            out   = usage.get("output_tokens", 0)
            total = inp + out
            tok_str = f" | {total:,} token (in:{inp:,} out:{out:,})" if total else ""
            return f"\n{c(C.CYAN, f'[tur:{turns} | maliyet:${cost:.2f}{tok_str}]')}\n", False, None

    # --- system/thinking gibi meta eventler: yoksay ---
    return None, False, None


def _get_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def stream_process(cmd, stdin_data=None):
    """
    Komutu çalıştırır, her JSON satırını parse edip anında ekrana basar.
    stdin_data: bytes — prompt shell'e gömülmek yerine stdin'den geçer (newline sorunu yok).
    Döndürür: (tam_metin, limit_hit:bool, resets_at_ts:int|None)
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # bufsize=0 + binary: Windows'ta pipe line-buffer sorunu olmaz
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdin=subprocess.PIPE if stdin_data is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env=env,
    )

    if stdin_data is not None:
        proc.stdin.write(stdin_data)
        proc.stdin.close()

    collected = []
    limit_hit = False
    resets_ts = None

    for raw_bytes in iter(proc.stdout.readline, b""):
        raw = raw_bytes.decode("utf-8", errors="ignore").rstrip("\n")
        if not raw:
            continue

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            emit(raw + "\n")
            collected.append(raw)
            continue

        text, hit, ts = handle_event(obj)

        if text:
            emit(text)
            collected.append(text)

        if hit and not limit_hit:
            limit_hit = True
            resets_ts = ts
            proc.terminate()
            break

    stderr_out = proc.stderr.read().decode("utf-8", errors="ignore").strip()
    if stderr_out:
        emit(f"\n{c(C.RED, '[stderr]')} {c(C.DIM, stderr_out)}\n")
        collected.append(stderr_out)

    proc.wait()
    emit("\n")
    return "".join(collected), limit_hit, resets_ts



def get_reset_datetime(resets_ts=None):
    if resets_ts:
        return datetime.fromtimestamp(resets_ts)
    return None


def main():
    open(LOG_FILE, "w", encoding="utf-8").close()  # sıfırla
    log(c(C.CYAN + C.BOLD, "Agent başlıyor..."))
    prompt = read_prompt()
    log(c(C.CYAN, f"Prompt yüklendi ({len(prompt)} karakter)"))

    context = build_context()
    full_prompt = prompt + context if context else prompt
    log(c(C.CYAN, f"Bağlam enjekte edildi ({len(full_prompt)} karakter)"))

    BACKLOG_PATH = os.path.join(AI_DIR, "backlog.md")
    WAKE_MSG     = "Yeni görevler backlog.md'ye eklendi. Dosyayı oku ve kaldığın yerden devam et.".encode("utf-8")

    use_continue = False
    wake_msg     = b"."
    BASE         = "-p - --output-format stream-json --dangerously-skip-permissions"

    while True:
        if use_continue:
            cmd        = f'claude {BASE} --continue'
            stdin_data = wake_msg
        else:
            cmd        = f'claude {BASE}'
            stdin_data = full_prompt.encode("utf-8")

        use_continue = False
        wake_msg     = b"."

        log(c(C.BLUE, "Oturum başlatılıyor..."))
        output, limit_hit, resets_ts = stream_process(cmd, stdin_data=stdin_data)

        if DONE_MARKER in output:
            log(c(C.GREEN + C.BOLD, "✓ Görev tamamlandı. Backlog izleniyor..."))
            last_mtime = _get_mtime(BACKLOG_PATH)
            while True:
                time.sleep(30)
                if _get_mtime(BACKLOG_PATH) > last_mtime:
                    log(c(C.CYAN, "Backlog güncellendi, devam ediliyor..."))
                    use_continue = True
                    wake_msg     = WAKE_MSG
                    break
            continue

        if limit_hit:
            log(c(C.ORANGE, "Limit vurdu."))
            use_continue = True
            target = get_reset_datetime(resets_ts)
            if target:
                wait = max(0, int((target - datetime.now()).total_seconds()))
                log(c(C.ORANGE, f"Reset: {target.strftime('%d %b %H:%M:%S')} — {wait}s bekleniyor."))
                if wait > 0:
                    time.sleep(wait)
                log(c(C.GREEN, "Uyandı, devam ediliyor..."))
            else:
                log(c(C.YELLOW, "Reset zamanı bulunamadı, 10dk bekleniyor."))
                time.sleep(600)
        else:
            log(c(C.YELLOW, "Oturum bitti, yeniden başlatılıyor..."))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Durduruldu.")
