#!/usr/bin/env bash

# ==============================================================================
# Agile Sales & Marketing - Unified Development Runner & Process Controller
# ==============================================================================
# Usage:
#   ./dev.sh         (or ./dev.sh start)  -> Runs both Backend & Frontend in a single window
#   ./dev.sh stop    (or ./dev.sh kill)   -> Stops and kills running servers and frees ports
#   ./dev.sh restart                      -> Restarts both servers
#   ./dev.sh status                       -> Displays current running status & ports
# ==============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
PID_DIR="$PROJECT_ROOT/.run"
PID_FILE="$PID_DIR/dev.pids"

BACKEND_PORT=8000
FRONTEND_PORT=3000

# ANSI color codes for single-window multi-service streaming
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_BLUE="\033[1;34m"
C_CYAN="\033[1;36m"
C_GREEN="\033[1;32m"
C_YELLOW="\033[1;33m"
C_RED="\033[1;31m"
C_DIM="\033[2m"

log_info() {
    echo -e "${C_CYAN}ℹ [DEV]${C_RESET} $1"
}

log_success() {
    echo -e "${C_GREEN}✓ [DEV]${C_RESET} $1"
}

log_warn() {
    echo -e "${C_YELLOW}⚠ [DEV]${C_RESET} $1"
}

log_error() {
    echo -e "${C_RED}✗ [DEV]${C_RESET} $1"
}

# Prefix streams with service tags
prefix_stream() {
    local color="$1"
    local tag="$2"
    while IFS= read -r line || [ -n "$line" ]; do
        echo -e "${color}[${tag}]${C_RESET} $line"
    done
}

# Kill processes listening on specified ports
kill_port() {
    local port="$1"
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        for pid in $pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 0.5
        # Force kill if still holding port
        local remaining
        remaining=$(lsof -ti :"$port" 2>/dev/null || true)
        if [ -n "$remaining" ]; then
            for rpid in $remaining; do
                kill -9 "$rpid" 2>/dev/null || true
            done
        fi
    fi
}

# Stop all background instances & clean ports
stop_servers() {
    echo -e "\n${C_BOLD}${C_YELLOW}Stopping Agile Sales & Marketing servers...${C_RESET}"
    
    # Kill tracked PIDs if pidfile exists
    if [ -f "$PID_FILE" ]; then
        while IFS= read -r pid; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi

    # Ensure ports 8000 and 3000 are freed
    kill_port "$BACKEND_PORT"
    kill_port "$FRONTEND_PORT"

    log_success "Backend (port $BACKEND_PORT) and Frontend (port $FRONTEND_PORT) stopped."
}

# Check service status
status_servers() {
    echo -e "${C_BOLD}=== Service Status ===${C_RESET}"
    
    local be_pid
    be_pid=$(lsof -ti :"$BACKEND_PORT" 2>/dev/null || true)
    if [ -n "$be_pid" ]; then
        echo -e "  Backend  (Port ${BACKEND_PORT}):  ${C_GREEN}● RUNNING${C_RESET} (PID: ${be_pid})"
    else
        echo -e "  Backend  (Port ${BACKEND_PORT}):  ${C_DIM}○ STOPPED${C_RESET}"
    fi

    local fe_pid
    fe_pid=$(lsof -ti :"$FRONTEND_PORT" 2>/dev/null || true)
    if [ -n "$fe_pid" ]; then
        echo -e "  Frontend (Port ${FRONTEND_PORT}):  ${C_GREEN}● RUNNING${C_RESET} (PID: ${fe_pid})"
    else
        echo -e "  Frontend (Port ${FRONTEND_PORT}):  ${C_DIM}○ STOPPED${C_RESET}"
    fi
}

# Start both servers in single window with unified log stream
start_servers() {
    mkdir -p "$PID_DIR"

    # Check and clean ports before starting
    if lsof -ti :"$BACKEND_PORT" >/dev/null 2>&1 || lsof -ti :"$FRONTEND_PORT" >/dev/null 2>&1; then
        log_warn "Existing processes detected on ports. Cleaning before launch..."
        stop_servers
    fi

    # Locate backend virtualenv
    local UVICORN_CMD=""
    if [ -f "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
        UVICORN_CMD="$BACKEND_DIR/.venv/bin/uvicorn"
    elif command -v uvicorn >/dev/null 2>&1; then
        UVICORN_CMD="uvicorn"
    elif [ -f "$BACKEND_DIR/.venv/bin/python" ]; then
        UVICORN_CMD="$BACKEND_DIR/.venv/bin/python -m uvicorn"
    else
        log_error "Python virtual environment not found in backend/.venv. Please setup backend venv first."
        exit 1
    fi

    # Verify frontend npm
    if ! command -v npm >/dev/null 2>&1; then
        log_error "npm is not installed or not in PATH."
        exit 1
    fi

    echo -e "${C_BOLD}${C_CYAN}======================================================${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}  Agile Sales & Marketing - Development Servers       ${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}======================================================${C_RESET}"
    echo -e "  ${C_BLUE}Backend:${C_RESET}  http://localhost:${BACKEND_PORT} (Docs: http://localhost:${BACKEND_PORT}/docs)"
    echo -e "  ${C_GREEN}Frontend:${C_RESET} http://localhost:${FRONTEND_PORT}"
    echo -e "  ${C_YELLOW}Press Ctrl+C at any time to shut down both servers.${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}======================================================${C_RESET}\n"

    # Cleanup trap on exit / Ctrl+C
    trap 'echo ""; log_info "Received interrupt signal. Shutting down..."; stop_servers; exit 0' INT TERM EXIT

    # Launch Backend in subshell with prefixing
    (
        cd "$BACKEND_DIR"
        $UVICORN_CMD app.main:app --reload --port "$BACKEND_PORT" 2>&1 | prefix_stream "$C_BLUE" "backend"
    ) &
    BACKEND_PID=$!

    # Launch Frontend in subshell with prefixing
    (
        cd "$FRONTEND_DIR"
        npm run dev -- -p "$FRONTEND_PORT" 2>&1 | prefix_stream "$C_GREEN" "frontend"
    ) &
    FRONTEND_PID=$!

    # Store PIDs
    echo "$BACKEND_PID" > "$PID_FILE"
    echo "$FRONTEND_PID" >> "$PID_FILE"

    # Wait for background jobs
    wait
}

# Main command dispatcher
case "${1:-start}" in
    start|run)
        start_servers
        ;;
    stop|kill|close)
        stop_servers
        ;;
    restart)
        stop_servers
        sleep 1
        start_servers
        ;;
    status)
        status_servers
        ;;
    *)
        echo "Usage: $0 {start|stop|kill|close|restart|status}"
        exit 1
        ;;
esac
