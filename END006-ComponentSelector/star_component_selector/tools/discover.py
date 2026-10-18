"""Scopre le immagini candidate per ogni componente dalle pagine HTML del fornitore. Non esegue nulla di scaricato."""
import json, re, sys, urllib.request, urllib.parse
from html.parser import HTMLParser
from pathlib import Path

CAT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

# pagine prodotto per i componenti la cui fonte e' un PDF (aggiunte a mano, da pagine di fornitori/rivenditori ufficiali)
MANUAL = {
    "endurosat-structure-3u": ["https://www.endurosat.com/products/3u-structure/", "https://www.endurosat.com/products/8u-structure/"],
    "endurosat-structure-6u": ["https://www.endurosat.com/products/6u-structure/", "https://www.endurosat.com/products/8u-structure/"],
    "endurosat-eps-i": ["https://www.endurosat.com/products/eps-i/", "https://www.endurosat.com/products/cubesat-eps/"],
    "endurosat-eps-ii": ["https://www.endurosat.com/products/eps-ii/", "https://www.endurosat.com/products/cubesat-eps/"],
    "isis-structure-3u": ["https://www.isispace.nl/?p=2271"],
    "isis-structure-6u": ["https://www.isispace.nl/?p=2271"],
    "isis-solar-3u": ["https://www.cubesatshop.com/product/isis-cubesat-solar-panels/"],
    "isis-trxvu": ["https://isispace.nl/?p=142653", "https://www.cubesatshop.com/product/isis-vhf-uplink-uhf-downlink-full-duplex-transceiver/"],
    "aac-starbuck-nano": ["https://www.aac-clyde.space/what-we-do/space-products-components/pcdu/cubesat-eps-starbuck-nano"],
    "aac-starbuck-nano-plus": ["https://www.aac-clyde.space/what-we-do/space-products-components/pcdu/cubesat-eps-starbuck-nano"],
    "aac-optimus-30": ["https://www.aac-clyde.space/what-we-do/space-products-components/cubesat-batteries"],
    "aac-optimus-40": ["https://www.aac-clyde.space/what-we-do/space-products-components/cubesat-batteries"],
    "aac-optimus-80": ["https://www.aac-clyde.space/what-we-do/space-products-components/cubesat-batteries"],
    "aac-zaphod-3u": ["https://www.aac-clyde.space/what-we-do/space-products-components/cubesat-structures"],
    "aac-zaphod-6u": ["https://www.aac-clyde.space/what-we-do/space-products-components/cubesat-structures"],
    "aac-photon-side-3u": ["https://www.aac-clyde.space/what-we-do/space-products-components/photon-solar-arrays"],
    "cubespace-cubeadcs-3axis-small": ["https://www.cubesatshop.com/product/cubeadcs-3-axis/", "https://cubesatshop.com/?p=20801"],
    "cubespace-cubeadcs-ymomentum-small": ["https://www.cubesatshop.com/product/cubeadcs-y-momentum/", "https://cubesatshop.com/?p=20801"],
    "gomspace-nanostruct-6u": ["https://gomspace.com/product/nanostruct-6u/"],
    "gomspace-nanomind-a3200": ["https://gomspace.com/product/nanomind-a3200/"],
    "gomspace-nanopower-p60": ["https://gomspace.com/product/nanopower-p60/"],
    "gomspace-nanopower-p80": ["https://gomspace.com/product/nanopower-p80/"],
    "gomspace-bpx-100wh-16v": ["https://gomspace.com/product/nanopower-bpx/"],
    "gomspace-bpx-100wh-32v": ["https://gomspace.com/product/nanopower-bpx/"],
    "gomspace-bp8-100wh": ["https://gomspace.com/product/nanopower-bp8/"],
    "gomspace-dsp-135-mk2": ["https://gomspace.com/product/nanopower-dsp/"],
    "gomspace-nanocom-ax100": ["https://gomspace.com/product/nanocom-ax100/"],
    "gomspace-nanocam-c1u-8mm": ["https://gomspace.com/?p=13563"],
    "gomspace-nanocam-c1u-35mm": ["https://gomspace.com/?p=13563"],
    "gomspace-nanocam-c1u-70mm": ["https://gomspace.com/?p=13563"],
    "pumpkin-csk-mb-ppma1": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-csk-mb-ppma2": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-csk-mb-ppma3": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-csk-mb-ppmb1": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-csk-mb-ppmd1": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-csk-mb-ppmd2": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-fm430": ["https://www.cubesatkit.com/content/electronics/fm430.html"],
    "pumpkin-linear-eps-11wh": ["https://www.cubesatkit.com/content/electronics/power.html"],
    "pumpkin-linear-eps-22wh": ["https://www.cubesatkit.com/content/electronics/power.html"],
    "pumpkin-bm1-40wh": ["https://www.cubesatkit.com/content/electronics/power.html"],
    "pumpkin-mai-100": ["https://www.cubesatkit.com/content/electronics/modules.html"],
    "pumpkin-mai-200": ["https://www.cubesatkit.com/content/electronics/modules.html"],
    "satlab-srs-3": ["https://www.satlab.com/products/srs-3/"],
    "satlab-srs-4": ["https://www.satlab.com/products/srs-4/"],
    "satlab-srx-8": ["https://www.satlab.com/products/srx-8/"],
    "bct-xact-15": ["https://www.bluecanyontech.com/?p=4112", "https://bluecanyontech.com/products/xact"],
    "bct-xact-50": ["https://www.bluecanyontech.com/?p=4112", "https://bluecanyontech.com/products/xact"],
    "bct-xact-100": ["https://www.bluecanyontech.com/?p=4112", "https://bluecanyontech.com/products/xact"],
    "bct-battery-1p8s": ["https://www.bluecanyontech.com/components/batteries/"],
    "bct-battery-2p8s": ["https://www.bluecanyontech.com/components/batteries/"],
    "hyperion-iadcs200": ["https://www.aac-clyde.space/what-we-do/space-products-components/adcs/iadcs200"],
    "hyperion-iadcs400": ["https://www.aac-clyde.space/what-we-do/space-products-components/adcs/iadcs400"],
    "hyperion-im200": ["https://www.aac-clyde.space/what-we-do/space-products-components/payloads/im200"],
    "innoflight-cfc-400-champs": ["https://innoflight.com/product/"],
    "satlantis-isim-90": ["https://www.satlantis.com/space-cameras/"],
    "satlantis-isim-90-swir": ["https://www.satlantis.com/space-cameras/"],
    "satlantis-isim-170": ["https://www.satlantis.com/space-cameras/"],
    "satlantis-isim-170-swir": ["https://www.satlantis.com/space-cameras/"],
    "simera-monoscape200": ["https://simera-sense.com/earth-observation-cameras/xscape200-dual-use/"],
    "spacemind-sm03": ["https://www.npcspacemind.com/product/sm03/"],
}


class Img(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.found, self.title = base, [], ""

    def add(self, url, kind, **kw):
        if url and not url.startswith("data:"):
            self.found.append({"url": urllib.parse.urljoin(self.base, url.strip().split(" ")[0]), "kind": kind, **kw})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property") in ("og:image", "og:image:secure_url") or tag == "meta" and a.get("name") == "twitter:image":
            self.add(a.get("content"), "meta")
        elif tag == "img":
            src = a.get("data-src") or a.get("data-lazy-src") or a.get("src")
            ss = a.get("srcset") or a.get("data-srcset")
            if ss:  # prende la variante piu' larga
                cands = [p.strip().split(" ") for p in ss.split(",") if p.strip()]
                best = max(cands, key=lambda c: int(re.sub(r"\D", "", c[1]) or 0) if len(c) > 1 else 0)
                src = best[0]
            self.add(src, "img", alt=a.get("alt", ""), width=a.get("width"), height=a.get("height"))
        elif tag == "source":
            ss = a.get("srcset")
            if ss:
                self.add(ss.split(",")[-1].strip().split(" ")[0], "source")


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore"), r.geturl()


def main():
    comps = json.loads(CAT.read_text(encoding="utf-8"))["components"]
    pages = {}
    plan = {}
    for c in comps:
        urls = []
        src = c["source"]["url"]
        if not src.lower().split("?")[0].endswith(".pdf") and src.startswith("http"):
            urls.append(src)
        urls += MANUAL.get(c["id"], [])
        plan[c["id"]] = [u for i, u in enumerate(urls) if u not in urls[:i]]
    for u in sorted({u for v in plan.values() for u in v}):
        try:
            html, final = get(u)
            p = Img(final)
            p.feed(html)
            pages[u] = {"final": final, "images": p.found, "ok": True}
        except Exception as e:  # noqa: BLE001
            pages[u] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        print("OK " if pages[u]["ok"] else "ERR", u, len(pages[u].get("images", [])), pages[u].get("error", ""))
    OUT.write_text(json.dumps({"plan": plan, "pages": pages}, indent=1, ensure_ascii=False), encoding="utf-8")


main()
