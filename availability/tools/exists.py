import sys, re
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import octo
from concurrent.futures import ThreadPoolExecutor
qs = sys.argv[1:]
def one(q):
    r = octo.lookup(q)
    hit = [m for m in r["mpns"] if octo.norm(m).startswith(octo.norm(q)[:10])]
    return q, hit[:6]
with ThreadPoolExecutor(6) as ex:
    for q, hit in ex.map(one, qs): print(f"{q:28} -> {hit}")
