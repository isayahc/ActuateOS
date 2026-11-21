#!/usr/bin/env python3
"""Retrieve a single real IndustReal recording using HTTP byte ranges."""

import io
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "industreal"
BASE = "https://data.4tu.nl/file/b008dd74-020d-4ea4-a8ba-7bb60769d224/"
FILES = {
    "videos": ("cf21602e-4424-42a4-b05d-9897957082ad", 4960644152),
    "test_p1": ("ec7a4f94-7c1d-497d-b75a-4e694b7a9f7e", 7535688635),
    "geometry": ("4b6641cf-0034-4875-8ebb-73e35e4a5b91", 17338432),
    "ar_labels": ("778d7d5f-6631-4cb6-9451-f88c574c7991", 67816),
}


class RemoteZip(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position

    def read(self, length=-1):
        end = self.size if length < 0 else min(self.size, self.position + length)
        if end <= self.position:
            return b""
        req = Request(self.url, headers={"Range": f"bytes={self.position}-{end - 1}"})
        with urlopen(req, timeout=180) as response:
            if response.status != 206:
                raise RuntimeError("Server did not honor byte range; refusing a multi-GB download.")
            data = response.read()
        if len(data) != end - self.position:
            raise RuntimeError("Incomplete archive range")
        self.position = end
        return data


def archive(key):
    file_id, size = FILES[key]
    return zipfile.ZipFile(RemoteZip(BASE + file_id, size))


def prepare():
    DATA.mkdir(parents=True, exist_ok=True)
    sources = []
    selections = {
        "videos": lambda name: name == "03_assy_0_1.mp4",
        "test_p1": lambda name: name.startswith("03_assy_0_1/") and name.endswith(("AR_labels.csv", "PSR_labels.csv", "PSR_labels_with_errors.csv", "PSR_labels_raw.csv")),
        "geometry": lambda name: name.endswith((".3mf", ".pdf")),
    }
    for key, include in selections.items():
        with archive(key) as source:
            for member in source.infolist():
                if not include(member.filename):
                    continue
                target = DATA / Path(member.filename).name
                if not target.exists() or target.stat().st_size != member.file_size or zlib.crc32(target.read_bytes()) != member.CRC:
                    print(f"Downloading {member.filename} ({member.file_size:,} bytes)", flush=True)
                    target.write_bytes(source.read(member))
                sources.append({"file": target.name, "archive_url": BASE + FILES[key][0],
                                "member": member.filename, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    manifest = {
        "dataset": "IndustReal", "version": 2, "recording": "03_assy_0_1", "split": "test",
        "doi": "10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v2", "license": "Apache-2.0",
        "source_fps": 10, "sources": sources,
        "geometry_note": "Original dataset 3MF models; paper specifies printing at 200% scale. Placement is proposed, not measured from video.",
    }
    original = DATA / "03_assy_0_1.mp4"
    browser = DATA / "03_assy_0_1.browser.mp4"
    if not browser.exists():
        temporary = DATA / "03_assy_0_1.encoding.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(original),
                        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)], check=True)
        temporary.replace(browser)
    manifest["browser_video"] = {"file": browser.name, "sha256": hashlib.sha256(browser.read_bytes()).hexdigest(),
                                 "conversion": "MPEG-4 Part 2 source re-encoded as H.264 for browser playback; original timing retained."}
    (DATA / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Ready: {DATA}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", choices=FILES)
    parser.add_argument("--contains", default="")
    args = parser.parse_args()
    if args.list:
        with archive(args.list) as source:
            for member in source.infolist():
                if args.contains in member.filename:
                    print(member.filename, member.file_size)
    else:
        prepare()
