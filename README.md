# sf_to_ia

Automatically mirror a SourceForge project to Internet Archive. Scrapes the SourceForge file listing, downloads each file one at a time, uploads it to an Internet Archive item, then deletes the local copy — keeping disk usage minimal.

## Features

- Recursively mirrors all files and folders from any public SourceForge project
- Auto-generates an Internet Archive identifier from the project name
- Preserves original folder structure on IA
- Skips files already uploaded — safe to re-run after interruption
- Downloads and deletes one file at a time (no large disk space needed)
- Dry-run mode to preview files before uploading

## Requirements

- Python 3.10+
- A free [Internet Archive account](https://archive.org/account/signup)

## Installation

```bash
pip install requests internetarchive tqdm
```

On Debian/Ubuntu systems that block system-wide pip installs:

```bash
pip install requests internetarchive tqdm --break-system-packages
```

## Authentication

Run this once to save your Internet Archive credentials:

```bash
ia configure
```

Enter your archive.org email and password when prompted.

## Usage

```bash
python3 sf_to_ia.py <sourceforge_project_url> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `sf_url` | SourceForge project URL (required) |
| `--dry-run` | List all files without downloading or uploading |
| `--keep-files` | Keep downloaded files after uploading (default: delete) |
| `--delay` | Seconds to wait between uploads (default: 2.0) |
| `--creator` | Creator field in IA metadata (default: `sf_to_ia.py`) |
| `--title` | Title for the IA item (default: project name) |

### Examples

Preview what would be mirrored:
```bash
python3 sf_to_ia.py https://sourceforge.net/projects/myproject --dry-run
```

Mirror a project with default settings:
```bash
python3 sf_to_ia.py https://sourceforge.net/projects/myproject
```

Mirror with a custom title and creator:
```bash
python3 sf_to_ia.py https://sourceforge.net/projects/myproject --title "My Project Archive" --creator "myusername"
```

Mirror with a slower upload rate:
```bash
python3 sf_to_ia.py https://sourceforge.net/projects/myproject --delay 5
```

## Output

The IA item is created at:
```
https://archive.org/details/sourceforge-<projectname>
```

For example, `https://sourceforge.net/projects/sevenzip` would be mirrored to:
```
https://archive.org/details/sourceforge-sevenzip
```

> Note: Newly created IA items can take 5–30 minutes to become publicly accessible.

## Running in the Background

To keep the script running after closing your SSH session, use `tmux`, `byobu`, or `nohup`.

**With byobu (recommended):**
```bash
byobu
python3 sf_to_ia.py https://sourceforge.net/projects/myproject
# Detach with F6, reattach later by running: byobu
```

**With nohup (fire and forget):**
```bash
nohup python3 sf_to_ia.py https://sourceforge.net/projects/myproject > output.log 2>&1 &
tail -f output.log   # follow progress
```

## Notes

- The script uses HTML scraping instead of the SourceForge REST API, since the REST API does not support non-standard file mount points used by some projects.
- Files are downloaded to `/tmp/sf_<projectname>/` and deleted after each successful upload unless `--keep-files` is passed.
- Both downloads and uploads are retried up to 3 times on failure.
