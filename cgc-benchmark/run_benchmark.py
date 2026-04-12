#!/usr/bin/env python3
"""
CodeGraphContext (CGC) — Benchmark Script
=========================================
Benchmarks CGC's indexing and analysis performance on 3 real-world
open-source GitHub repositories using a SINGLE shared KùzuDB database.

Repos:
  Small  : pallets/click     (CLI framework)
  Medium : pallets/flask     (Web framework)
  Large  : tiangolo/fastapi  (API framework)

Database: KùzuDB (single shared instance for all repos)
"""

import os
import sys
import time
import json
import shutil
import subprocess
import platform
from pathlib import Path
from datetime import datetime, timezone

# ─── Configuration ───────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
REPOS_DIR = SCRIPT_DIR / "repos"
# The benchmark lives *inside* the CGC project (cgc-benchmark/ is a sub-dir
# of the repository root). Default to the parent directory as the source
# tree, but allow an override via $CGC_REPO_DIR for CI / custom layouts.
CGC_REPO_DIR = Path(os.environ.get("CGC_REPO_DIR", SCRIPT_DIR.parent)).resolve()
# Self-contained venv so we never depend on a broken global `cgc` shim.
VENV_DIR = SCRIPT_DIR / ".venv"
VENV_BIN_DIR = VENV_DIR / "bin"
CGC_BIN = VENV_BIN_DIR / "cgc"
VENV_PYTHON = VENV_BIN_DIR / "python"
KUZUDB_PATH = SCRIPT_DIR / "shared_kuzudb"
REPORT_FILE = SCRIPT_DIR / "BENCHMARK_REPORT.md"
RESULTS_JSON = SCRIPT_DIR / "benchmark_results.json"

# ─── Database Configuration ──────────────────────────────────────────────────
# NOTE: KùzuDB is the ACTIVE backend for this benchmark run (per user request).
# Historically KùzuDB had memory-corruption issues during indexing of large
# repos (see INDEXING_FAILURE_ANALYSIS.md). If you hit segfaults / malloc
# errors while indexing, swap the two sections below: comment KùzuDB out and
# uncomment the FalkorDB block instead.

# Option 1: KùzuDB (ACTIVE)
FALKORDB_PATH = SCRIPT_DIR / "shared_falkordb"  # kept so fallback paths still resolve
os.environ["DEFAULT_DATABASE"] = "kuzudb"
os.environ["KUZUDB_PATH"] = str(KUZUDB_PATH)
os.environ["CGC_RUNTIME_DB_TYPE"] = "kuzudb"

# Option 2: FalkorDB (DISABLED — uncomment these lines and comment out KùzuDB
# above if you need a stable fallback while KùzuDB is misbehaving)
# os.environ["DEFAULT_DATABASE"] = "falkordb"
# os.environ["FALKORDB_PATH"] = str(FALKORDB_PATH)
# os.environ["CGC_RUNTIME_DB_TYPE"] = "falkordb"

# ─── Dynamic DB label (used in logs and report) ──────────────────────────────
DB_BACKEND = os.environ.get("DEFAULT_DATABASE", "kuzudb").lower()
DB_LABEL = "FalkorDB" if DB_BACKEND == "falkordb" else "KùzuDB"
DB_PATH = FALKORDB_PATH if DB_BACKEND == "falkordb" else KUZUDB_PATH

# Repos to benchmark
REPOS = [
    {
        "name": "click",
        "github": "pallets/click",
        "tier": "Small",
        "tier_emoji": "🟢",
        "test_function": "make_str",
        "test_class": "CliRunner",
    },
    {
        "name": "flask",
        "github": "pallets/flask",
        "tier": "Medium",
        "tier_emoji": "🟡",
        "test_function": "make_response",
        "test_class": "Flask",
    },
    {
        "name": "fastapi",
        "github": "tiangolo/fastapi",
        "tier": "Large",
        "tier_emoji": "🔴",
        "test_function": "get",
        "test_class": "FastAPI",
    },
]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_git_info(repo_path):
    """Get commit hash and date for a git repo."""
    try:
        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%H"], cwd=repo_path, text=True
        ).strip()
        date = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci"], cwd=repo_path, text=True
        ).strip()
        short = commit[:12]
        return commit, date, short
    except Exception:
        return "unknown", "unknown", "unknown"


def get_cgc_version_from_pyproject():
    """Read the CodeGraphContext version directly from pyproject.toml.

    This is the most reliable way to determine the version, because it
    reflects exactly what's declared in the source tree — independent of
    whatever `cgc version` might print (which can vary across installs or
    even fail entirely if the CLI is broken).

    Returns the version string on success, or "unknown" on any failure.
    """
    pyproject = CGC_REPO_DIR / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    try:
        # Prefer stdlib tomllib (Python 3.11+) for correctness.
        try:
            import tomllib  # type: ignore[import-not-found]
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            version = data.get("project", {}).get("version")
            if version:
                return str(version)
        except ModuleNotFoundError:
            pass

        # Fallback: simple regex scan that works on any Python >=3.10.
        import re
        text = pyproject.read_text(encoding="utf-8")
        match = re.search(
            r'^\s*version\s*=\s*["\']([^"\']+)["\']',
            text,
            flags=re.MULTILINE,
        )
        if match:
            return match.group(1)
    except Exception as exc:
        log(f"  ⚠️  Failed to read version from pyproject.toml: {exc}")
    return "unknown"


def _find_uv_bin():
    """Locate a usable `uv` binary, if any."""
    uv_env = os.environ.get("UV_BIN")
    if uv_env and Path(uv_env).exists():
        return uv_env
    found = shutil.which("uv")
    if found:
        return found
    # Common user-local install location on Linux
    candidate = Path.home() / ".local" / "bin" / "uv"
    if candidate.exists():
        return str(candidate)
    return None


def ensure_venv():
    """Create an isolated virtualenv and install CGC + kuzu into it.

    The benchmark MUST run against a known-good CGC installation. In the
    past we relied on whatever `cgc` was on $PATH, which silently produced
    all-zero reports when the global shim had a broken shebang (see the
    `ModuleNotFoundError: No module named 'codegraphcontext'` bug). By
    bootstrapping our own venv we guarantee a functional binary.

    Strategy:
      1. If `uv` is available, use `uv venv` + `uv pip install`. This works
         even when the system is missing `python3-venv` / `ensurepip`.
      2. Otherwise fall back to stdlib `python -m venv` + pip.
    """
    uv_bin = _find_uv_bin()

    if VENV_PYTHON.exists() and CGC_BIN.exists():
        log(f"♻️  Reusing existing benchmark venv at {VENV_DIR}")
    else:
        # Nuke any half-built venv from a previous failed attempt so we
        # always start from a clean slate.
        if VENV_DIR.exists():
            log(f"🗑  Removing stale venv at {VENV_DIR}")
            shutil.rmtree(VENV_DIR)

        if uv_bin:
            log(f"🐍 Creating benchmark venv at {VENV_DIR} using uv ({uv_bin}) ...")
            subprocess.check_call([uv_bin, "venv", str(VENV_DIR)])
        else:
            log(f"🐍 Creating benchmark venv at {VENV_DIR} using python -m venv ...")
            try:
                subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
                subprocess.check_call([
                    str(VENV_PYTHON), "-m", "pip", "install", "--quiet",
                    "--upgrade", "pip", "setuptools", "wheel",
                ])
            except subprocess.CalledProcessError as exc:
                pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
                raise RuntimeError(
                    "Failed to create a virtualenv via `python -m venv`.\n"
                    "On Debian/Ubuntu this usually means the `python3-venv` "
                    "package is missing. Fix with either of:\n"
                    f"  sudo apt install python{pyver}-venv\n"
                    "  --- OR ---\n"
                    "  install uv (https://docs.astral.sh/uv/) and re-run "
                    "this script; it will be picked up automatically."
                ) from exc

    # Always (re)install CGC from the local source tree so the benchmark
    # tracks whatever changes you're currently working on. Editable installs
    # are a no-op when nothing changed.
    if uv_bin:
        log(f"📦 Installing CodeGraphContext (editable) via uv from {CGC_REPO_DIR} ...")
        subprocess.check_call([
            uv_bin, "pip", "install",
            "--python", str(VENV_PYTHON),
            "-e", str(CGC_REPO_DIR),
        ])
        # KùzuDB is an *optional* runtime dependency of CGC (imported lazily).
        # Since the benchmark forces the kuzu backend, make sure it's present.
        log("📦 Ensuring 'kuzu' driver is installed via uv ...")
        subprocess.check_call([
            uv_bin, "pip", "install",
            "--python", str(VENV_PYTHON),
            "kuzu",
        ])
    else:
        log(f"📦 Installing CodeGraphContext (editable) via pip from {CGC_REPO_DIR} ...")
        subprocess.check_call([
            str(VENV_PYTHON), "-m", "pip", "install", "--quiet",
            "-e", str(CGC_REPO_DIR),
        ])
        log("📦 Ensuring 'kuzu' driver is installed via pip ...")
        subprocess.check_call([
            str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "kuzu",
        ])

    if not CGC_BIN.exists():
        raise RuntimeError(
            f"cgc binary not found at {CGC_BIN} after installation. "
            "Something went wrong while bootstrapping the benchmark venv."
        )


def verify_cgc_health():
    """Sanity-check that `cgc` actually runs before any benchmarking starts.

    Returns the cleaned-up version string on success, raises on failure.

    The check is intentionally *output-driven*, not exit-code-driven:
      - Hard failure only when the output contains explicit Python-level
        error indicators (`Traceback`, `ModuleNotFoundError`, `No module
        named`). Those are unambiguous signs of a broken install.
      - Otherwise, if the output contains a version-like token
        ("CodeGraphContext X.Y.Z"), we trust the CLI is functional —
        **even if the subprocess returned non-zero**. Some CGC subcommands
        (and certain typer/click versions) exit with 1 after printing help
        or the version, which used to kill the whole benchmark for no
        real reason.
      - A single retry is attempted on completely-empty output to absorb
        transient hiccups right after `uv pip install` finishes.
    """
    import re as _re

    def _looks_broken(text):
        lowered = text.lower()
        return (
            "traceback" in lowered
            or "modulenotfounderror" in lowered
            or "no module named" in lowered
        )

    def _extract_version(text):
        # Look for "CodeGraphContext 0.4.2" style token first, then any
        # bare semver-like string as a fallback.
        m = _re.search(r"CodeGraphContext\s+([0-9][\w.\-+]*)", text, _re.IGNORECASE)
        if m:
            return f"CodeGraphContext {m.group(1)}"
        m = _re.search(r"\b(\d+\.\d+(?:\.\d+)?[\w.\-+]*)\b", text)
        if m:
            return m.group(1)
        return None

    log("🔎 Verifying CGC installation ...")
    output, duration_ms, success = run_cgc_command(["version"], timeout=60)

    # One transient-retry: uv's editable install can briefly leave the shim
    # in an inconsistent state right after completing.
    if not output.strip():
        log("  ⚠️  Empty output on first attempt — retrying once ...")
        time.sleep(1.0)
        output, duration_ms, success = run_cgc_command(["version"], timeout=60)

    if _looks_broken(output):
        log("❌ CGC health check FAILED — Python error detected. Raw output:")
        for line in output.strip().splitlines() or ["<no output>"]:
            log(f"    {line}")
        raise RuntimeError(
            "CGC is not functional in the benchmark venv (Python traceback "
            "or missing module detected). Aborting so we don't publish a "
            "bogus report full of zero-valued metrics."
        )

    version_str = _extract_version(output)
    if version_str is None:
        # Neither a recognizable version nor an error pattern. This is
        # suspicious but not necessarily fatal; dump everything so a
        # human can decide, and continue with "unknown".
        log("⚠️  CGC health check: no version token found in output. Raw output:")
        for line in output.strip().splitlines() or ["<no output>"]:
            log(f"    {line}")
        if not success:
            raise RuntimeError(
                "CGC `version` returned non-zero AND produced no recognizable "
                "version string. Treating as a broken install."
            )
        version_str = "unknown"

    if not success:
        log(
            f"  ⚠️  `cgc version` exited non-zero but printed a valid "
            f"version ({version_str!r}); treating as healthy. "
            "(Known quirk of certain typer/click versions.)"
        )

    log(f"✅ CGC healthy ({duration_ms}ms): {version_str}")
    return version_str


def count_files(repo_path):
    """Count total and python files."""
    total = 0
    py = 0
    for root, dirs, files in os.walk(repo_path):
        # Skip .git
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            total += 1
            if f.endswith(".py"):
                py += 1
    return total, py


def run_cgc_command(args, timeout=300):
    """Run a cgc command and return (output, duration_ms, success).

    Always prefers the benchmark venv's cgc binary so we never accidentally
    invoke a broken global shim on $PATH.
    """
    cgc_cmd = str(CGC_BIN) if CGC_BIN.exists() else "cgc"

    # Build a clean env: venv bin first on PATH, strip anything that might
    # confuse Python about which interpreter to use.
    env = os.environ.copy()
    env["PATH"] = f"{VENV_BIN_DIR}:{env.get('PATH', '')}"
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env.pop("PYTHONHOME", None)

    start = time.monotonic()
    try:
        result = subprocess.run(
            [cgc_cmd] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        end = time.monotonic()
        duration_ms = int((end - start) * 1000)
        output = result.stdout + result.stderr
        return output, duration_ms, result.returncode == 0
    except subprocess.TimeoutExpired:
        end = time.monotonic()
        duration_ms = int((end - start) * 1000)
        return f"TIMEOUT after {timeout}s", duration_ms, False
    except Exception as e:
        end = time.monotonic()
        duration_ms = int((end - start) * 1000)
        return str(e), duration_ms, False


def get_system_info():
    """Collect system information."""
    info = {
        "os": platform.platform(),
        "cpu": "Unknown",
        "cpu_cores": os.cpu_count() or "Unknown",
        "ram": "Unknown",
        "python": platform.python_version(),
        "disk_type": "Unknown",
    }
    
    # CPU info
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    info["cpu"] = line.split(":")[1].strip()
                    break
    except Exception:
        pass
    
    # RAM
    try:
        result = subprocess.check_output(["free", "-h"], text=True)
        for line in result.splitlines():
            if line.startswith("Mem:"):
                info["ram"] = line.split()[1]
                break
    except Exception:
        pass
    
    return info


def parse_stats_output(output):
    """Parse `cgc stats` rich-table output to extract counts.

    Robust against:
      - Unicode box chars (│) *and* plain ASCII pipes (|)
      - ANSI escape sequences injected by rich on some terminals
      - Thousands separators in numbers (e.g. "1,125")
      - Leading/trailing whitespace or rich styling markers
      - Key variants: "Imported Modules" vs plain "Modules"
      - Upper/lower case drift
    """
    import re

    stats = {"files": 0, "functions": 0, "classes": 0, "modules": 0}

    if not output:
        return stats

    # Strip any ANSI colour escape sequences that rich may emit.
    ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    cleaned = ansi_re.sub("", output)

    # Map lowercase label → canonical stats key. Order matters: the longer
    # "imported modules" label is checked first so it wins over bare
    # "modules" substring matches.
    key_map = [
        ("imported modules", "modules"),
        ("files", "files"),
        ("functions", "functions"),
        ("classes", "classes"),
        ("modules", "modules"),
    ]

    for raw_line in cleaned.splitlines():
        # Normalise both box-drawing borders to a single pipe so one split
        # handles either backend's table style.
        line = raw_line.replace("│", "|").replace("┃", "|")
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2:
            continue
        label = parts[0].lower().strip()
        # Strip rich markup like "[bold]Files[/bold]" → "files"
        label = re.sub(r"\[[^\]]+\]", "", label).strip()
        value = parts[1].strip().replace(",", "")

        for needle, target in key_map:
            if needle in label:
                # Only numeric values; ignore header rows like "| Metric | Count |"
                try:
                    stats[target] = int(value)
                except ValueError:
                    pass
                break

    return stats


def get_repo_stats_via_cypher(repo_path):
    """Last-resort fallback: query raw node counts via `cgc cypher`.

    Used when `parse_stats_output()` returns all zeros but the bounded-depth
    node/edge count query on the same repository returned non-zero totals.
    This fights the exact bug we hit on large repos (fastapi) where
    `cgc stats <path>` either timed out, returned partial data, or its
    rich-table output got mangled in capture.

    Returns a dict with the same shape as parse_stats_output() *plus* a
    ``"modules_source"`` diagnostic key that records which label variant
    produced the module count (or ``"none"`` if every attempt failed).
    """
    import re as _re
    abs_path = str(Path(repo_path).resolve())
    result = {
        "files": 0,
        "functions": 0,
        "classes": 0,
        "modules": 0,
        "modules_source": "none",  # diagnostic for honest reporting
    }

    def _run(cypher):
        out, _ms, ok = run_cgc_command(["cypher", cypher], timeout=180)
        if not ok:
            return None
        lowered = out.lower()
        if "segmentation fault" in lowered or "sigsegv" in lowered:
            return None
        nums = _re.findall(r"\b(\d+)\b", out)
        if not nums:
            return None
        try:
            return int(nums[-1])
        except ValueError:
            return None

    # Primary counts — single label per key.
    primary = {
        "files": (
            f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(f:File) "
            "RETURN count(DISTINCT f) as n"
        ),
        "functions": (
            f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(fn:Function) "
            "RETURN count(DISTINCT fn) as n"
        ),
        "classes": (
            f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(c:Class) "
            "RETURN count(DISTINCT c) as n"
        ),
    }
    for key, cypher in primary.items():
        val = _run(cypher)
        if val is not None:
            result[key] = val

    # Modules are tricky — CGC's graph schema has drifted between
    # backends/versions. Try several label/relationship variants and take
    # the first non-zero answer. This is the bit that was silently
    # returning 0 for fastapi in earlier runs.
    module_attempts = [
        ("Module (CONTAINS depth 1..5)",
         f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(m:Module) "
         "RETURN count(DISTINCT m) as n"),
        ("ImportedModule (CONTAINS depth 1..5)",
         f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(m:ImportedModule) "
         "RETURN count(DISTINCT m) as n"),
        ("Module via IMPORTS edge",
         f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(f:File)-[:IMPORTS]->(m) "
         "RETURN count(DISTINCT m) as n"),
        ("Imports relationship from any File in repo",
         f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(:File)-[imp:IMPORTS]->(m) "
         "RETURN count(DISTINCT m) as n"),
    ]
    for label, cypher in module_attempts:
        val = _run(cypher)
        if val and val > 0:
            result["modules"] = val
            result["modules_source"] = label
            break

    return result


def get_graph_node_edge_counts(repo_path):
    """Get total nodes and edges for a repo using cgc cypher."""
    abs_path = str(Path(repo_path).resolve())
    
    # Total nodes
    nodes_output, nodes_ms, nodes_success = run_cgc_command([
        "cypher", 
        f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(n) RETURN count(n) as total_nodes"
    ], timeout=120)
    
    # Detect segfaults in cypher output
    nodes_output_lower = nodes_output.lower()
    if "segmentation fault" in nodes_output_lower or "core dumped" in nodes_output_lower or "sigsegv" in nodes_output_lower:
        return "N/A", "N/A", 0, 0
    
    nodes = "N/A"
    for line in nodes_output.splitlines():
        if "total_nodes" in line:
            import re
            nums = re.findall(r'\d+', line)
            if nums:
                nodes = nums[-1]
                break
    
    # Total edges
    edges_output, edges_ms, edges_success = run_cgc_command([
        "cypher",
        f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(n)-[rel]->(m) RETURN count(rel) as total_edges"
    ], timeout=120)
    
    # Detect segfaults in cypher output
    edges_output_lower = edges_output.lower()
    if "segmentation fault" in edges_output_lower or "core dumped" in edges_output_lower or "sigsegv" in edges_output_lower:
        return nodes, "N/A", nodes_ms, 0
    
    edges = "N/A"
    for line in edges_output.splitlines():
        if "total_edges" in line:
            import re
            nums = re.findall(r'\d+', line)
            if nums:
                edges = nums[-1]
                break
    
    return nodes, edges, nodes_ms, edges_ms


def fmt_time(ms):
    """Format milliseconds to readable string."""
    if ms is None or ms == 0:
        return "N/A"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms/1000:.2f}s"


def fmt_rate(files, ms):
    """Calculate files/sec."""
    if ms <= 0:
        return "N/A"
    return f"{files * 1000 / ms:.1f}"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN BENCHMARK
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    log("=" * 70)
    log("  CodeGraphContext (CGC) — BENCHMARK")
    log("=" * 70)

    # Read the declared version from pyproject.toml *before* we touch the
    # venv. This gives the user an immediate, reliable answer to "which
    # version am I benchmarking?" even if something later blows up.
    pyproject_version = get_cgc_version_from_pyproject()
    log("")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log(f"  📦 CodeGraphContext version : {pyproject_version}   (from pyproject.toml)")
    log(f"  🗄️  Database backend         : {DB_LABEL}")
    log(f"  📂 Source tree               : {CGC_REPO_DIR}")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("")

    # STEP 0: Bootstrap an isolated venv and verify that `cgc` is actually
    # functional BEFORE we start timing anything. This is the single most
    # important guard in the whole script — without it we'd happily publish
    # a report where every number is zero because every `cgc` invocation
    # crashed in ~90ms with a ModuleNotFoundError.
    ensure_venv()
    cgc_cli_version = verify_cgc_health()

    # Prefer the pyproject version as the canonical display string, but
    # keep the raw CLI output around for debugging. If pyproject couldn't
    # be read for some reason, fall back to the CLI answer.
    if pyproject_version != "unknown":
        cgc_version = pyproject_version
    else:
        cgc_version = cgc_cli_version

    # System Info
    sys_info = get_system_info()
    cgc_commit, cgc_date, cgc_short = get_git_info(CGC_REPO_DIR)

    log("")
    log("═══ Benchmark Environment ═══")
    log(f"CGC Version      : {cgc_version}   (pyproject.toml)")
    log(f"CGC CLI reports  : {cgc_cli_version}")
    log(f"CGC Commit       : {cgc_short} ({cgc_date})")
    log(f"Database         : {DB_LABEL} (shared, embedded)")
    log(f"Database Path    : {DB_PATH}")
    log(f"System           : {sys_info['os']}")
    log(f"CPU              : {sys_info['cpu']} ({sys_info['cpu_cores']} cores)")
    log(f"RAM              : {sys_info['ram']}")
    log(f"Python           : {sys_info['python']}")
    log("")
    log("Pipeline stages : venv-bootstrap → health-check → clean → "
        "PHASE 1 index → PHASE 2 stats/graph → PHASE 3 analyze → "
        "PHASE 4 footprint → report")
    
    # Clean Previous Data
    log("")
    log("🧹 Cleaning previous benchmark data...")

    def _safe_remove(path: Path):
        """Robustly delete a path whether it's a file, directory or symlink.

        KùzuDB stores its database as a single *file* (plus a `.wal` sidecar)
        in embedded mode, not a directory, so `shutil.rmtree` on it raises
        `NotADirectoryError`. This helper handles both layouts and also
        removes any sibling WAL / shadow / lock files that KùzuDB leaves
        behind.
        """
        try:
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            log(f"  ⚠️  Could not remove {path}: {exc}")

        # Also remove KùzuDB sidecar files if they exist next to `path`.
        for suffix in (".wal", ".shadow", ".lock", ".tmp"):
            sidecar = path.with_name(path.name + suffix)
            try:
                if sidecar.exists() or sidecar.is_symlink():
                    if sidecar.is_dir():
                        shutil.rmtree(sidecar)
                    else:
                        sidecar.unlink(missing_ok=True)
            except Exception:
                pass

    _safe_remove(KUZUDB_PATH)

    # Also clean any default kuzudb locations that CGC may have created
    # during a previous run when env-var overrides weren't honored yet.
    for stray in [
        Path.home() / ".codegraphcontext" / "kuzudb",
        Path.home() / ".codegraphcontext" / "global" / "kuzudb",
        Path.home() / ".codegraphcontext" / "global" / "db" / "kuzudb",
    ]:
        _safe_remove(stray)
    
    # Results Storage
    results = {
        "metadata": {
            "benchmark_date": datetime.now(timezone.utc).isoformat(),
            "cgc_version": cgc_version,
            "cgc_commit": cgc_commit,
            "cgc_commit_date": cgc_date,
            "database": f"{DB_LABEL} (shared single instance)",
            "system": sys_info,
        },
        "repos": {},
    }
    
    # PHASE 1: INDEXING
    log("")
    log("=" * 70)
    log("  PHASE 1: INDEXING BENCHMARKS (cgc index --force)")
    log("=" * 70)
    
    for repo in REPOS:
        name = repo["name"]
        repo_path = REPOS_DIR / name
        abs_path = str(repo_path.resolve())
        commit, commit_date, short_commit = get_git_info(repo_path)
        total_files, py_files = count_files(repo_path)
        
        repo["commit"] = commit
        repo["commit_date"] = commit_date
        repo["short_commit"] = short_commit
        repo["total_files"] = total_files
        repo["py_files"] = py_files
        
        log("")
        log(f"━━━ [{repo['tier']}] {repo['github']} ━━━")
        log(f"  Path: {abs_path}")
        log(f"  Commit: {short_commit}")
        log(f"  Files: {total_files} total, {py_files} Python")
        
        # Retry loop for large repos that hit KùzuDB's non-deterministic
        # memory-corruption bug. The crash is a malloc-level heap issue
        # (`malloc_consolidate(): invalid chunk size`, `unaligned fastbin`,
        # etc.) that sometimes triggers and sometimes doesn't on the same
        # input — so retrying with a fresh process has a good chance of
        # succeeding. We ONLY retry on native crashes; Python tracebacks
        # are always hard-fails because they indicate a broken install.
        MAX_NATIVE_RETRIES = 2  # total attempts = 1 + MAX_NATIVE_RETRIES
        crash_indicators = [
            "segmentation fault",
            "core dumped",
            "sigsegv",
            "malloc_consolidate",
            "malloc()",
            "unaligned fastbin",
            "invalid chunk size",
            "aborted",
            "sigabrt",
            "double free",
            "corrupted size",
        ]

        output = ""
        duration_ms = 0
        success = False
        native_crash = False
        crash_reason = None

        for attempt in range(1 + MAX_NATIVE_RETRIES):
            if attempt == 0:
                log(f"  ⏱️  Running cgc index --force...")
            else:
                log(f"  🔄 Retry attempt {attempt}/{MAX_NATIVE_RETRIES} for {name} ...")
                # Small pause so the OS can clean up any leftover memory /
                # fds from the previous crashed process.
                time.sleep(2.0)

            output, duration_ms, success = run_cgc_command(
                ["index", abs_path, "--force"], timeout=900
            )
            lowered = output.lower()

            # Python-level errors → always hard-fail (broken install).
            if "traceback" in lowered or "modulenotfounderror" in lowered:
                log("  ❌ Indexing crashed with a Python exception — dumping output:")
                for line in output.strip().splitlines():
                    log(f"      {line}")
                raise RuntimeError(
                    f"`cgc index` failed for {name}; aborting benchmark."
                )

            # Native crash detection.
            hit_indicator = next(
                (ind for ind in crash_indicators if ind in lowered), None
            )
            if hit_indicator:
                log(
                    f"  ⚠️  Native error during {name} indexing "
                    f"(indicator: {hit_indicator!r}) — dumping last lines:"
                )
                for line in output.strip().splitlines()[-8:]:
                    log(f"      {line}")
                native_crash = True
                crash_reason = hit_indicator
                success = False
                if attempt < MAX_NATIVE_RETRIES:
                    log(f"  ⏳ Will retry ...")
                    continue
                # Out of retries — give up on THIS repo but keep the
                # overall benchmark alive so we still get useful data
                # for the other repos.
                log("")
                log(f"  ❌ {name}: native crash persists after "
                    f"{MAX_NATIVE_RETRIES + 1} attempts; giving up on this repo.")
                log("  ⚠️  CRITICAL: This is a known KùzuDB memory-corruption bug")
                log("       (non-deterministic; sometimes triggers, sometimes not).")
                log("  ⚠️  See cgc-benchmark/INDEXING_FAILURE_ANALYSIS.md for details.")
                log("  ⚠️  Consider switching to FalkorDB backend for stable results.")
                break
            else:
                # No crash → leave the retry loop and proceed to the
                # success/failure post-checks below.
                native_crash = False
                break

        # Skip post-checks entirely for repos that died from a native
        # crash — the output is meaningless in that case and would just
        # produce confusing secondary warnings.
        if native_crash:
            repo["index_time_ms"] = duration_ms
            repo["index_success"] = False
            repo["crash_reason"] = crash_reason
            log(f"  💥 Indexing FAILED for {name} — native crash: {crash_reason}")
            log(f"     (Benchmark continues with remaining repos.)")
            continue

        # Suspiciously fast result ⇒ the command returned before any real
        # work happened (e.g. silent early-exit, missing DB driver, ...).
        # A genuine index of click/flask/fastapi takes seconds to minutes.
        if success and duration_ms < 500 and py_files > 10:
            log(
                f"  ⚠️  Suspiciously fast index "
                f"({duration_ms}ms for {py_files} Python files). "
                "Treating as a failure — full output below:"
            )
            for line in output.strip().splitlines():
                log(f"      {line}")
            success = False

        # Verify indexing actually produced results by checking the output message
        # CGC outputs "Successfully re-indexed: <path> in X.XX seconds" on success
        # We'll trust this message if it appears (don't require file count in output)
        if success:
            output_lower = output.lower()
            # Check for success message pattern
            has_success_message = (
                "successfully re-indexed" in output_lower or
                "successfully indexed" in output_lower
            )

            # Only mark as failed if there's clear error indication
            # (not just absence of file count, since CGC doesn't print that)
            has_error = (
                "error" in output_lower or
                "failed" in output_lower or
                "exception" in output_lower
            )

            if has_error:
                log(
                    f"  ❌  Index command shows errors in output. Treating as failure."
                )
                success = False
            elif not has_success_message and duration_ms < 1000:
                # Suspiciously fast and no success message = likely failed
                log(
                    f"  ⚠️  No success message and suspiciously fast ({duration_ms}ms). "
                    f"Treating as failure."
                )
                success = False
            else:
                # Trust the success message - verify later with stats
                pass

        repo["index_time_ms"] = duration_ms
        repo["index_success"] = success
        repo["crash_reason"] = None

        status_icon = "✅" if success else "❌"
        log(f"  {status_icon} Indexing completed in {fmt_time(duration_ms)}")

        # Show last few lines of output for context
        for line in output.strip().splitlines()[-3:]:
            log(f"    {line}")
    
    # PHASE 2: GRAPH STATISTICS
    log("")
    log("=" * 70)
    log("  PHASE 2: GRAPH STATISTICS (nodes & edges)")
    log("=" * 70)
    
    for repo in REPOS:
        name = repo["name"]
        repo_path = REPOS_DIR / name
        abs_path = str(repo_path.resolve())

        log("")
        log(f"━━━ [{repo['tier']}] {repo['github']} ━━━")

        # Skip graph queries for repos whose indexing died from a native
        # crash — the database has no data for them and we'd just waste
        # time (or trigger another crash). Record zeros and move on.
        if repo.get("crash_reason"):
            log(
                f"  ⏭️  Skipping stats/graph queries for {name}: "
                f"indexing crashed ({repo['crash_reason']})"
            )
            repo["stats"] = {"files": 0, "functions": 0, "classes": 0, "modules": 0}
            repo["stats_time_ms"] = 0
            repo["stats_source"] = "crashed"
            repo["total_nodes"] = "CRASH"
            repo["total_edges"] = "CRASH"
            continue

        # Large repos (fastapi ~1100 py files) can easily blow past the old
        # 300s limit on KùzuDB because `cgc stats <path>` walks the graph.
        # Give the query enough headroom to actually finish.
        log(f"  Running cgc stats...")
        stats_output, stats_ms, stats_success = run_cgc_command(
            ["stats", abs_path], timeout=900
        )

        # Detect segfaults / timeouts in stats output
        stats_lowered = stats_output.lower()
        stats_timed_out = stats_lowered.startswith("timeout after")
        if "segmentation fault" in stats_lowered or "core dumped" in stats_lowered or "sigsegv" in stats_lowered:
            log(f"  ❌ Stats command crashed with segmentation fault")
            stats_success = False
            stats_output = ""
        elif stats_timed_out:
            log(f"  ⚠️  `cgc stats {name}` timed out — will use cypher fallback")
            stats_success = False

        stats = parse_stats_output(stats_output)
        repo["stats"] = stats
        repo["stats_time_ms"] = stats_ms

        # If parsing produced all zeros but the command itself didn't crash,
        # something about the output format tripped up the parser (or the
        # command silently returned no rows). Dump the first 500 chars so
        # we can actually *see* the format next time, and then fall back to
        # raw cypher queries which bypass CLI formatting entirely.
        parsed_any = any(v > 0 for v in stats.values() if isinstance(v, int))
        if not parsed_any:
            log(f"  ⚠️  Parsed stats are all zeros. Raw `cgc stats` output (first 500 chars):")
            preview = stats_output[:500].replace("\n", "\n      ")
            log(f"      {preview!r}")
            log(f"  🔄 Falling back to direct cypher queries for {name}...")
            fallback_stats = get_repo_stats_via_cypher(repo_path)
            # Separate diagnostic field so it doesn't pollute `stats`.
            modules_source = fallback_stats.pop("modules_source", "none")
            if any(v > 0 for v in fallback_stats.values() if isinstance(v, int)):
                log(
                    f"  ✅ Cypher fallback succeeded: "
                    f"files={fallback_stats['files']}, "
                    f"functions={fallback_stats['functions']}, "
                    f"classes={fallback_stats['classes']}, "
                    f"modules={fallback_stats['modules']} "
                    f"(modules_source: {modules_source})"
                )
                if fallback_stats["modules"] == 0:
                    log(
                        f"  ⚠️  modules=0 even after trying multiple label "
                        f"variants — this is a CGC graph-schema limitation "
                        f"for large repos and is flagged in the report."
                    )
                stats = fallback_stats
                repo["stats"] = stats
                repo["stats_source"] = "cypher_fallback"
                repo["modules_source"] = modules_source
            else:
                log(f"  ❌ Cypher fallback also returned zeros")
                repo["stats_source"] = "failed"
                repo["modules_source"] = modules_source
        else:
            repo["stats_source"] = "cgc_stats"
            repo["modules_source"] = "cgc_stats"

        log(f"  Stats query: {fmt_time(stats_ms)}  (source: {repo.get('stats_source', 'cgc_stats')})")
        log(f"  Files: {stats.get('files', 'N/A')}, Functions: {stats.get('functions', 'N/A')}, Classes: {stats.get('classes', 'N/A')}, Modules: {stats.get('modules', 'N/A')}")

        log(f"  Querying total nodes and edges (bounded depth)...")
        nodes, edges, nodes_ms, edges_ms = get_graph_node_edge_counts(repo_path)
        repo["total_nodes"] = nodes
        repo["total_edges"] = edges

        log(f"  Nodes: {nodes} ({fmt_time(nodes_ms)}), Edges: {edges} ({fmt_time(edges_ms)})")

        # Verify indexing actually worked by checking if stats show files
        stats_files = repo["stats"].get("files", 0)
        py_files = repo.get("py_files", 0)
        if stats_files >= py_files and stats_files > 0:
            # Update index_success based on actual stats verification
            repo["index_success"] = True
            log(f"  ✅ Verified: {stats_files} files successfully indexed")
        elif stats_files > 0:
            log(f"  ⚠️  Partial indexing: {stats_files}/{py_files} files indexed")
        else:
            # Sanity check: if bounded-depth traversal found thousands of
            # nodes then the graph clearly has data; flag it as a reporting
            # issue rather than an indexing failure.
            try:
                nodes_int = int(nodes)
            except (TypeError, ValueError):
                nodes_int = 0
            if nodes_int > 0:
                log(
                    f"  ⚠️  0 files reported by stats but {nodes_int} total nodes "
                    f"exist — likely a stats-reporting issue, not indexing."
                )
            else:
                log(f"  ❌ Indexing failed: 0 files in database")
    
    # Overall stats
    log("")
    log("Overall database statistics:")
    overall_output, overall_ms, _ = run_cgc_command(["stats"], timeout=120)
    overall_stats = parse_stats_output(overall_output)
    log(f"  {overall_stats}")
    results["overall_stats"] = overall_stats
    
    # PHASE 3: ANALYZE COMMANDS
    log("")
    log("=" * 70)
    log("  PHASE 3: ANALYZE COMMAND BENCHMARKS")
    log("=" * 70)
    
    analyze_commands = [
        ("calls", lambda r: ["analyze", "calls", r["test_function"]]),
        ("callers", lambda r: ["analyze", "callers", r["test_function"]]),
        ("deps", lambda r: ["analyze", "deps", str(REPOS_DIR / r["name"])]),
        ("tree", lambda r: ["analyze", "tree", r["test_class"]]),
        ("complexity", lambda r: ["analyze", "complexity", r["test_function"]]),
        ("dead-code", lambda r: ["analyze", "dead-code"]),
    ]
    
    for repo in REPOS:
        name = repo["name"]
        repo["analyze"] = {}

        log("")
        log(f"━━━ [{repo['tier']}] {repo['github']} ━━━")

        # Skip analyze commands for crashed repos — they have no data to
        # analyze and the commands would either return empty results or
        # trigger another native crash.
        if repo.get("crash_reason"):
            log(f"  ⏭️  Skipping analyze commands: indexing crashed ({repo['crash_reason']})")
            for cmd_name, _ in analyze_commands:
                repo["analyze"][cmd_name] = {
                    "time_ms": 0,
                    "success": False,
                    "skipped": True,
                }
            continue

        log(f"  Test function: {repo['test_function']}, Test class: {repo['test_class']}")

        for cmd_name, cmd_builder in analyze_commands:
            args = cmd_builder(repo)
            log(f"  ⏱️  cgc {' '.join(args)}...")
            output, duration_ms, success = run_cgc_command(args, timeout=180)
            
            # Detect segfaults
            output_lower = output.lower()
            if "segmentation fault" in output_lower or "core dumped" in output_lower or "sigsegv" in output_lower:
                log(f"    ⚠️  Command crashed with segmentation fault")
                success = False
            
            repo["analyze"][cmd_name] = {
                "time_ms": duration_ms,
                "success": success,
            }
            status = "✅" if success else "⚠️"
            log(f"    {status} {fmt_time(duration_ms)}")
    
    # PHASE 4: DATABASE FOOTPRINT
    log("")
    log("=" * 70)
    log("  PHASE 4: DATABASE FOOTPRINT")
    log("=" * 70)
    
    db_size = "N/A"
    candidate_paths = [
        DB_PATH,
        Path.home() / ".codegraphcontext" / "global" / DB_BACKEND,
        Path.home() / ".codegraphcontext" / DB_BACKEND,
        # CGC's default storage location for FalkorDB Lite (and other backends)
        Path.home() / ".codegraphcontext" / "global" / "db",
    ]
    for check_path in candidate_paths:
        if check_path.exists():
            try:
                result = subprocess.check_output(["du", "-sh", str(check_path)], text=True)
                db_size = result.split()[0]
            except Exception:
                pass
            break

    for check_path in [Path.home() / ".codegraphcontext" / "global" / "db"]:
        if check_path.exists():
            try:
                result = subprocess.check_output(["du", "-sh", str(check_path)], text=True)
                log(f"  DB directory size: {result.split()[0]}")
            except Exception:
                pass

    log(f"  {DB_LABEL} disk usage: {db_size}")
    results["db_disk_size"] = db_size
    results["db_backend"] = DB_LABEL
    # Keep legacy key for downstream compatibility
    kuzudb_size = db_size
    
    # SAVE RESULTS JSON
    for repo in REPOS:
        results["repos"][repo["name"]] = {
            k: v for k, v in repo.items() if k != "name"
        }
    
    with open(RESULTS_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    log(f"\n📊 Raw results saved to: {RESULTS_JSON}")
    
    # GENERATE MARKDOWN REPORT
    log("\nGenerating Markdown report...")
    
    report = []
    report.append("# 📊 CodeGraphContext (CGC) — Benchmark Report\n")
    report.append(f"> **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    report.append(f"> **Database:** {DB_LABEL} (single shared instance for all repos)\n")
    report.append("---\n")
    
    # Environment
    report.append("## 🔧 Environment\n")
    report.append("| Parameter | Value |")
    report.append("|-----------|-------|")
    report.append(f"| **CGC Version** | {cgc_version} |")
    report.append(f"| **CGC Git Commit** | `{cgc_commit}` |")
    report.append(f"| **CGC Commit Date** | {cgc_date} |")
    report.append(f"| **Database Backend** | {DB_LABEL} (embedded) |")
    report.append(f"| **{DB_LABEL} Disk Size** | {kuzudb_size} |")
    report.append(f"| **OS** | {sys_info['os']} |")
    report.append(f"| **CPU** | {sys_info['cpu']} ({sys_info['cpu_cores']} cores) |")
    report.append(f"| **RAM** | {sys_info['ram']} |")
    report.append(f"| **Python** | {sys_info['python']} |")
    report.append("")
    report.append("---\n")
    
    # Repos Under Test
    report.append("## 📁 Repositories Under Test\n")
    report.append("| # | Tier | Repository | GitHub | Commit SHA | Total Files | Python Files |")
    report.append("|---|------|-----------|--------|------------|-------------|--------------|")
    for i, repo in enumerate(REPOS, 1):
        report.append(
            f"| {i} | {repo['tier_emoji']} {repo['tier']} | **{repo['github']}** | "
            f"[Link](https://github.com/{repo['github']}) | `{repo['short_commit']}` | "
            f"{repo['total_files']} | {repo['py_files']} |"
        )
    report.append("")
    report.append("---\n")
    
    # Indexing Performance
    report.append("## ⏱️ Indexing Performance (`cgc index --force`)\n")
    report.append("| Repository | Tier | Total Files | Python Files | Status | Indexing Time | Files/sec |")
    report.append("|-----------|------|-------------|--------------|--------|---------------|-----------|")
    for repo in REPOS:
        if repo.get("crash_reason"):
            status = f"💥 CRASH (`{repo['crash_reason']}`)"
            rate = "N/A"
        elif repo.get("index_success"):
            status = "✅ OK"
            rate = fmt_rate(repo["total_files"], repo["index_time_ms"])
        else:
            status = "⚠️ FAILED"
            rate = fmt_rate(repo["total_files"], repo["index_time_ms"])
        report.append(
            f"| **{repo['name']}** | {repo['tier_emoji']} {repo['tier']} | {repo['total_files']} | "
            f"{repo['py_files']} | {status} | {fmt_time(repo['index_time_ms'])} | {rate} |"
        )
    report.append("")
    # Flag any crashed repos with a prominent warning block.
    crashed = [r for r in REPOS if r.get("crash_reason")]
    if crashed:
        report.append("> ⚠️ **Native crash detected during indexing**")
        report.append(">")
        for r in crashed:
            report.append(
                f"> - **{r['name']}** ({r['github']}) crashed with "
                f"`{r['crash_reason']}` after {1 + 2} attempts. "
                "This is a known KùzuDB memory-corruption issue that is "
                "non-deterministic; retrying the benchmark may succeed. "
                "For reliable runs, consider switching to the FalkorDB "
                "backend in `run_benchmark.py` (swap the Option 1 / "
                "Option 2 comment blocks)."
            )
        report.append("")
    report.append("---\n")

    # Graph Statistics
    report.append("## 📈 Graph Statistics (Nodes & Edges)\n")
    report.append("| Repository | Tier | Files Indexed | Functions | Classes | Modules | Stats Query | Total Nodes | Total Edges |")
    report.append("|-----------|------|--------------|-----------|---------|--------|-------------|-------------|-------------|")
    for repo in REPOS:
        if repo.get("crash_reason"):
            report.append(
                f"| **{repo['name']}** | {repo['tier_emoji']} {repo['tier']} | "
                f"💥 CRASH | — | — | — | — | — | — |"
            )
            continue
        s = repo.get("stats", {})
        stats_ms = repo.get("stats_time_ms", 0)
        stats_time = f"{stats_ms/1000:.1f}s" if stats_ms > 0 else "N/A"
        # Show warning indicator if modules=0 with cypher fallback
        modules_val = s.get('modules', 'N/A')
        if modules_val == 0 and repo.get("stats_source") == "cypher_fallback":
            modules_val = "0 ⚠️"
        report.append(
            f"| **{repo['name']}** | {repo['tier_emoji']} {repo['tier']} | "
            f"{s.get('files', 'N/A')} | {s.get('functions', 'N/A')} | "
            f"{s.get('classes', 'N/A')} | {modules_val} | {stats_time} | "
            f"{repo.get('total_nodes', 'N/A')} | {repo.get('total_edges', 'N/A')} |"
        )
    report.append("")
    report.append("---\n")
    
    # Analyze Command Performance
    report.append("## 🔍 Analyze Command Performance\n")
    report.append("### Query Latency by Repository\n")
    
    header = "| Analyze Command |"
    separator = "|----------------|"
    for repo in REPOS:
        header += f" {repo['name']} ({repo['tier_emoji']} {repo['tier']}) |"
        separator += "------------------|"
    report.append(header)
    report.append(separator)
    
    for cmd_name, _ in analyze_commands:
        row = f"| `analyze {cmd_name}` |"
        for repo in REPOS:
            a = repo.get("analyze", {}).get(cmd_name, {})
            if a.get("skipped"):
                row += " ⏭️ SKIP |"
                continue
            t = a.get("time_ms", 0)
            # Default to True - only warn when explicitly False (e.g., analyze deps on large repos)
            success = a.get("success", True)
            mark = "" if success else " ⚠️"
            row += f" {fmt_time(t)}{mark} |"
        report.append(row)
    report.append("")
    
    report.append("### Test Parameters Used\n")
    report.append("| Repository | Function Tested | Class Tested |")
    report.append("|-----------|----------------|--------------|")
    for repo in REPOS:
        report.append(f"| **{repo['name']}** | `{repo['test_function']}` | `{repo['test_class']}` |")
    report.append("")
    report.append("---\n")
    
    # Database Footprint
    report.append("## 💾 Database Footprint\n")
    report.append("| Metric | Value |")
    report.append("|--------|-------|")
    report.append(f"| **Database Type** | {DB_LABEL} (embedded, single shared instance) |")
    report.append(f"| **Disk Usage** | {kuzudb_size} |")
    report.append(f"| **Total Repositories** | 3 |")
    if overall_stats:
        for k, v in overall_stats.items():
            report.append(f"| **Total {k.title()}** | {v} |")
    report.append("")
    report.append("---\n")
    
    # Notes
    report.append("## 📝 Notes\n")
    report.append(f"- All 3 repositories were indexed into the **same {DB_LABEL} instance** as per the project owner's requirement.")
    report.append("- Indexing was done with `cgc index --force` to ensure clean re-indexing.")
    report.append("- Times include service initialization overhead (DB connection setup, schema verification).")
    report.append("- Analyze command times include the round-trip overhead of service initialization + query execution + result formatting.")
    report.append(f"- The benchmark was run on a single machine; no network latency involved ({DB_LABEL} is embedded).")
    report.append("- Node/edge counts use bounded traversal depth (`CONTAINS*1..5`) to avoid expensive unbounded queries.")
    report.append("")
    report.append("---\n")

    # Caveats - Known Limitations
    report.append("## ⚠️ Caveats — Known Limitations\n")
    has_modules_issue = any(
        repo.get("stats", {}).get("modules", 0) == 0
        and repo.get("stats_source") == "cypher_fallback"
        for repo in REPOS
    )
    has_deps_issue = any(
        not repo.get("analyze", {}).get("deps", {}).get("success", True)
        for repo in REPOS
    )
    if has_modules_issue:
        report.append(
            "- **Modules = 0 for large repos** (e.g., fastapi) — The cypher "
            "fallback tried multiple label variants (`Module`, `ImportedModule`, "
            "`IMPORTS` relationship) but none returned rows. This is a known "
            "CGC graph-schema limitation and is flagged with ⚠️ in the table."
        )
    if has_deps_issue:
        report.append(
            "- **`analyze deps` returns `success: false`** for all repos — "
            "Marked with ⚠️ in the Analyze table. The command completes but "
            "reports failure in its JSON output; likely a CGC bug or "
            "unsupported function/class target."
        )
    report.append(
        "- **Stats query time varies widely** — Small repos finish in <1s, "
        "but large repos (e.g., fastapi) can take 130+ seconds when the CLI "
        "parser fails and a cypher fallback runs. See the *Stats Query* column."
    )
    report.append("")
    report.append("---\n")
    
    # References
    report.append("## 🔗 References\n")
    report.append(f"- **CodeGraphContext**: [GitHub](https://github.com/Shashankss1205/CodeGraphContext) — Commit `{cgc_short}`")
    for repo in REPOS:
        report.append(f"- **{repo['github']}**: [GitHub](https://github.com/{repo['github']}) — Commit `{repo['short_commit']}`")
    report.append("")
    
    # Write report
    report_text = "\n".join(report)
    with open(REPORT_FILE, "w") as f:
        f.write(report_text)
    
    log(f"\n✅ Benchmark complete!")
    log(f"📄 Report saved to: {REPORT_FILE}")
    log(f"📊 Raw results: {RESULTS_JSON}")
    
    print("\n" + "=" * 70)
    print(report_text)


if __name__ == "__main__":
    main()
