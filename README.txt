# Android Proxy Checker Dashboard (Termux)

## 1) Install dependencies in Termux
```bash
pkg update
pkg install python
pip install -r requirements.txt
```

## 2) Start the local web server
Go to the folder where `app.py` and `requirements.txt` are saved:
```bash
python app.py
```

## 3) Open the dashboard
Open Chrome on the same Android phone and visit:
http://127.0.0.1:5000

Keep Termux running while using the dashboard. Stop the server with Ctrl+C in Termux.

## Notes
- The server listens on 127.0.0.1 only, so it is local to your phone by default.
- Maximum upload size is 2 MB and maximum 1,000 unique proxy lines per run.
- Tests use `https://api.ipify.org?format=json`.
- A failed result means no successful response; it does not prove a proxy is permanently dead.
- Use only proxies you own or are authorized to test.
