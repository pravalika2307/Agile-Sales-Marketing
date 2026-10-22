#!/usr/bin/env bash

# ==============================================================================
# Helper script to immediately kill / close backend and frontend development servers
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/dev.sh" stop
