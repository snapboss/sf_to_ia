#!/usr/bin/env python3
"""
sf_to_ia.py — Mirror a SourceForge project to Internet Archive
Usage: python3 sf_to_ia.py <sourceforge_project_url>
Example: python3 sf_to_ia.py https://sourceforge.net/projects/personal-roms
"""

import sys
import re
import time
import argparse
import requests
import internetarchive as ia
from tqdm import tqdm
from pathlib import Path
from datetime import datetime

# ── helpers ───────────────────────────────────────────────────────────────────

def extract_project_name(url: str) -> str:
    m = re.search(r"sourceforge\.net/projects/([^/?\s]+)", url)
    if not m:
        raise ValueError(f"Could not parse project name from URL: {url}")
    return m.group(1).strip("/")


def make_ia_identifier(project: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "-", project.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return f"sourceforge-{slug}"[:100]


def sf_scrape_list(project: str, path: str = "") -> list[dict]:
    """
    Recursively list all files by scraping the SF files HTML pages.
    path is relative, e.g. "" for root, "LineageOS-personal" for a subfolder.
    Returns a flat list of dicts: {name, path, url}
    """
    url = f"https://sourceforge.net/projects/{project}/files/{path}"
    resp = requests.get(url, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    # Each file/folder is a <tr title="NAME" class="folder "> or class="file ">
    rows = re.findall(r'<tr\s+title="([^"]+)"\s+class="(folder|file)\s*"', html)

    results = []
    for name, kind in rows:
        if name == "{{name}}":   # template placeholder row, skip
            continue
        entry_path = f"{path}/{name}".lstrip("/") if path else name
        if kind == "folder":
            sub = sf_scrape_list(project, entry_path)
            results.extend(sub)
            time.sleep(0.5)      # be polite between folder requests
        else:
            results.append({
                "name": name,
                "path": entry_path,
                "url":  f"https://sourceforge.net/projects/{project}/files/{entry_path}/download",
            })
    return results


def stream_download(url: str, dest: Path, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True,
                              timeout=120, allow_redirects=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f, tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"    {dest.name}",
                    leave=False,
                ) as bar:
                    for chunk in r.iter_content(chunk_size=1 << 17):
                        f.write(chunk)
                        bar.update(len(chunk))
            return True
        except Exception as e:
            print(f"    [attempt {attempt}/{retries}] download error: {e}")
            time.sleep(5 * attempt)
    return False


def ia_file_exists(identifier: str, remote_name: str) -> bool:
    try:
        item = ia.get_item(identifier)
        existing = {f["name"] for f in item.files}
        return remote_name in existing
    except Exception:
        return False


def ia_item_owned_by_me(identifier: str) -> bool:
    """Return True if the IA item doesn't exist yet, or we have write access."""
    try:
        item = ia.get_item(identifier)
        if not item.exists:
            return True
        r = ia.modify_metadata(identifier, metadata={})
        return r.status_code in (200, 204)
    except Exception:
        return False


def find_free_identifier(base: str) -> str:
    """
    Find an IA identifier we can write to.
    Tries base, then base-2, base-3, ... up to base-99.
    """
    item = ia.get_item(base)
    if not item.exists:
        return base
    if ia_item_owned_by_me(base):
        return base
    for n in range(2, 100):
        candidate = f"{base}-{n}"
        item = ia.get_item(candidate)
        if not item.exists:
            print(f"  Identifier '{base}' is taken — using '{candidate}'")
            return candidate
        if ia_item_owned_by_me(candidate):
            print(f"  Identifier '{base}' is taken — using '{candidate}'")
            return candidate
    raise RuntimeError(f"Could not find a free IA identifier starting with '{base}'")


def upload_to_ia(identifier: str, local_path: Path,
                 remote_name: str, metadata: dict,
                 retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            r = ia.upload(
                identifier,
                files={remote_name: str(local_path)},
                metadata=metadata,
                checksum=True,
                retries=3,
            )
            if r and r[0].status_code in (200, 201):
                return True
            print(f"    [attempt {attempt}] IA returned status {r[0].status_code}")
        except Exception as e:
            print(f"    [attempt {attempt}/{retries}] upload error: {e}")
            time.sleep(10 * attempt)
    return False


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Mirror a SourceForge project to Internet Archive")
    parser.add_argument("sf_url",
                        help="SourceForge project URL")
    parser.add_argument("--keep-files", action="store_true",
                        help="Keep downloaded files after uploading (default: delete)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files but do not download or upload")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between uploads (default: 2)")
    parser.add_argument("--creator", default="sf_to_ia.py",
                        help="Creator field for IA metadata (default: sf_to_ia.py)")
    parser.add_argument("--title", default=None,
                        help="Title for IA item (default: project name)")
    args = parser.parse_args()

    # 1. parse project
    project = extract_project_name(args.sf_url)
    base_id = make_ia_identifier(project)
    print(f"\n  SourceForge project : {project}")
    print(f"  Checking IA identifier…")
    try:
        identifier = find_free_identifier(base_id)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)
    print(f"  IA identifier       : {identifier}")

    # 2. scrape file list
    print("\n  Scraping file list from SourceForge…")
    try:
        files = sf_scrape_list(project)
    except Exception as e:
        print(f"  ERROR: could not list files — {e}")
        sys.exit(1)

    if not files:
        print("  No files found. Exiting.")
        sys.exit(0)

    print(f"  Found {len(files)} file(s)\n")

    if args.dry_run:
        for f in files:
            print(f"  {f['path']}")
        print("\n  [dry-run] nothing downloaded or uploaded.")
        return

    # 3. IA metadata
    title = args.title if args.title else project
    metadata = {
        "title":       title,
        "description": (
            f"Automated mirror of the SourceForge project '{project}' "
            f"({args.sf_url}). Mirrored on {datetime.utcnow().strftime('%Y-%m-%d')}."
        ),
        "mediatype":   "software",
        "subject":     ["sourceforge", "mirror", project],
        "source":      args.sf_url,
        "creator":     args.creator,
    }

    # 4. download + upload
    work_dir = Path(f"/tmp/sf_{project}")
    work_dir.mkdir(parents=True, exist_ok=True)

    ok_count = skipped = failed = 0

    for i, f in enumerate(files, 1):
        remote_name = f["path"]
        local_path  = work_dir / remote_name

        print(f"  [{i}/{len(files)}] {remote_name}")

        if ia_file_exists(identifier, remote_name):
            print(f"    → already on IA, skipping")
            skipped += 1
            continue

        print(f"    ↓ downloading…")
        if not stream_download(f["url"], local_path):
            print(f"    ✗ download failed, skipping")
            failed += 1
            continue

        print(f"    ↑ uploading to archive.org/{identifier}/…")
        if upload_to_ia(identifier, local_path, remote_name, metadata):
            print(f"    ✓ done")
            ok_count += 1
        else:
            print(f"    ✗ upload failed")
            failed += 1

        if not args.keep_files and local_path.exists():
            local_path.unlink()

        time.sleep(args.delay)

    # 5. summary
    print(f"\n  ── Summary ──────────────────────────────────")
    print(f"  Uploaded : {ok_count}")
    print(f"  Skipped  : {skipped}  (already existed)")
    print(f"  Failed   : {failed}")
    print(f"  IA item  : https://archive.org/details/{identifier}")
    print()


if __name__ == "__main__":
    main()
