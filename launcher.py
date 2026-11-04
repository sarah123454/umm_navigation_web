# launcher.py
import argparse
import subprocess
import sys
import webbrowser

from config import BASE_DIR, WEB_PORT, KIOSK_PORT, KIOSK_START_ID


def finde_app():
    """Sucht die Streamlit-App: zuerst im Hauptordner, sonst in web/."""
    for pfad in (BASE_DIR / "app.py", BASE_DIR / "web" / "app.py"):
        if pfad.exists():
            return pfad
    sys.exit("❌ Keine app.py gefunden (weder im Hauptordner noch in web\\).")


def start_streamlit(port):
    # Streamlit-Apps müssen mit "streamlit run" gestartet werden, nicht mit "python -m"
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(finde_app()),
         "--server.port", str(port),
         "--server.address", "0.0.0.0"],        # auch von Handy/Tablet im WLAN erreichbar
        cwd=BASE_DIR,
    )


def start_web():
    print(f"▶ Web-App startet: http://localhost:{WEB_PORT}")
    return start_streamlit(WEB_PORT)


def start_kiosk():
    # Kiosk = dieselbe App auf eigenem Port, Startpunkt fest auf den Kiosk-Standort
    p = start_streamlit(KIOSK_PORT)
    url = f"http://localhost:{KIOSK_PORT}"
    if KIOSK_START_ID:
        url += f"/?start={KIOSK_START_ID}"
    print(f"▶ Kiosk startet: {url}")
    webbrowser.open(url)
    return p


def generate_qr():
    from qr.generator import generate_all
    generate_all()


def main():
    parser = argparse.ArgumentParser(description="UMM Navigation Launcher")
    # nargs="?" + default="web": ohne Angabe (z. B. ▶-Button in VS Code) startet die Web-App
    parser.add_argument("mode", nargs="?", default="web", choices=["web", "kiosk", "both", "qr"])
    args = parser.parse_args()

    if args.mode == "qr":
        generate_qr()
        return

    procs = []
    if args.mode in ("web", "both"):
        procs.append(start_web())
    if args.mode in ("kiosk", "both"):
        procs.append(start_kiosk())

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()