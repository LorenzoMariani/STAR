"""Sceglie e scarica un'immagine per componente (solo immagini: decodificate con Pillow, mai eseguite)."""
import io, json, re, sys, urllib.request, urllib.parse, hashlib
from pathlib import Path
from PIL import Image

WORK = Path(sys.argv[1])          # cartella di lavoro (imgs/)
CAT = Path(sys.argv[2])
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
RAW = WORK / "raw"
RAW.mkdir(exist_ok=True)
cand = json.loads((WORK / "candidates.json").read_text(encoding="utf-8"))
comps = {c["id"]: c for c in json.loads(CAT.read_text(encoding="utf-8"))["components"]}
OVERRIDE = json.loads((WORK / "override.json").read_text(encoding="utf-8-sig")) if (WORK / "override.json").exists() else {}

BAD = re.compile(r"logo|icon|favicon|flag|badge|sprite|avatar|banner|cursor|arrow|placeholder|footer|social|certif|iso-?9|iso-?1|-150x150|-100x100|-300x\d+-|gravatar|spinner|loader|\.svg|\.gif|\.ico|whatsapp|linkedin|twitter|facebook|youtube|flight-heritage|heritage-badge|partner|client|team|news|blog|case-study|ground|flyer|trustpilot|cookie|menu|search|close|check|play", re.I)
STOP = {"the", "and", "con", "per", "imager", "camera", "telescope", "transceiver", "module", "unit", "optical", "structure", "solar", "panel"}


def tokens(c):
    name = re.sub(r"\(.*?\)", " ", c["name"])
    toks = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", name) if len(t) >= 3}
    toks |= {t.lower() for t in re.findall(r"[A-Za-z]+\d+[A-Za-z]*|\d+[A-Za-z]+", name)}
    return toks


def score(c, im):
    u = im["url"].lower()
    if BAD.search(u) or BAD.search((im.get("alt") or "").lower()):
        return -1
    s = 0
    if im["kind"] == "meta":
        s += 10
    blob = u + " " + (im.get("alt") or "").lower()
    for t in tokens(c):
        if t in blob:
            s += 6 if t not in STOP else 1
    for t in re.findall(r"[a-z0-9]+", c["id"].split("-", 1)[-1].lower()):
        if len(t) >= 3 and t in blob:
            s += 3
    if "wp-content/uploads" in u or "/uploads/" in u:
        s += 2
    try:
        if im.get("width") and int(re.sub(r"\D", "", im["width"])) >= 300:
            s += 2
    except ValueError:
        pass
    return s


def fetch(url):
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    f = RAW / key
    if f.exists():
        return f.read_bytes()
    req = urllib.request.Request(url, headers={**UA, "Referer": url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + "/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(15_000_000)
    f.write_bytes(data)
    return data


def load(data):
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def pick(cid):
    c = comps[cid]
    if cid in OVERRIDE:
        urls = [{"url": OVERRIDE[cid], "kind": "override", "alt": ""}]
        ranked = [(99, u) for u in urls]
    else:
        pool = []
        for page in cand["plan"].get(cid, []):
            info = cand["pages"].get(page, {})
            for im in info.get("images", []):
                pool.append((score(c, im), im, page))
        seen, ranked = set(), []
        for s, im, page in sorted(pool, key=lambda x: -x[0]):
            if s < 0 or im["url"] in seen:
                continue
            seen.add(im["url"])
            ranked.append((s, im))
    tried = []
    for s, im in ranked[:6]:
        try:
            pil = load(fetch(im["url"]))
        except Exception as e:  # noqa: BLE001
            tried.append((im["url"], f"ERR {type(e).__name__}"))
            continue
        w, h = pil.size
        tried.append((im["url"], f"{w}x{h} s={s}"))
        if min(w, h) >= 220 and 0.25 < w / h < 4:
            return im["url"], pil, tried
    return None, None, tried


result = {}
for cid in comps:
    url, pil, tried = pick(cid)
    result[cid] = {"url": url, "tried": tried}
    if pil is not None:
        pil.save(WORK / "pick" / f"{cid}.png") if (WORK / "pick").exists() else None
    print(("OK  " if url else "MISS"), cid, "|", url or tried[:2])
(WORK / "picked.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

