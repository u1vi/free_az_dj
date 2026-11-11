"""Production entry point: one server and a browser opened after it is ready."""

import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from .settings import HOST, PORT


def open_when_ready() -> None:
    url = f"http://{HOST}:{PORT}"
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{url}/openapi.json", timeout=0.5):
                webbrowser.open(url)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)


if __name__ == "__main__":
    from .main import app

    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT)

