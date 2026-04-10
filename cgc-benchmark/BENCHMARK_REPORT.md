# 📊 CodeGraphContext (CGC) — Benchmark Report

> **Generated:** 2026-04-10 15:46:57 
> **Database:** FalkorDB (single shared instance for all repos)

---

## 🔧 Environment

| Parameter | Value |
|-----------|-------|
| **CGC Version** | CodeGraphContext 0.3.1 |
| **CGC Git Commit** | `649f045fea5c2e7a22e3eb220d984135623f2ba8` |
| **CGC Commit Date** | 2026-04-09 20:11:54 +0530 |
| **Database Backend** | FalkorDB (embedded) |
| **FalkorDB Disk Size** | 4.9M |
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
| **click** | 🟢 Small | 148 | 63 | 33.68s | 4.4 |
| **flask** | 🟡 Medium | 237 | 83 | 25.00s | 9.5 |
| **fastapi** | 🔴 Large | 2986 | 1121 | 80.14s | 37.3 |

---

## 📈 Graph Statistics (Nodes & Edges)

| Repository | Tier | Files Indexed | Functions | Classes | Imported Modules | Total Nodes | Total Edges |
|-----------|------|--------------|-----------|---------|------------------|-------------|-------------|
| **click** | 🟢 Small | 63 | 2594 | 142 | 241 | 4498 | 29613 |
| **flask** | 🟡 Medium | 83 | 3047 | 161 | 260 | 4181 | 14679 |
| **fastapi** | 🔴 Large | 1125 | 5651 | 689 | 384 | 14506 | 28773 |

---

## 🔍 Analyze Command Performance

### Query Latency by Repository

| Analyze Command | click (🟢 Small) | flask (🟡 Medium) | fastapi (🔴 Large) |
|----------------|------------------|------------------|------------------|
| `analyze calls` | 893ms | 972ms | 904ms |
| `analyze callers` | 904ms | 926ms | 929ms |
| `analyze deps` | 898ms | 910ms | 902ms |
| `analyze tree` | 913ms | 923ms | 903ms |
| `analyze complexity` | 914ms | 895ms | 901ms |
| `analyze dead-code` | 1.01s | 1.01s | 999ms |

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
| **Database Type** | FalkorDB (embedded, single shared instance) |
| **Disk Usage** | 4.9M |
| **Total Repositories** | 3 |
| **Total Files** | 1271 |
| **Total Functions** | 7527 |
| **Total Classes** | 992 |
| **Total Modules** | 789 |

---

## 📝 Notes

- All 3 repositories were indexed into the **same FalkorDB instance** as per the project owner's requirement.
- Indexing was done with `cgc index --force` to ensure clean re-indexing.
- Times include service initialization overhead (DB connection setup, schema verification).
- Analyze command times include the round-trip overhead of service initialization + query execution + result formatting.
- The benchmark was run on a single machine; no network latency involved (FalkorDB is embedded).
- Node/edge counts use bounded traversal depth (`CONTAINS*1..5`) to avoid expensive unbounded queries.

---

## 🔗 References

- **CodeGraphContext**: [GitHub](https://github.com/Shashankss1205/CodeGraphContext) — Commit `649f045fea5c`
- **pallets/click**: [GitHub](https://github.com/pallets/click) — Commit `04ef3a6f473d`
- **pallets/flask**: [GitHub](https://github.com/pallets/flask) — Commit `2ac89889f4cc`
- **tiangolo/fastapi**: [GitHub](https://github.com/tiangolo/fastapi) — Commit `eba8942c81db`
