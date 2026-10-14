"""
RouteSense AI - Production WSGI Entrypoint
------------------------------------------
Production server runner for RouteSense AI.
Run with:
    python wsgi.py
Or with Waitress CLI:
    waitress-serve --host=0.0.0.0 --port=5000 wsgi:app
Or with Gunicorn (Linux/WSL):
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app

if __name__ == '__main__':
    from waitress import serve
    print("======================================================================")
    print("       RouteSense AI - Disaster Evacuation Routing Intelligence       ")
    print("                PRODUCTION WSGI SERVER (Waitress)                    ")
    print("======================================================================")
    print("  URL:        http://127.0.0.1:5000 (Local)")
    print("  Network:    http://0.0.0.0:5000   (LAN / Mobile Access)")
    print("  Workers:    8 concurrent threads")
    print("  Status:     Production Ready - No development server warnings")
    print("======================================================================\n")
    serve(app, host='0.0.0.0', port=5000, threads=8, channel_timeout=60, cleanup_interval=30)
