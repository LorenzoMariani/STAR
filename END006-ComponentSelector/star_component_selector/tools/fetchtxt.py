import re, ssl, sys, urllib.request, urllib.parse
from html.parser import HTMLParser

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


class T(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.links = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "a" and dict(attrs).get("href"):
            self.links.append(dict(attrs)["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.out.append(d.strip())


for u in sys.argv[1:]:
    try:
        h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25).read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print("ERR", u, type(e).__name__, e)
        continue
    t = T()
    t.feed(h)
    print("=====", u)
    print(" | ".join(t.out)[:3500])
    links = sorted({urllib.parse.urljoin(u, l) for l in t.links if "tyvak" in urllib.parse.urljoin(u, l)})
    print("LINKS:", links[:60])
