"""Windows desktop launcher for the packaged Job Role Finder application."""
from threading import Timer
import webbrowser

from app import create_server


def main():
    address = "http://127.0.0.1:5000"
    server = create_server()
    Timer(1.0, lambda: webbrowser.open(address)).start()
    print(f"Job Role Finder is running at {address}")
    print("Keep this window open while using the tool. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
