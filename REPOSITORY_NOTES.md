# Repository Cleanup Notes

This GitHub-ready package was prepared from the latest project workspace.

Cleanup performed:
- Removed `.ipynb_checkpoints`.
- Removed `__pycache__`, `.pyc`, and `.pyo` files.
- Removed local `.env` / Streamlit secrets files if present.
- Replaced the previously identified hard-coded development password string with
  `CHANGE_ME_LOCAL_ONLY`.
- Added `.gitignore`.
- Added `.env.example`.
- Added `SECURITY.md`.
- Added a top-level README for recruiters and GitHub visitors.

Before publishing:
1. Review `CHANGE_ME_LOCAL_ONLY` occurrences and ensure your code reads
   `PGPASSWORD` from the environment.
2. Run the complete automated test suite.
3. Rotate any credential that may previously have been exposed.
4. Review sample data to confirm it contains no sensitive information.
