# Contributing

1. Create a virtual environment with Python 3.11+.
2. Install development dependencies: `pip install -e ".[dev]"`.
3. Run `ruff check .` and `pytest` before opening a pull request.
4. Keep vehicle integrations focused on read-only telemetry.
5. Never include real credentials, VINs, trip databases, or location history in commits, issues, or test fixtures.

See `SECURITY.md` for the repository's sensitive-data policy.
