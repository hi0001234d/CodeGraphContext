# 📊 CodeGraphContext (CGC) — Benchmark Report

> **Generated:** 2026-04-12 10:42:38 
> **Database:** KùzuDB (single shared instance for all repos)

---

## 🔧 Environment

| Parameter | Value |
|-----------|-------|
| **CGC Version** | 0.4.2 |
| **CGC Git Commit** | `60c29d4ed960543723007ada6be05988498df8ee` |
| **CGC Commit Date** | 2026-04-11 20:16:01 +0530 |
| **Database Backend** | KùzuDB (embedded) |
| **KùzuDB Disk Size** | 174M |
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

| Repository | Tier | Total Files | Python Files | Status | Indexing Time | Files/sec |
|-----------|------|-------------|--------------|--------|---------------|-----------|
| **click** | 🟢 Small | 148 | 63 | ✅ OK | 8.81s | 16.8 |
| **flask** | 🟡 Medium | 237 | 83 | ✅ OK | 10.49s | 22.6 |
| **fastapi** | 🔴 Large | 2986 | 1121 | ✅ OK | 91.70s | 32.6 |

---

## 📈 Graph Statistics (Nodes & Edges)

| Repository | Tier | Files Indexed | Functions | Classes | Modules | Stats Query | Total Nodes | Total Edges |
|-----------|------|--------------|-----------|---------|--------|-------------|-------------|-------------|
| **click** | 🟢 Small | 63 | 2710 | 142 | 241 | 0.9s | 4535 | 13189 |
| **flask** | 🟡 Medium | 83 | 3047 | 161 | 260 | 0.9s | 4331 | 10701 |
| **fastapi** | 🔴 Large | 1125 | 4534 | 688 | 384 | 134.5s | 14667 | 25721 |

---

## 🔍 Analyze Command Performance

### Query Latency by Repository

| Analyze Command | click (🟢 Small) | flask (🟡 Medium) | fastapi (🔴 Large) |
|----------------|------------------|------------------|------------------|
| `analyze calls` | 786ms | 791ms | 789ms |
| `analyze callers` | 791ms | 825ms | 791ms |
| `analyze deps` | 1.05s ⚠️ | 1.05s ⚠️ | 1.03s ⚠️ |
| `analyze tree` | 825ms | 800ms | 818ms |
| `analyze complexity` | 778ms | 810ms | 771ms |
| `analyze dead-code` | 843ms | 869ms | 853ms |

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
| **Disk Usage** | 174M |
| **Total Repositories** | 3 |
| **Total Files** | 1271 |
| **Total Functions** | 7527 |
| **Total Classes** | 992 |
| **Total Modules** | 789 |

---

## 📝 Notes

- All 3 repositories were indexed into the **same KùzuDB instance** as per the project owner's requirement.
- Indexing was done with `cgc index --force` to ensure clean re-indexing.
- Times include service initialization overhead (DB connection setup, schema verification).
- Analyze command times include the round-trip overhead of service initialization + query execution + result formatting.
- The benchmark was run on a single machine; no network latency involved (KùzuDB is embedded).
- Node/edge counts use bounded traversal depth (`CONTAINS*1..5`) to avoid expensive unbounded queries.

---

## ⚠️ Caveats — Known Limitations

- **`analyze deps` returns `success: false`** for all repos — Marked with ⚠️ in the Analyze table. The command completes but reports failure in its JSON output; likely a CGC bug or unsupported function/class target.
- **Stats query time varies widely** — Small repos finish in <1s, but large repos (e.g., fastapi) can take 130+ seconds when the CLI parser fails and a cypher fallback runs. See the *Stats Query* column.

---

## 🔗 References

- **CodeGraphContext**: [GitHub](https://github.com/Shashankss1205/CodeGraphContext) — Commit `60c29d4ed960`
- **pallets/click**: [GitHub](https://github.com/pallets/click) — Commit `04ef3a6f473d`
- **pallets/flask**: [GitHub](https://github.com/pallets/flask) — Commit `2ac89889f4cc`
- **tiangolo/fastapi**: [GitHub](https://github.com/tiangolo/fastapi) — Commit `eba8942c81db`
