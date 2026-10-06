# sweep

**Reclaim your dev disk.** Find and delete `node_modules`, `.venv`, `target`, and build caches across every project — sorted by size, aware of age, and sent to the trash so every delete is reversible.

`npkill` has ~7k stars doing this for `node_modules` alone. `sweep` does it for your *whole* machine — Node, Python, Rust, JVM, Go, .NET, Xcode and more — in one size-sorted, age-aware interactive TUI, and defaults to the **trash** instead of `rm -rf`.

---

## Demo

```console
$ sweep ~/code

Scanning /home/dev/code ...

     SIZE    AGE  ECOSYSTEM  PATH
------------------------------------------------------------------
  8.91 GB   214d  rust       ~/code/graphengine/target
  6.40 GB   181d  node       ~/code/legacy-dashboard/node_modules
  5.12 GB    97d  apple      ~/code/ios-app/DerivedData
  4.88 GB    12d  node       ~/code/web/node_modules
  3.70 GB   140d  jvm        ~/code/android/.gradle
  2.95 GB   220d  python     ~/code/ml-spike/.venv
  2.11 GB    88d  node       ~/code/docs-site/.next
  1.64 GB   310d  rust       ~/code/old-cli/target
  ...
     41 MB    91d  python     ~/code/scripts/__pycache__

61 item(s), 47.3 GB reclaimable.
```

Interactive mode (the default in a terminal) lets you walk the list, `space`
to select the stale ones, and press `d`:

```console
About to move 9 item(s) (47.3 GB) to the trash:

      8.91 GB  ~/code/graphengine/target
      6.40 GB  ~/code/legacy-dashboard/node_modules
      5.12 GB  ~/code/ios-app/DerivedData
      ...
These go to the OS trash and can be restored.
Proceed? [y/N] y

trashed ~/code/graphengine/target
trashed ~/code/legacy-dashboard/node_modules
...
Reclaimed 47.3 GB.
```

Changed your mind about one? It's in your Recycle Bin / Trash. Restore it.

---

## Install

```bash
pipx install sweep-disk          # recommended
# or:  pip install sweep-disk
```

Zero required dependencies — the core runs on the Python 3.11+ standard
library. Installing the optional `send2trash` extra gives the most robust
cross-platform trash behavior:

```bash
pipx install "sweep-disk[trash]"
```

Run without installing:

```bash
python -m sweep ~/code --dry-run
```

---

## Usage

```text
sweep [PATH] [options]

  PATH                  Root directory to scan (default: current dir)

Filters:
  --min-size SIZE       Only show artifacts >= SIZE, e.g. 100MB, 1.5GB
  --older-than AGE      Only show artifacts not modified in >= AGE, e.g. 90d, 2w
  --ecosystem NAME      Limit to ecosystem(s), repeatable
                        (node, python, rust, jvm, go, php, dotnet, apple,
                         infra, generic)

Modes:
  --dry-run             Preview; never deletes
  --yes, -y             Delete all matches to trash without prompting
  --json                Emit findings as JSON (never deletes)
  --interactive, -i     Force the interactive TUI

  --workers N           Threads used to size directories (default: 8)
  --version
```

### Examples

```bash
# Interactive cleanup of your projects folder (TUI opens automatically)
sweep ~/code

# Just show me the big, abandoned stuff
sweep ~/code --min-size 500MB --older-than 90d

# Reclaim every Rust target/ older than six months, no questions asked
sweep ~/code --ecosystem rust --older-than 180d --yes

# Feed a dashboard / script
sweep ~/code --json | jq '.total_reclaimable_bytes'

# Safe preview — the default when piping or in CI
sweep ~/code --dry-run
```

---

## Features

- **Cross-ecosystem ruleset.** `node_modules`, `.next`, `.nuxt`, `.turbo`,
  `.svelte-kit`, `bower_components` (Node); `.venv`/`venv`, `__pycache__`,
  `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox` (Python); `target`
  (Rust); `.gradle` and `build` (JVM); `DerivedData`, `Pods` (Apple);
  `vendor` (Go/PHP); `bin`/`obj` (.NET); `.terraform`; and more — each tagged
  with its ecosystem.
- **Marker-guarded matching.** Generic names like `build`, `dist`, `vendor`
  and `obj` only match when the right manifest (`Cargo.toml`, `go.mod`,
  `composer.json`, `*.csproj`, …) sits beside them, so your real source
  folders are never flagged.
- **Size-sorted, age-aware.** Concurrent sizing, sorted largest-first, with a
  last-modified age for every entry and a highlight on anything stale
  (>90 days).
- **Reversible by default.** Deletes go to the OS trash (Windows Recycle Bin,
  macOS Trash, freedesktop.org Trash) — not `rm -rf`.
- **Scriptable.** `--dry-run`, `--json`, `--yes`, and rich filters make it
  usable in CI and cron, not just interactively.
- **Safe.** Never follows symlinks (no cycles, no double-counting), never
  descends into an already-matched directory, and surfaces permission errors
  instead of failing silently.
- **Importable core.** `from sweep import scan, filter_findings` — the whole
  engine is a pure, typed, fully-tested module you can build on.

---

## As a library

```python
import time
from sweep import scan, filter_findings
from sweep.humanize import human_size

stats = scan("~/code")
big = filter_findings(
    stats.findings,
    now=time.time(),
    min_size=500_000_000,          # 500 MB
    older_than_seconds=90 * 86400, # 90 days
)
for f in big:
    print(human_size(f.size_bytes), f.ecosystem, f.path)
```

---

## Limitations

- **"Size" is apparent size** (sum of file sizes), not on-disk blocks. On
  filesystems with compression, deduplication, or large block sizes the space
  actually freed can differ from the reported number.
- **Trash needs somewhere to go.** Moving to trash fails on filesystems/paths
  with no trash location (some network mounts, read-only volumes). `sweep`
  reports the error per item rather than hard-deleting as a fallback.
- **Huge trees take time.** Sizing is concurrent but still bounded by disk I/O;
  the first scan of a very large directory tree is not instant.
- **Rules are conservative, not exhaustive.** The built-in ruleset targets
  common regenerable caches. It won't catch every tool's cache, and it
  deliberately won't touch anything ambiguous. The ruleset lives in
  `sweep/rules.py` if you want to extend it.
- **Not a package manager.** `sweep` deletes artifacts; regenerating them
  (`npm install`, `cargo build`, …) is on you.

---

## Development

```bash
make dev        # editable install with dev + trash extras
make test       # pytest (73 tests)
make typecheck  # mypy --strict
make run        # sweep . --dry-run
```

The core has no third-party dependencies and the test suite also runs under
the standard library:

```bash
python -m unittest tests.test_core_unittest
```

---

## License

MIT © 2026 freyesperales

---

*Development Experiment 061 of dev-experiments-365.*
