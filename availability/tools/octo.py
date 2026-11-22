"""Octopart search via the Zyte proxy, cached. octo.lookup(q) → {mpns, mouser, skus}."""
import re, subprocess, pathlib, hashlib, urllib.parse, os
CACHE = pathlib.Path(__file__).with_name("octo_cache"); CACHE.mkdir(exist_ok=True)
REPO = pathlib.Path(__file__).resolve().parents[2]
def _key():
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("ZYTE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
def fetch(q):
    f = CACHE / (hashlib.sha1(q.encode()).hexdigest() + ".html")
    if not f.exists() or f.stat().st_size < 1000:
        url = "https://octopart.com/search?q=" + urllib.parse.quote(q) + "&currency=USD"
        subprocess.run(["curl", "-s", "--compressed", "-x", "api.zyte.com:8011", "-U", _key() + ":", "-k",
                        url, "-o", str(f), "--max-time", "120"], check=False)
    return f.read_text(errors="ignore") if f.exists() else ""
def norm(s): return re.sub(r"[^A-Z0-9]", "", s.upper())
def lookup(q):
    h = fetch(q).replace('\\"', '"')
    mpns = list(dict.fromkeys(re.findall(r'"mpn":"([^"]+)"', h)))
    skus = sorted(set(re.findall(r'"sku":"([^"]+)"', h)))
    mouser = [s for s in skus if re.match(r"^\d{2,3}-", s) and not s.endswith("-ND")]
    return {"mpns": mpns, "skus": skus, "mouser": mouser, "bytes": len(h)}
if __name__ == "__main__":
    import sys, json
    for q in sys.argv[1:]:
        r = lookup(q); print(q, "→", json.dumps({k: (v[:8] if isinstance(v, list) else v) for k, v in r.items()}))

def describe(mpn):
    """(exists, short description, sellers) for an exact MPN from its search page."""
    h = fetch(mpn).replace('\\"', '"')
    i = next((m.start() for m in re.finditer(r'"mpn":"%s"' % re.escape(mpn), h)), -1)
    desc = None
    if i >= 0:
        m = re.search(r'"short_description":"([^"]{0,160})"', h[i:i + 6000]) or re.search(r'"short_description":"([^"]{0,160})"', h[max(0, i - 6000):i])
        desc = m[1] if m else None
    sellers = sorted(set(re.findall(r'"company":\{[^{}]*?"name":"([^"]+)"', h)))[:12]
    return i >= 0, desc, sellers
