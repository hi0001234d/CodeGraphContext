# 📊 CodeGraphContext (CGC) — Benchmark Report

> **Generated:** 2026-04-09 20:04:48 
> **Database:** KùzuDB (single shared instance for all repos)

---

## 🔧 Environment

| Parameter | Value |
|-----------|-------|
| **CGC Version** | Traceback (most recent call last):
  File "/home/pc1/.local/bin/cgc", line 5, in <module>
    from codegraphcontext.cli.main import app
ModuleNotFoundError: No module named 'codegraphcontext' |
| **CGC Git Commit** | `unknown` |
| **CGC Commit Date** | unknown |
| **Database Backend** | KùzuDB (embedded) |
| **KùzuDB Disk Size** | N/A |
| **OS** | Linux-6.17.0-20-generic-x86_64-with-glibc2.39 |
| **CPU** | Intel(R) Core(TM) i5-9600K CPU @ 3.70GHz (6 cores) |
| **RAM** | 31Gi |
| **Python** | 3.12.3 |

---

## 📁 Repositories Under Test

| # | Tier | Repository | GitHub | Commit SHA | Total Files | Python Files |
|---|------|-----------|--------|------------|-------------|--------------|
| 1 | 🟢 Small | **pallets/click** | [Link](https://github.com/pallets/click) | `04ef3a6f473d` | 148 | 63 |
| 2 | 🟡 Medium | **pallets/flask** | [Link](https://github.com/pallets/flask) | `2ac89889f4cc` | 237 | 83 |
| 3 | 🔴 Large | **tiangolo/fastapi** | [Link](https://github.com/tiangolo/fastapi) | `eba8942c81db` | 2986 | 1121 |

---

## ⏱️ Indexing Performance (`cgc index --force`)

| Repository | Tier | Total Files | Python Files | Indexing Time | Files/sec |
|-----------|------|-------------|--------------|---------------|-----------|
| **click** | 🟢 Small | 148 | 63 | 90ms | 1644.4 |
| **flask** | 🟡 Medium | 237 | 83 | 97ms | 2443.3 |
| **fastapi** | 🔴 Large | 2986 | 1121 | 92ms | 32456.5 |

---

## 📈 Graph Statistics (Nodes & Edges)

| Repository | Tier | Files Indexed | Functions | Classes | Imported Modules | Total Nodes | Total Edges |
|-----------|------|--------------|-----------|---------|------------------|-------------|-------------|
| **click** | 🟢 Small | 0 | 0 | 0 | 0 | N/A | N/A |
| **flask** | 🟡 Medium | 0 | 0 | 0 | 0 | N/A | N/A |
| **fastapi** | 🔴 Large | 0 | 0 | 0 | 0 | N/A | N/A |

---

## 🔍 Analyze Command Performance

### Query Latency by Repository

| Analyze Command | click (🟢 Small) | flask (🟡 Medium) | fastapi (🔴 Large) |
|----------------|------------------|------------------|------------------|
| `analyze calls` | 89ms ⚠️ | 88ms ⚠️ | 92ms ⚠️ |
| `analyze callers` | 92ms ⚠️ | 89ms ⚠️ | 89ms ⚠️ |
| `analyze deps` | 88ms ⚠️ | 89ms ⚠️ | 92ms ⚠️ |
| `analyze tree` | 93ms ⚠️ | 89ms ⚠️ | 91ms ⚠️ |
| `analyze complexity` | 89ms ⚠️ | 90ms ⚠️ | 91ms ⚠️ |
| `analyze dead-code` | 96ms ⚠️ | 91ms ⚠️ | 89ms ⚠️ |

### Test Parameters Used

| Repository | Function Tested | Class Tested |
|-----------|----------------|--------------|
| **click** | `make_str` | `CliRunner` |
| **flask** | `make_response` | `Flask` |
| **fastapi** | `get` | `FastAPI` |

---

## 💾 Database Footprint

| Metric | Value |
|--------|-------|
| **Database Type** | KùzuDB (embedded, single shared instance) |
| **Disk Usage** | N/A |
| **Total Repositories** | 3 |
| **Total Files** | 0 |
| **Total Functions** | 0 |
| **Total Classes** | 0 |
| **Total Modules** | 0 |

---

## 📝 Notes

- All 3 repositories were indexed into the **same KùzuDB instance** as per the project owner's requirement.
- Indexing was done with `cgc index --force` to ensure clean re-indexing.
- Times include service initialization overhead (DB connection setup, schema verification).
- Analyze command times include the round-trip overhead of service initialization + query execution + result formatting.
- The benchmark was run on a single machine; no network latency involved (KùzuDB is embedded).
- Node/edge counts use bounded traversal depth (`CONTAINS*1..5`) to avoid expensive unbounded queries.

---

## 🔗 References

- **CodeGraphContext**: [GitHub](https://github.com/Shashankss1205/CodeGraphContext) — Commit `unknown`
- **pallets/click**: [GitHub](https://github.com/pallets/click) — Commit `04ef3a6f473d`
- **pallets/flask**: [GitHub](https://github.com/pallets/flask) — Commit `2ac89889f4cc`
- **tiangolo/fastapi**: [GitHub](https://github.com/tiangolo/fastapi) — Commit `eba8942c81db`
