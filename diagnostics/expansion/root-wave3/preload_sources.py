"""Populate the pinned public cache with bounded ranged HTTP reads; no solver."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen
from sudoku import expanded_data as data

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data/expanded/source-cache"
SIZES = {"easy.txt": 10000000, "medium.txt": 35264300,
         "hard.txt": 32159200, "diabolical.txt": 11968100}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    if (CACHE / "receipt.json").exists():
        data.cache_sources(CACHE)
        print("Verified existing pinned source cache", flush=True)
        return
    receipts = []
    for name in [group + ".txt" for group in data.GROUPS] + ["LICENSE.txt", "README.md"]:
        target = CACHE / name
        old = ROOT / "data/source" / ("sudoku-exchange-" + name)
        expected = data.PINNED_KNOWN_HASHES.get(name)
        if target.exists():
            # A cancelled original downloader may have published a complete file.
            # Admit it only after comparing with the pinned GitHub blob identity.
            url = f"https://api.github.com/repos/grantm/sudoku-exchange-puzzle-bank/contents/{name}?ref={data.COMMIT}"
            with urlopen(Request(url, headers={"User-Agent": "Sudoku-BTL1-expanded-data"}), timeout=20) as response:
                metadata = json.load(response)
            raw = target.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if len(raw) != metadata["size"] or blob != metadata["sha"]:
                raise RuntimeError("Unreceipted source differs from pinned GitHub blob: " + name)
        elif old.is_file() and expected and hashlib.sha256(old.read_bytes()).hexdigest() == expected:
            shutil.copyfile(old, target)
        elif name in SIZES:
            size = SIZES[name]
            chunk = 1048576
            ranges = [(start, min(start + chunk, size) - 1) for start in range(0, size, chunk)]

            def fetch(bounds):
                start, end = bounds
                request = Request(data.SOURCE_BASE + name, headers={
                    "User-Agent": "Sudoku-BTL1-expanded-data",
                    "Range": f"bytes={start}-{end}",
                })
                with urlopen(request, timeout=25) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise RuntimeError("Unexpected ranged response: " + name)
                    raw = response.read(end - start + 2)
                if len(raw) != end - start + 1:
                    raise RuntimeError("Truncated source range: " + name)
                return raw

            print("Downloading pinned source in bounded ranges: " + name, flush=True)
            with ThreadPoolExecutor(max_workers=4) as pool:
                parts = list(pool.map(fetch, ranges))
            with target.open("xb") as stream:
                for raw in parts:
                    stream.write(raw)
        else:
            with urlopen(Request(data.SOURCE_BASE + name, headers={"User-Agent": "Sudoku-BTL1-expanded-data"}), timeout=20) as response:
                raw = response.read(1048576)
            with target.open("xb") as stream:
                stream.write(raw)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected and digest != expected:
            raise RuntimeError("Pinned source digest mismatch: " + name)
        receipts.append({"file": name, "url": data.SOURCE_BASE + name, "sha256": digest})
        print("READY", name, target.stat().st_size, digest, flush=True)
    with (CACHE / "receipt.json").open("xb") as stream:
        stream.write(data.json_bytes({"source_commit": data.COMMIT, "files": receipts}))
    data.cache_sources(CACHE)
    (Path(__file__).parent / "source-preload-verification.json").write_text(json.dumps({
        "status": "PASS", "source_commit": data.COMMIT, "files": receipts,
        "solver_calls": 0, "total_bytes": sum((CACHE / row["file"]).stat().st_size for row in receipts),
    }, indent=2) + "\n", encoding="utf-8")
    print("ALL_PINNED_SOURCES_READY; solver_calls=0", flush=True)


if __name__ == "__main__":
    main()
