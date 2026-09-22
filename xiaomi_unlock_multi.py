#!/usr/bin/env python3
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import time
from datetime import datetime, timezone, timedelta

import browser_cookie3
import ntplib
import pytz
import urllib3
from colorama import Fore, Style, init

COMMUNITY_URL = "https://new.c.mi.com/global"
STATUS_URL = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
APPLY_URL = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"

# Dipertahankan dari script sumber.
VERSION_CODE = "500411"
VERSION_NAME = "5.4.11"

DEFAULT_OFFSETS_MS = [1000, 500, 150, 0]

NTP_SERVERS = (
    "time.google.com",
    "time.apple.com",
    "pool.ntp.org",
    "ntp.aliyun.com",
    "ntp.tencent.com",
    "cn.pool.ntp.org",
)

BEIJING_TZ = pytz.timezone("Asia/Shanghai")

init(autoreset=True)
RESET = Style.RESET_ALL

def info(msg): print(Fore.CYAN + "[i] " + RESET + msg)
def ok(msg): print(Fore.GREEN + "[OK] " + RESET + msg)
def warn(msg): print(Fore.YELLOW + "[!] " + RESET + msg)
def err(msg): print(Fore.RED + "[X] " + RESET + msg)

def generate_device_id():
    raw = f"{random.random()}-{time.time_ns()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest().upper()

def open_firefox():
    firefox = shutil.which("firefox")
    if not firefox:
        return False
    try:
        subprocess.Popen(
            [firefox, COMMUNITY_URL],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False

def extract_service_token():
    try:
        jar = browser_cookie3.firefox()
    except Exception as exc:
        err(f"Gagal membaca cookie Firefox: {exc}")
        return None

    matches = [c for c in jar if c.name == "new_bbs_serviceToken"]
    if not matches:
        return None

    matches.sort(
        key=lambda c: (
            "mi.com" in (c.domain or ""),
            "new.c.mi.com" in (c.domain or ""),
        ),
        reverse=True,
    )
    return matches[0].value

def get_token(no_browser=False):
    token = extract_service_token()
    if token:
        ok("Session Xiaomi Community ditemukan di Firefox.")
        return token

    if no_browser:
        return None

    info("Session Xiaomi Community belum ditemukan.")
    if open_firefox():
        print("Firefox sudah dibuka ke Xiaomi Community Global.")
    else:
        warn("Firefox tidak bisa dibuka otomatis.")
        print(f"Buka manual: {COMMUNITY_URL}")

    print(
        "\nLogin dengan akun Xiaomi yang sama seperti di tablet.\n"
        "Setelah login selesai, TUTUP Firefox agar cookie tersimpan."
    )
    input("\nTekan ENTER setelah Firefox benar-benar ditutup... ")
    time.sleep(1.5)

    token = extract_service_token()
    if token:
        ok("new_bbs_serviceToken berhasil dibaca.")
        return token

    err("Token tidak ditemukan. Pastikan login selesai dan Firefox sudah ditutup.")
    return None

class XiaomiSession:
    def __init__(self):
        self.http = urllib3.PoolManager(
            retries=False,
            timeout=urllib3.Timeout(connect=4.0, read=10.0),
        )

    def request_json(self, method, url, headers=None, body=None):
        r = self.http.request(
            method,
            url,
            headers=headers or {},
            body=body,
            preload_content=True,
        )
        raw = r.data
        status = r.status
        r.release_conn()

        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            preview = raw[:500].decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Respons non-JSON (HTTP {status}): {preview}"
            ) from exc

        return status, payload

def make_headers(token, device_id, post=False):
    cookie = (
        f"new_bbs_serviceToken={token};"
        f"versionCode={VERSION_CODE};"
        f"versionName={VERSION_NAME};"
        f"deviceId={device_id};"
    )
    headers = {
        "Cookie": cookie,
        "Content-Type": "application/json; charset=utf-8",
    }
    if post:
        headers.update(
            {
                "Accept-Encoding": "gzip, deflate, br",
                "User-Agent": "okhttp/4.12.0",
                "Connection": "keep-alive",
            }
        )
    return headers

def parse_status(payload):
    code = payload.get("code")
    if code == 100004:
        return "expired", ""

    data = payload.get("data") or {}
    is_pass = data.get("is_pass")
    button_state = data.get("button_state")
    deadline = data.get("deadline_format", "")

    if is_pass == 1:
        return "approved", deadline
    if is_pass == 4:
        if button_state == 1:
            return "can_apply", deadline
        if button_state == 2:
            return "blocked", deadline
        if button_state == 3:
            return "too_new", deadline

    return "unknown", deadline

def check_unlock_status(session, token, device_id, quiet=False):
    _, payload = session.request_json(
        "GET",
        STATUS_URL,
        headers=make_headers(token, device_id),
    )
    state, deadline = parse_status(payload)

    if not quiet:
        if state == "approved":
            ok("Permohonan unlock sudah disetujui" + (f" sampai {deadline}." if deadline else "."))
        elif state == "can_apply":
            ok("Akun saat ini diizinkan mengirim permohonan.")
        elif state == "blocked":
            warn("Akun belum bisa mengirim permohonan" + (f" sampai {deadline}." if deadline else "."))
        elif state == "too_new":
            warn("Akun terdeteksi berumur kurang dari 30 hari.")
        elif state == "expired":
            err("Cookie/session sudah kedaluwarsa.")
        else:
            warn("Status akun belum dikenali:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

    return state, deadline, payload

def ntp_beijing_now():
    client = ntplib.NTPClient()
    for server in NTP_SERVERS:
        try:
            info(f"Sinkronisasi waktu: {server}")
            response = client.request(server, version=3, timeout=2.5)
            now_utc = datetime.fromtimestamp(response.tx_time, timezone.utc)
            now_bj = now_utc.astimezone(BEIJING_TZ)
            ok(f"Waktu Beijing: {now_bj.strftime('%Y-%m-%d %H:%M:%S.%f')}")
            return now_bj
        except Exception:
            continue

    warn("Semua NTP gagal. Menggunakan jam sistem.")
    return datetime.now(timezone.utc).astimezone(BEIJING_TZ)

def parse_offsets(text):
    if not text:
        return list(DEFAULT_OFFSETS_MS)

    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = float(part)
        except ValueError:
            raise ValueError(f"Offset tidak valid: {part!r}")
        if not 0 <= value <= 5000:
            raise ValueError("Setiap offset harus antara 0 dan 5000 ms.")
        values.append(value)

    if not values:
        raise ValueError("Daftar offset kosong.")

    # Harus dari paling awal ke paling dekat ke tengah malam:
    # 1000 -> 500 -> 150 -> 0
    values = sorted(set(values), reverse=True)
    return values

def target_midnight(base_time):
    tomorrow = base_time + timedelta(days=1)
    return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

def make_synced_clock(base_time):
    base_mono = time.monotonic()
    def now():
        return base_time + timedelta(seconds=time.monotonic() - base_mono)
    return now

def wait_until(now_func, target):
    while True:
        now = now_func()
        remain = (target - now).total_seconds()
        if remain <= 0:
            return now

        if remain > 60:
            print(
                f"\rMenunggu {int(remain//60):02d}:{int(remain%60):02d} ...",
                end="",
                flush=True,
            )
            time.sleep(min(10.0, max(1.0, remain - 30)))
        elif remain > 2:
            print(
                f"\rMenunggu {remain:6.2f} detik ...",
                end="",
                flush=True,
            )
            time.sleep(min(0.4, max(0.03, remain - 1.0)))
        elif remain > 0.05:
            time.sleep(min(0.005, remain / 2))
        else:
            # Spin sangat singkat menjelang target.
            pass

def classify_apply_response(payload):
    code = payload.get("code")
    data = payload.get("data") or {}

    if code == 0:
        result = data.get("apply_result")
        deadline = data.get("deadline_format", "")
        if result == 1:
            return "approved", deadline
        if result == 3:
            return "limit", deadline
        if result == 4:
            return "blocked", deadline

    if code == 100003:
        return "recheck", ""
    if code == 100004:
        return "expired", ""
    if code == 100001:
        return "rejected", ""

    return "unknown", ""

def send_apply_once(session, token, device_id):
    _, payload = session.request_json(
        "POST",
        APPLY_URL,
        headers=make_headers(token, device_id, post=True),
        body=b'{"is_retry":true}',
    )
    state, deadline = classify_apply_response(payload)
    return state, deadline, payload

def main():
    parser = argparse.ArgumentParser(
        description="Xiaomi Community unlock helper multi-offset untuk Linux Mint."
    )
    parser.add_argument(
        "--offsets",
        default=None,
        help="Offset ms, contoh: 1000,500,150,0",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Hanya cek status akun.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Jangan buka Firefox otomatis.",
    )
    args = parser.parse_args()

    print(Style.BRIGHT + "\nXiaomi Unlock Community Helper - Multi Offset\n" + RESET)
    print(
        "Maksimal 4 request terjadwal (default 1000, 500, 150, 0 ms sebelum 00:00 GMT+8).\n"
        "Tidak ada loop request tanpa batas. Token hanya disimpan di RAM.\n"
    )

    try:
        offsets = parse_offsets(args.offsets)
    except ValueError as exc:
        err(str(exc))
        raise SystemExit(2)

    info("Offset aktif: " + ", ".join(f"{x:g} ms" for x in offsets))

    token = get_token(no_browser=args.no_browser)
    if not token:
        raise SystemExit(1)

    device_id = generate_device_id()
    session = XiaomiSession()

    try:
        state, deadline, _ = check_unlock_status(session, token, device_id)
    except Exception as exc:
        err(f"Gagal cek status akun: {exc}")
        raise SystemExit(1)

    if args.check_only:
        return

    if state == "approved":
        return
    if state in {"expired", "too_new"}:
        warn("Tidak melanjutkan pengajuan.")
        return

    # Penting:
    # Jika saat 23:59 status masih 'blocked/limit until tomorrow',
    # tetap lanjut ke jadwal midnight karena kuota baru bisa terbuka tepat 00:00.
    if state == "blocked":
        warn(
            "Status saat ini masih blocked/limit, tetapi script tetap menunggu 00:00 GMT+8 "
            "karena kuota harian dapat reset saat pergantian hari."
        )
    elif state == "unknown":
        warn(
            "Status awal tidak dikenali. Script tetap menunggu, tetapi akan berhenti "
            "jika server mengembalikan status fatal."
        )

    base_time = ntp_beijing_now()
    midnight = target_midnight(base_time)
    now_func = make_synced_clock(base_time)

    print()
    info(f"Midnight target: {midnight.strftime('%Y-%m-%d %H:%M:%S.%f')} GMT+8")
    warn("Biarkan terminal terbuka dan cegah laptop masuk sleep.")
    print()

    for idx, offset_ms in enumerate(offsets, start=1):
        target = midnight - timedelta(milliseconds=offset_ms)

        # Kalau script dijalankan terlambat dan target offset sudah lewat,
        # jangan mundur; langsung kirim untuk slot itu.
        now = now_func()
        if now < target:
            wait_until(now_func, target)
            print()

        send_time = now_func()
        info(
            f"[{idx}/{len(offsets)}] Kirim request "
            f"(offset {offset_ms:g} ms) pada {send_time.strftime('%H:%M:%S.%f')} GMT+8"
        )

        try:
            result, deadline, payload = send_apply_once(
                session, token, device_id
            )
        except Exception as exc:
            warn(f"Request gagal secara jaringan: {exc}")
            continue

        if result == "approved":
            ok("APPROVED. Tidak mengirim request berikutnya.")
            try:
                check_unlock_status(session, token, device_id)
            except Exception:
                pass
            return

        if result == "recheck":
            warn("Server meminta re-check status.")
            try:
                st, _, _ = check_unlock_status(session, token, device_id)
                if st == "approved":
                    return
            except Exception:
                pass
            continue

        if result == "expired":
            err("Session/cookie kedaluwarsa. Berhenti.")
            return

        if result == "blocked":
            warn(
                "Server mengembalikan BLOCKED"
                + (f" sampai {deadline}." if deadline else ".")
            )
            # Jika request masih sebelum midnight, lanjut ke slot berikutnya.
            # Jika sudah tepat/selepas midnight, berhenti agar tidak spam.
            if send_time >= midnight:
                return
            continue

        if result == "limit":
            warn(
                "Server mengembalikan LIMIT"
                + (f" sampai {deadline}." if deadline else ".")
            )
            # Sebelum 00:00, limit bisa masih kuota hari lama -> lanjut.
            # Pada/selepas 00:00, anggap kuota baru sudah habis -> berhenti.
            if send_time >= midnight:
                warn("Limit terjadi pada/selepas 00:00 GMT+8. Berhenti.")
                return
            continue

        if result == "rejected":
            warn("Request ditolak. Respons server:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        warn("Respons belum dikenali; lanjut ke offset berikutnya.")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    print()
    warn("Semua offset selesai tanpa status approved.")

if __name__ == "__main__":
    main()
