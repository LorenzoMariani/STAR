"""Server HTTP locale (solo libreria standard) per la GUI del selettore: `python -m star_selector serve`.

Endpoint:  GET /               GUI
           GET /api/health     {"ok": true}
           GET /api/catalog    classi CubeSat, sottosistemi, fornitori, piattaforme
           GET /api/component/<id>
           POST /api/select    corpo = {"form_factor_u": 1|3|6|12}
           POST /api/requirements   {"text": "...", "defaults": {...}} -> parametri ricavati dai requisiti (orchestratore)
           GET /images/<file>  immagini dei componenti
           GET /datasheets/<file>  datasheet e brochure PDF dei componenti
Ascolta solo su 127.0.0.1 (nessun accesso dalla rete) e non scrive file."""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .api import ROOT, SelectorService, dumps, requirements_to_params

# la GUI e' il file del tab END-006 nel FrontEnd di STAR (unica copia dal 2026-10-17): STAR/FrontEnd/web/modules/end006_results.html
GUI = ROOT.parent.parent / "FrontEnd" / "web" / "modules" / "end006_results.html"
MAX_BODY = 1_000_000


def make_handler(service: SelectorService, gui_path: Path = GUI):
    class Handler(BaseHTTPRequestHandler):
        server_version = "STARComponentSelector/1.0"

        def log_message(self, fmt, *args):  # silenzioso: la GUI chiama spesso
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, dumps(obj).encode("utf-8"))

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            try:
                if path in ("/", "/index.html"):
                    if not gui_path.is_file():
                        return self._send(404, f"GUI not found: {gui_path} (STAR FrontEnd/web/modules/end006_results.html)".encode("utf-8"),
                                          "text/plain; charset=utf-8")
                    self._send(200, gui_path.read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/health":
                    self._json({"ok": True, "components": len(service.catalog)})
                elif path == "/api/catalog":
                    self._json(service.overview())
                elif path.startswith("/api/component/"):
                    self._json(service.component(path.rsplit("/", 1)[1]))
                elif path.startswith("/images/"):
                    img = service.image_path(path.lstrip("/"))
                    if img is None:
                        self._send(404, b"not found", "text/plain")
                    else:
                        self._send(200, img.read_bytes(), mimetypes.guess_type(img.name)[0] or "image/png", {"Cache-Control": "max-age=3600"})
                elif path.startswith("/datasheets/"):
                    pdf = service.datasheet_path(path.lstrip("/"))
                    if pdf is None:
                        self._send(404, b"not found", "text/plain")
                    else:
                        self._send(200, pdf.read_bytes(), "application/pdf", {"Cache-Control": "max-age=3600", "Content-Disposition": "inline"})
                else:
                    self._send(404, b"not found", "text/plain")
            except KeyError:
                self._json({"ok": False, "error": "unknown component"}, 404)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._json({"ok": False, "error": "request too large"}, 413)
                data = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/select":
                    self._json(service.select(data, with_images=bool(data.pop("with_images", False))))
                elif path == "/api/requirements":
                    self._json(requirements_to_params(data.get("requirements") or data.get("text") or "", data.get("defaults")))
                else:
                    self._send(404, b"not found", "text/plain")
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)

    return Handler


def serve(catalog_path: str | None = None, port: int = 8765, open_browser: bool = False) -> None:
    service = SelectorService(catalog_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service))
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"STAR Component Selector: {url}  ({len(service.catalog)} components; Ctrl+C to stop)")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
