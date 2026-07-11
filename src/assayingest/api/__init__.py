"""The FastAPI transport adapter -- translates HTTP <-> the Phase 1-3 domain
via `service.py` (04-01). No mapping/validation/signature/gate logic lives
here; every route is a thin adapter, exactly as `cli.py` is for the CLI.
"""
