"""Datasheet locali, conteggi del riquadro Database e coerenza con i file presenti nelle cartelle images/ e datasheets/."""
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from star_selector.api import ACRONYMS, SelectorService
from star_selector.selector import SUBSYSTEMS
from star_selector.server import make_handler
from tests.datasheet_library import PDFS_PRESENT, needs_pdfs

SERVICE = SelectorService()
CAT = {c.id: c for c in SERVICE.catalog}


class TestDatasheets(unittest.TestCase):
    def test_every_registered_datasheet_is_a_real_pdf_of_its_source(self):
        n = 0
        for c in SERVICE.catalog:
            ds = c.raw.get("datasheet")
            if not ds:
                continue
            n += 1
            if not ds.get("origin"):     # il file e' il documento citato come fonte (un PDF aggiunto dall'utente puo' essere solo di riferimento)
                self.assertEqual(ds["source_url"], c.raw["source"]["url"], c.id)
            else:
                self.assertIsNone(ds["source_url"], c.id)
            if PDFS_PRESENT:             # i file solo con la libreria dei PDF (tests/datasheet_library.py)
                path = SERVICE.root / ds["file"]
                self.assertTrue(path.is_file(), c.id)
                self.assertEqual(path.read_bytes()[:4], b"%PDF", c.id)
                self.assertEqual(ds["bytes"], path.stat().st_size, c.id)
        self.assertGreaterEqual(n, 90)

    def test_components_whose_source_is_a_web_page_have_no_datasheet(self):
        self.assertIsNone(CAT["cubespace-cubestar"].raw.get("datasheet"))              # fonte: pagina HTML
        self.assertIsNone(CAT["spacemanic-structure-1u"].raw.get("datasheet"))         # PDF non raggiungibile (HTTP 404)
        self.assertIsNone(SERVICE.component("cubespace-cubestar", with_image=False)["datasheet"])

    @needs_pdfs
    def test_record_exposes_file_document_and_page_but_no_link(self):
        rec = SERVICE.component("endurosat-structure-3u", with_image=False)["datasheet"]
        self.assertEqual(rec["file"], "datasheets/EnduroSat__Endurosat_Product_Catalogue_02_22.pdf")
        self.assertEqual(rec["page"], 19)
        self.assertNotIn("source_url", rec)

    def test_datasheet_data_for_star(self):
        d = SERVICE.datasheet_data("gomspace-nanotorque-gst-600-mk2")
        if PDFS_PRESENT:
            self.assertTrue(d["ok"])
            self.assertEqual(d["mime"], "application/pdf")
        else:                            # senza libreria il datasheet registrato risulta non disponibile (README)
            self.assertEqual(d, {"ok": False, "error": "Not available in the database"})
            self.assertIsNone(SERVICE.component("gomspace-nanotorque-gst-600-mk2", with_image=False)["datasheet"])
        self.assertFalse(SERVICE.datasheet_data("cubespace-cubestar")["ok"])
        self.assertEqual(SERVICE.datasheet_data("cubespace-cubestar")["error"], "Not available in the database")
        with self.assertRaises(KeyError):
            SERVICE.datasheet_data("nope")

    def test_path_traversal_is_refused(self):
        self.assertIsNone(SERVICE.datasheet_path("datasheets/../data/catalog.json"))
        self.assertIsNone(SERVICE.datasheet_path("data/catalog.json"))


class TestLibraryStats(unittest.TestCase):
    def test_counts_match_the_catalogue_and_the_files(self):
        L = SERVICE.library()
        self.assertEqual([c["id"] for c in L["classes"]], [sid for sid, _, _ in SUBSYSTEMS])
        self.assertEqual(L["total"], len(SERVICE.catalog))
        self.assertEqual(L["images"], sum(1 for c in SERVICE.catalog if c.raw.get("image")))
        registered = sum(1 for c in SERVICE.catalog if c.raw.get("datasheet"))
        self.assertEqual(L["datasheets"], registered if PDFS_PRESENT else 0)     # il riquadro conta i PDF presenti
        self.assertEqual(sum(c["n"] for c in L["classes"]), L["total"])
        self.assertTrue(all(c["images"] <= c["n"] and c["datasheets"] <= c["n"] for c in L["classes"]))
        by = {c["id"]: c for c in L["classes"]}
        self.assertEqual((by["magnetorquer"]["n"], by["magnetorquer"]["images"]), (8, 0))   # nessuna immagine per i magnetorquer aggiunti

    def test_every_class_has_a_unique_acronym(self):
        self.assertEqual(set(ACRONYMS), {sid for sid, _, _ in SUBSYSTEMS})
        self.assertEqual(len({a for a, _ in ACRONYMS.values()}), len(ACRONYMS))

    def test_selection_carries_the_library(self):
        r = SERVICE.select({"form_factor_u": 3})
        self.assertEqual(r["library"]["total"], len(SERVICE.catalog))


class TestHttpRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(SERVICE))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10)

    @needs_pdfs
    def test_pdf_is_served_inline(self):
        r = self.get("/" + CAT["gomspace-nanotorque-gst-600-mk2"].raw["datasheet"]["file"])
        self.assertEqual(r.headers["Content-Type"], "application/pdf")
        self.assertEqual(r.read(4), b"%PDF")

    def test_other_files_are_not_served(self):
        for p in ("/datasheets/../data/catalog.json", "/datasheets/missing.pdf", "/datasheets/manifest.csv"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(p)
            self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
