# GenApp Analysis Workspace

This folder reorganizes the GenApp application by file type/purpose to make
legacy-modernization analysis easier.

## Categories

- `COBOL/` — COBOL source programs
- `COPYBOOKS/` — COBOL copybooks/data structures
- `JCL/` — JCL jobs and build/deployment definitions
- `BMS/` — BMS/3270 map definitions
- `SQL/` — SQL source, if present
- `REXX/` — REXX scripts
- `EVENT_BINDINGS/` — CICS event bindings
- `DATA/` — sample/data files
- `WORKLOAD_SIMULATOR/` — workload simulation assets
- `DOCUMENTATION/` — project documentation
- `SHELL/` — shell scripts
- `OTHER/` — files that do not fit the above categories
- `FILE_MANIFEST.csv` — original-to-new-path mapping

The `original/` directory preserves the downloaded repository exactly as it
was packaged, so no source information is lost.
