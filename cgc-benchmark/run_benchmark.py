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
CGC_REPO_DIR = SCRIPT_DIR / "CodeGraphContext"
KUZUDB_PATH = SCRIPT_DIR / "shared_kuzudb"
REPORT_FILE = SCRIPT_DIR / "BENCHMARK_REPORT.md"
RESULTS_JSON = SCRIPT_DIR / "benchmark_results.json"

# Force KùzuDB
os.environ["DEFAULT_DATABASE"] = "kuzudb"
os.environ["KUZUDB_PATH"] = str(KUZUDB_PATH)
os.environ["CGC_RUNTIME_DB_TYPE"] = "kuzudb"

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
    """Run a cgc command and return (output, duration_ms, success)."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["cgc"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
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
    """Parse cgc stats output to extract counts."""
    stats = {"files": 0, "functions": 0, "classes": 0, "modules": 0}
    for line in output.splitlines():
        if "Files" in line and "│" in line:
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) >= 2 and parts[0] == "Files":
                try:
                    stats["files"] = int(parts[1])
                except ValueError:
                    pass
        elif "Functions" in line and "│" in line:
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) >= 2 and parts[0] == "Functions":
                try:
                    stats["functions"] = int(parts[1])
                except ValueError:
                    pass
        elif "Classes" in line and "│" in line:
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) >= 2 and parts[0] == "Classes":
                try:
                    stats["classes"] = int(parts[1])
                except ValueError:
                    pass
        elif "Imported Modules" in line and "│" in line:
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) >= 2 and parts[0] == "Imported Modules":
                try:
                    stats["modules"] = int(parts[1])
                except ValueError:
                    pass
        elif "Modules" in line and "│" in line and "Imported" not in line:
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) >= 2 and parts[0] == "Modules":
                try:
                    stats["modules"] = int(parts[1])
                except ValueError:
                    pass
    return stats


def get_graph_node_edge_counts(repo_path):
    """Get total nodes and edges for a repo using cgc cypher."""
    abs_path = str(Path(repo_path).resolve())
    
    # Total nodes
    nodes_output, nodes_ms, _ = run_cgc_command([
        "cypher", 
        f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(n) RETURN count(n) as total_nodes"
    ], timeout=120)
    
    nodes = "N/A"
    for line in nodes_output.splitlines():
        if "total_nodes" in line:
            import re
            nums = re.findall(r'\d+', line)
            if nums:
                nodes = nums[-1]
                break
    
    # Total edges
    edges_output, edges_ms, _ = run_cgc_command([
        "cypher",
        f"MATCH (r:Repository {{path: '{abs_path}'}})-[:CONTAINS*1..5]->(n)-[rel]->(m) RETURN count(rel) as total_edges"
    ], timeout=120)
    
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
    
    # System Info
    sys_info = get_system_info()
    cgc_commit, cgc_date, cgc_short = get_git_info(CGC_REPO_DIR)
    
    cgc_ver_output, _, _ = run_cgc_command(["version"])
    cgc_version = cgc_ver_output.strip()
    
    log(f"CGC Version: {cgc_version}")
    log(f"CGC Commit: {cgc_short} ({cgc_date})")
    log(f"Database: KùzuDB (shared)")
    log(f"System: {sys_info['os']}")
    log(f"CPU: {sys_info['cpu']} ({sys_info['cpu_cores']} cores)")
    log(f"RAM: {sys_info['ram']}")
    log(f"Python: {sys_info['python']}")
    
    # Clean Previous Data
    log("")
    log("🧹 Cleaning previous benchmark data...")
    if KUZUDB_PATH.exists():
        shutil.rmtree(KUZUDB_PATH)
    
    # Also clean any default kuzudb location
    default_kuzu = Path.home() / ".codegraphcontext" / "global" / "kuzudb"
    if default_kuzu.exists():
        shutil.rmtree(default_kuzu)
    default_kuzu2 = Path.home() / ".codegraphcontext" / "global" / "db" / "kuzudb"
    if default_kuzu2.exists():
        os.remove(default_kuzu2) if default_kuzu2.is_file() else shutil.rmtree(default_kuzu2)
    
    # Results Storage
    results = {
        "metadata": {
            "benchmark_date": datetime.now(timezone.utc).isoformat(),
            "cgc_version": cgc_version,
            "cgc_commit": cgc_commit,
            "cgc_commit_date": cgc_date,
            "database": "KùzuDB (shared single instance)",
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
        
        log(f"  ⏱️  Running cgc index --force...")
        output, duration_ms, success = run_cgc_command(["index", abs_path, "--force"], timeout=600)
        repo["index_time_ms"] = duration_ms
        repo["index_success"] = success
        
        log(f"  {'✅' if success else '❌'} Indexing completed in {fmt_time(duration_ms)}")
        
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
        
        log(f"  Running cgc stats...")
        stats_output, stats_ms, _ = run_cgc_command(["stats", abs_path], timeout=300)
        stats = parse_stats_output(stats_output)
        repo["stats"] = stats
        repo["stats_time_ms"] = stats_ms
        
        log(f"  Stats query: {fmt_time(stats_ms)}")
        log(f"  Files: {stats.get('files', 'N/A')}, Functions: {stats.get('functions', 'N/A')}, Classes: {stats.get('classes', 'N/A')}, Modules: {stats.get('modules', 'N/A')}")
        
        log(f"  Querying total nodes and edges (bounded depth)...")
        nodes, edges, nodes_ms, edges_ms = get_graph_node_edge_counts(repo_path)
        repo["total_nodes"] = nodes
        repo["total_edges"] = edges
        
        log(f"  Nodes: {nodes} ({fmt_time(nodes_ms)}), Edges: {edges} ({fmt_time(edges_ms)})")
    
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
        log(f"  Test function: {repo['test_function']}, Test class: {repo['test_class']}")
        
        for cmd_name, cmd_builder in analyze_commands:
            args = cmd_builder(repo)
            log(f"  ⏱️  cgc {' '.join(args)}...")
            output, duration_ms, success = run_cgc_command(args, timeout=180)
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
    
    kuzudb_size = "N/A"
    for check_path in [KUZUDB_PATH, Path.home() / ".codegraphcontext" / "global" / "kuzudb"]:
        if check_path.exists():
            try:
                result = subprocess.check_output(["du", "-sh", str(check_path)], text=True)
                kuzudb_size = result.split()[0]
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
    
    log(f"  KùzuDB disk usage: {kuzudb_size}")
    results["kuzudb_disk_size"] = kuzudb_size
    
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
    report.append(f"> **Database:** KùzuDB (single shared instance for all repos)\n")
    report.append("---\n")
    
    # Environment
    report.append("## 🔧 Environment\n")
    report.append("| Parameter | Value |")
    report.append("|-----------|-------|")
    report.append(f"| **CGC Version** | {cgc_version} |")
    report.append(f"| **CGC Git Commit** | `{cgc_commit}` |")
    report.append(f"| **CGC Commit Date** | {cgc_date} |")
    report.append(f"| **Database Backend** | KùzuDB (embedded) |")
    report.append(f"| **KùzuDB Disk Size** | {kuzudb_size} |")
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
    report.append("| Repository | Tier | Total Files | Python Files | Indexing Time | Files/sec |")
    report.append("|-----------|------|-------------|--------------|---------------|-----------|")
    for repo in REPOS:
        rate = fmt_rate(repo["total_files"], repo["index_time_ms"])
        report.append(
            f"| **{repo['name']}** | {repo['tier_emoji']} {repo['tier']} | {repo['total_files']} | "
            f"{repo['py_files']} | {fmt_time(repo['index_time_ms'])} | {rate} |"
        )
    report.append("")
    report.append("---\n")
    
    # Graph Statistics
    report.append("## 📈 Graph Statistics (Nodes & Edges)\n")
    report.append("| Repository | Tier | Files Indexed | Functions | Classes | Imported Modules | Total Nodes | Total Edges |")
    report.append("|-----------|------|--------------|-----------|---------|------------------|-------------|-------------|")
    for repo in REPOS:
        s = repo.get("stats", {})
        report.append(
            f"| **{repo['name']}** | {repo['tier_emoji']} {repo['tier']} | "
            f"{s.get('files', 'N/A')} | {s.get('functions', 'N/A')} | "
            f"{s.get('classes', 'N/A')} | {s.get('modules', 'N/A')} | "
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
            t = a.get("time_ms", 0)
            success = a.get("success", False)
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
    report.append(f"| **Database Type** | KùzuDB (embedded, single shared instance) |")
    report.append(f"| **Disk Usage** | {kuzudb_size} |")
    report.append(f"| **Total Repositories** | 3 |")
    if overall_stats:
        for k, v in overall_stats.items():
            report.append(f"| **Total {k.title()}** | {v} |")
    report.append("")
    report.append("---\n")
    
    # Notes
    report.append("## 📝 Notes\n")
    report.append("- All 3 repositories were indexed into the **same KùzuDB instance** as per the project owner's requirement.")
    report.append("- Indexing was done with `cgc index --force` to ensure clean re-indexing.")
    report.append("- Times include service initialization overhead (DB connection setup, schema verification).")
    report.append("- Analyze command times include the round-trip overhead of service initialization + query execution + result formatting.")
    report.append("- The benchmark was run on a single machine; no network latency involved (KùzuDB is embedded).")
    report.append("- Node/edge counts use bounded traversal depth (`CONTAINS*1..5`) to avoid expensive unbounded queries.")
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
