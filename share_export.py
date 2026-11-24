#!/usr/bin/env python3
"""Share an export folder privately via Scaleway Object Storage (S3).

  python3 share_export.py FOLDER [--format both|7z|dmg] [--days 7] [--bucket B] [--region fr-par]

1. Packs FOLDER with a fresh random password (no look-alike characters):
   7z  — AES-256, file names encrypted too (-mhe); opens with 7-Zip / Keka;
   dmg — AES-256 encrypted, compressed disk image; macOS opens it natively
         (double-click, password, it mounts). macOS only.
2. Uploads it to the PRIVATE bucket (s3.<region>.scw.cloud) with the aws CLI.
3. Prints a pre-signed download link (max 7 days) and the password ONCE —
   send the two over different channels. Nothing secret is written to disk
   except the temporary archive, which is deleted afterwards.

Credentials come from .env (never printed): SCALEWAY_ACCESS_KEY (SCW…),
SCALEWAY_KEY (secret), optional SCALEWAY_BUCKET / SCALEWAY_REGION.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import secrets
import shutil
import string
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent


def _env() -> dict:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _password(n: int = 24) -> str:
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "lI1O0o")
    return "".join(secrets.choice(alphabet) for _ in range(n))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--days", type=int, default=7, help="link validity, 1-7 days")
    ap.add_argument("--format", choices=("both", "7z", "dmg"), default="both",
                    help="both = a .dmg for macOS and a .7z for Windows (separate passwords)")
    ap.add_argument("--bucket")
    ap.add_argument("--region")
    a = ap.parse_args()
    env = _env()
    ak, sk = env.get("SCALEWAY_ACCESS_KEY"), env.get("SCALEWAY_KEY")
    bucket = a.bucket or env.get("SCALEWAY_BUCKET")
    region = a.region or env.get("SCALEWAY_REGION", "fr-par")
    if not (ak and sk and bucket):
        print("missing SCALEWAY_ACCESS_KEY / SCALEWAY_KEY / SCALEWAY_BUCKET in .env", file=sys.stderr)
        return 1
    src = pathlib.Path(a.folder).resolve()
    if not src.is_dir():
        print(f"not a folder: {src}", file=sys.stderr)
        return 1
    seven = shutil.which("7zz") or shutil.which("7z")
    s3env = {**os.environ, "AWS_ACCESS_KEY_ID": ak, "AWS_SECRET_ACCESS_KEY": sk,
             "AWS_DEFAULT_REGION": region}
    endpoint = f"https://s3.{region}.scw.cloud"
    days = max(1, min(a.days, 7))
    fmts = ("dmg", "7z") if a.format == "both" else (a.format,)
    who = {"dmg": "macOS — double-click, enter the password, it mounts",
           "7z": "Windows — open with 7-Zip"}
    for fmt in fmts:
        pw = _password()                              # one password per file
        name = f"{src.parent.name}_{src.name}.{fmt}" if src.parent != REPO else f"{src.name}.{fmt}"
        with tempfile.TemporaryDirectory() as td:
            arc = pathlib.Path(td) / name
            if fmt == "dmg":
                subprocess.run(["hdiutil", "create", "-quiet", "-fs", "HFS+", "-format", "UDZO",
                                "-encryption", "AES-256", "-stdinpass", "-volname", src.name,
                                "-srcfolder", str(src), str(arc)],
                               input=pw.encode(), check=True)
            else:
                subprocess.run([seven, "a", "-t7z", "-mx=7", "-mhe=on", f"-p{pw}", str(arc), "."],
                               cwd=src, check=True, stdout=subprocess.DEVNULL)
            size = arc.stat().st_size
            key = f"exports/{name}"
            subprocess.run(["aws", "s3", "cp", str(arc), f"s3://{bucket}/{key}",
                            "--endpoint-url", endpoint, "--only-show-errors"], env=s3env, check=True)
        url = subprocess.run(["aws", "s3", "presign", f"s3://{bucket}/{key}", "--endpoint-url", endpoint,
                              "--expires-in", str(days * 86400)],
                             env=s3env, check=True, capture_output=True, text=True).stdout.strip()
        print(f"\n== {who[fmt]}")
        print(f"uploaded {name} ({size / 1e6:.0f} MB) to {bucket}/{key}")
        print(f"link (valid {days} days):\n{url}")
        print(f"password (send separately, e.g. by phone / Signal):\n{pw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
