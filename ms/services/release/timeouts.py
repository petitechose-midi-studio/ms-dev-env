from __future__ import annotations

# GH / API operations
GH_TIMEOUT_SECONDS = 60.0
GH_CLONE_TIMEOUT_SECONDS = 15 * 60.0
GH_WATCH_TIMEOUT_SECONDS = 4 * 60 * 60.0

# Local git operations (status, rev-parse, checkout, add, commit)
GIT_TIMEOUT_SECONDS = 30.0

# Network-bound git operations (pull, push)
GIT_NETWORK_TIMEOUT_SECONDS = 3 * 60.0

# Idempotent GH read retry policy
GH_READ_RETRY_ATTEMPTS = 3
GH_READ_RETRY_DELAY_SECONDS = 1.0
