import re
def rcode(ohm):
    if ohm == 0: return None
    if ohm < 100: return (f"{ohm:.1f}".replace(".", "R") if ohm < 10 else f"{ohm:.1f}".replace(".", "R"))[:4].ljust(4, "0")
    for div, s in ((1e6, "M"), (1e3, "K"), (1, "R")):
        if ohm >= div:
            v = ohm / div; txt = f"{v:.3g}"
            if "." in txt: a, b = txt.split("."); code = a + s + b
            else: code = txt + s
            return code.ljust(4, "0")[:4] if s != "R" else (txt + "R")[:4]
def ohms(v):
    m = re.match(r"([\d.]+)\s*([kKmM]?)", v); x = float(m[1]); u = m[2]
    return x * {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3, "": 1}[u]
def capcode(f):   # farads → 3-digit
    pf = f * 1e12; e = 0
    while pf >= 100: pf /= 10; e += 1
    return f"{int(round(pf)):02d}{e}"
def farads(v):
    m = re.match(r"([\d.]+)\s*([pnu])", v); return float(m[1]) * {"p": 1e-12, "n": 1e-9, "u": 1e-6}[m[2]]
def avx0402(f):
    pf = f * 1e12
    return f"04025A{str(pf).rstrip('0').rstrip('.').replace('.', 'R') if pf < 10 and '.' in str(pf) else ''}" if False else None
def avx_code(pf):
    if pf < 10: return f"{pf:.1f}".replace(".", "R"), "B"
    return capcode(pf * 1e-12), "J"
def wurth_kI(nh):
    return f"7447650{int(round(nh*10)):02d}A" if nh < 10 else f"7447651{int(round(nh)):02d}A"
def candidates(mpn, desc):
    m = re.match(r"CRCW0402 ([\d.]+[kKM]?|[\d.]+m) 1% e3", mpn)
    if m:
        v = m[1]
        if v == "0": return ["CRCW04020000Z0ED"]
        if v == "10m": return ["WFCP0402R0100FE66"]
        if v == "200m": return ["RCWE0402R200FKEA"]
        o = ohms(v)
        if o < 100:
            code = (f"{o:.1f}".replace(".", "R")).ljust(4, "0")[:4]
        else:
            code = rcode(o)
        return [f"CRCW0402{code}FKED"]
    m = re.match(r"C0402 X7R ([\d.]+[pnu]F)", mpn)
    if m: return [f"C0402C{capcode(farads(m[1]))}K3RACTU"]
    m = re.match(r"C-Series MIL-PRF-32535 X7R 0603 ([\d.]+[pnu]F)", mpn)
    if m: c = capcode(farads(m[1])); return [f"C0603C{c}K5RACTU", f"C0603C{c}K3RACTU"]
    if mpn.startswith("TBD 0402 C0G/NP0 1nF") and "KEMET" in desc or mpn.startswith("TBD 0402 C0G/NP0 1nF"):
        if "1nF" in mpn: return ["C0402C102J3GACTU"]
    if mpn.startswith("TBD 0402 X5R 2.2uF"): return ["C0402C225M9PACTU"]
    m = re.match(r"TBD 0402 C0G/NP0 ([\d.]+)pF", mpn)
    if m:
        code, tol = avx_code(float(m[1])); return [f"04025A{code}{tol}AT2A"]
    m = re.match(r"SQCSVA ([\d.]+)pF", mpn)
    if m:
        code, tol = avx_code(float(m[1])); return [f"SQCSVA{code}{tol}AT1A"]
    m = re.match(r"WE-KI 0402 ([\d.]+)nH", mpn)
    if m: return [wurth_kI(float(m[1]))]
    m = re.match(r"T491T 22uF", mpn)
    if m: return ["T491T226K010AT"]
    if mpn.startswith("T528W 47uF"): return ["T528W476M016ATE030"]
    if mpn.startswith("T528W 100uF"): return ["T523W107M006APE070", "T523W107M016APE070"]
    if mpn.startswith("T528W 470uF"): return ["T528W477M1R8ATE007"]
    if mpn == "MT29F4G01ABAFDWB-IT_F": return ["MT29F4G01ABAFDWB-IT:F", "MT29F4G01ABAFDWB-IT"]
    if mpn == "PMEG6010CEJ": return ["PMEG6010CEJ,115", "PMEG6010CEJ"]
    if mpn == "LTC5549IUDB#TRMPBF": return ["LTC5549IUDB#TRMPBF", "LTC5549IUDB#PBF", "LTC5549IUDB"]
    if mpn.startswith("XGL5020"): return [mpn]
    return []
