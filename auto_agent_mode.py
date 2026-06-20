import json
import os
import re
import sys
import time
import subprocess
from datetime import datetime, timedelta

PROMPT_FILE = "prompt.txt"
LOG_FILE    = "agent_output.log"
DONE_MARKER = "### AGENT_TASK_COMPLETED ###"

MONTHS = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}
RE_RESET_DATED = re.compile(r'Resets\s+([A-Za-z]+)\s+(\d+),\s+(\d+):(\d+)(am|pm)', re.I)
RE_RESET_TIME  = re.compile(r'Resets\s+(\d+):(\d+)(am|pm)', re.I)


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
    emit(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")


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
        content = obj.get("message", {}).get("content", [])
        parts = []
        for block in content:
            bt = block.get("type")
            if bt == "text":
                text = block["text"].strip()
                if text:
                    parts.append(text + "\n")
            elif bt == "tool_use":
                name   = block.get("name", "?")
                detail = _tool_detail(block.get("input", {}))
                parts.append(f"  -> {name}({detail})\n" if detail else f"  -> {name}()\n")
            elif bt == "thinking":
                pass  # iç düşünme, gösterme
        return "".join(parts) or None, False, None

    # --- Tool sonucu (user mesajı olarak gelir) ---
    if t == "user":
        result = obj.get("tool_use_result", {})
        rtype  = result.get("type", "")
        if rtype == "text":
            finfo = result.get("file")
            if finfo:
                path   = finfo.get("filePath", "")
                nlines = finfo.get("numLines", "?")
                return f"  <- Read({path}) [{nlines} satır]\n", False, None
            content = result.get("content", "")
            snippet = str(content)[:80].replace("\n", " ")
            return f"  <- {snippet}\n", False, None
        if rtype == "error":
            msg = result.get("message", "")
            return f"  <- ERROR: {msg}\n", False, None
        if rtype == "base64":
            return f"  <- [binary data]\n", False, None
        return None, False, None

    # --- Rate limit ---
    if t == "rate_limit_event":
        info   = obj.get("rate_limit_info", {})
        status = info.get("status")
        ts     = info.get("resetsAt")
        if status != "allowed":
            return f"\n[rate_limit: {status}]\n", True, ts
        return None, False, None

    # --- Hata ---
    if t == "error":
        err = obj.get("error", {})
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return f"\n[error: {msg}]\n", False, None

    # --- Oturum sonu ---
    if t == "result":
        cost = obj.get("total_cost_usd")
        if sub == "error_max_turns":
            return "\n[max turns]\n", False, None
        if cost is not None:
            turns = obj.get("num_turns", "?")
            return f"\n[tur:{turns} maliyet:${cost:.4f}]\n", False, None

    # --- system/thinking gibi meta eventler: yoksay ---
    return None, False, None


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
        emit(f"\n[stderr] {stderr_out}\n")
        collected.append(stderr_out)

    proc.wait()
    emit("\n")
    return "".join(collected), limit_hit, resets_ts


def parse_reset_target(m_dated=None, m_time=None):
    now = datetime.now()
    if m_dated:
        month_num = MONTHS.get(m_dated.group(1).lower()[:3], now.month)
        day, hour, minute, ampm = int(m_dated.group(2)), int(m_dated.group(3)), int(m_dated.group(4)), m_dated.group(5).lower()
    else:
        month_num = now.month
        day = now.day
        hour, minute, ampm = int(m_time.group(1)), int(m_time.group(2)), m_time.group(3).lower()

    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0

    target = now.replace(month=month_num, day=day, hour=hour, minute=minute, second=30, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def get_reset_datetime(resets_ts=None):
    """
    Önce stream'den gelen Unix timestamp'i dener.
    Yoksa /usage çıktısını parse eder.
    """
    if resets_ts:
        return datetime.fromtimestamp(resets_ts)

    log("Reset zamani alinamadi, /usage sorgulanıyor...")
    try:
        result = subprocess.run(
            'claude -p "/usage" --output-format stream-json --verbose',
            shell=True, capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="ignore",
        )
        output = result.stdout + result.stderr
    except Exception as e:
        log(f"/usage hatasi: {e}")
        return None

    # rate_limit_event içindeki resetsAt
    earliest_ts = None
    for line in output.splitlines():
        try:
            obj = json.loads(line)
            if obj.get("type") == "rate_limit_event":
                ts = obj.get("rate_limit_info", {}).get("resetsAt")
                if ts and (earliest_ts is None or ts < earliest_ts):
                    earliest_ts = ts
        except Exception:
            pass

    if earliest_ts:
        return datetime.fromtimestamp(earliest_ts)

    # Son çare: metin regex
    candidates = []
    for m in RE_RESET_DATED.finditer(output):
        candidates.append(parse_reset_target(m_dated=m))
    for m in RE_RESET_TIME.finditer(output):
        candidates.append(parse_reset_target(m_time=m))
    return min(candidates) if candidates else None


def main():
    open(LOG_FILE, "w", encoding="utf-8").close()  # sıfırla
    log("Agent basliyor...")
    prompt = read_prompt()
    log(f"Prompt yuklendi ({len(prompt)} karakter)")

    first_run = True
    BASE = "-p - --output-format stream-json --verbose --dangerously-skip-permissions"

    while True:
        if first_run:
            cmd = f'claude {BASE}'
            stdin_data = prompt.encode("utf-8")
            first_run = False
        else:
            cmd = f'claude {BASE} --continue'
            stdin_data = b"continue"

        log(f"Oturum baslatiliyor...")
        output, limit_hit, resets_ts = stream_process(cmd, stdin_data=stdin_data)

        if DONE_MARKER in output:
            log("Gorev tamamlandi.")
            break

        if limit_hit:
            log("Limit vurdu.")
        else:
            log("Oturum bitti, gorev tamamlanmadi.")

        target = get_reset_datetime(resets_ts)

        if target:
            wait = max(0, int((target - datetime.now()).total_seconds()))
            log(f"Reset: {target.strftime('%d %b %H:%M:%S')} — {wait}s bekleniyor.")
            if wait > 0:
                time.sleep(wait)
            log("Uyandi, devam ediliyor...")
        else:
            log("Reset zamani bulunamadi, 10dk bekleniyor.")
            time.sleep(600)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Durduruldu.")
