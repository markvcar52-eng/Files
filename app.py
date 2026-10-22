import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB upload limit

TEST_URL = "https://api.ipify.org?format=json"
TIMEOUT = 8
MAX_THREADS = 15
MAX_LINES = 1000


def parse_proxy(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return []

    if "://" in line:
        scheme, rest = line.split("://", 1)
        scheme = scheme.lower()

        if scheme in ("socks4", "socks4a"):
            scheme = "socks4"
        elif scheme in ("socks5", "socks5h"):
            scheme = "socks5"
        elif scheme not in ("http", "https"):
            return []

        if "@" not in rest:
            url = f"{scheme}://{rest}"
        else:
            auth, address = rest.rsplit("@", 1)
            if ":" not in auth:
                return []
            user, password = auth.split(":", 1)
            url = (
                f"{scheme}://{quote(user, safe='')}:"
                f"{quote(password, safe='')}@{address}"
            )
        return [(scheme, url)]

    parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        auth = ""
    elif len(parts) == 4:
        host, port, user, password = parts
        auth = f"{quote(user, safe='')}:{quote(password, safe='')}@"
    else:
        return []

    if not port.isdigit() or not (1 <= int(port) <= 65535):
        return []

    return [
        ("http", f"http://{auth}{host}:{port}"),
        ("socks4", f"socks4://{auth}{host}:{port}"),
        ("socks5", f"socks5h://{auth}{host}:{port}"),
    ]


def test_one(proxy_url):
    proxies = {"http": proxy_url, "https": proxy_url}
    started = time.perf_counter()
    try:
        response = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)
        response.raise_for_status()
        ip = response.json().get("ip")
        if not ip:
            return None
        latency = round((time.perf_counter() - started) * 1000)
        return {"latency": latency, "ip": ip, "status": "ALIVE"}
    except (requests.exceptions.RequestException, ValueError):
        return None


def check_proxy(line):
    candidates = parse_proxy(line)
    if not candidates:
        return {"proxy": line, "ok": False, "status": "INVALID", "scheme": "", "latency": None, "ip": ""}
    for scheme, proxy_url in candidates:
        result = test_one(proxy_url)
        if result:
            return {
                "proxy": line,
                "ok": True,
                "status": "ALIVE",
                "scheme": scheme.upper(),
                "latency": result["latency"],
                "ip": result["ip"],
            }
    return {"proxy": line, "ok": False, "status": "FAILED / UNVERIFIED", "scheme": "", "latency": None, "ip": ""}


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/check")
def api_check():
    pasted = request.form.get("proxies", "")
    upload = request.files.get("proxy_file")
    entries = []

    if pasted.strip():
        entries.extend(pasted.splitlines())

    if upload and upload.filename:
        if not upload.filename.lower().endswith(".txt"):
            return jsonify({"error": "TXT files only."}), 400
        try:
            entries.extend(upload.read().decode("utf-8-sig").splitlines())
        except UnicodeDecodeError:
            return jsonify({"error": "The uploaded file must be UTF-8 text."}), 400

    lines = list(dict.fromkeys(
        item.strip() for item in entries
        if item.strip() and not item.lstrip().startswith("#")
    ))

    if not lines:
        return jsonify({"error": "Paste proxies or upload a TXT file first."}), 400
    if len(lines) > MAX_LINES:
        return jsonify({"error": f"Limit is {MAX_LINES} unique lines per check."}), 400

    results = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as pool:
        futures = [pool.submit(check_proxy, line) for line in lines]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                results.append({
                    "proxy": "A result could not be processed",
                    "ok": False,
                    "status": "ERROR",
                    "scheme": "",
                    "latency": None,
                    "ip": "",
                })

    # Keep results in the same order as the input list.
    order = {line: i for i, line in enumerate(lines)}
    results.sort(key=lambda item: order.get(item["proxy"], len(order)))

    return jsonify({
        "total": len(results),
        "alive": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
    })


@app.post("/api/download")
def download_results():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "alive")
    results = data.get("results", [])
    if kind not in ("alive", "failed"):
        return jsonify({"error": "Invalid download type."}), 400

    selected = [
        row for row in results
        if isinstance(row, dict) and bool(row.get("ok")) == (kind == "alive")
    ]
    content = "\n".join(str(row.get("proxy", "")) for row in selected)
    memory_file = io.BytesIO(content.encode("utf-8"))
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="text/plain; charset=utf-8",
        as_attachment=True,
        download_name=f"{kind}.txt",
    )


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Upload is too large. Maximum size is 2 MB."}), 413


if __name__ == "__main__":
    # Local-only by default. Open http://127.0.0.1:5000 in the phone browser.
    app.run(host="127.0.0.1", port=5000, debug=False)
