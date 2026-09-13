#!/bin/sh
# Keep this file LF-terminated; Docker executes it directly.
set -eu
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
