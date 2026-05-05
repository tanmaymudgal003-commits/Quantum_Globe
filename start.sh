#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
# QuantumGlobe — Optimized Monolithic Startup (Submission Build)
# ════════════════════════════════════════════════════════════════════
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

banner() {
  echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║   ⚛  QUANTUM GLOBE  ·  QCC × QML Weather AI       ║${NC}"
  echo -e "${CYAN}║   AMOLED Edition + Gemini AI + OSM Free Tiles     ║${NC}"
  echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"
}

check_python() {
  if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[✗] Python 3 not found. Install Python 3.10+${NC}"
    exit 1
  fi
  PY_VER=$(python3 --version)
  echo -e "${GREEN}[✓] ${PY_VER} found.${NC}"
}

setup_venv() {
  if [ ! -d "venv" ]; then
    echo -e "${CYAN}[*] Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}[✓] Virtual environment created.${NC}"
  fi
  source venv/bin/activate
}

install_deps() {
  # Check if core modules are already functional to skip slow installs[cite: 9, 14]
  if python3 -c "import flask, google.generativeai, qiskit" &>/dev/null; then
    echo -e "${GREEN}[✓] Dependencies already satisfied. Skipping install.${NC}"
  else
    echo -e "${CYAN}[*] Dependencies missing or incomplete. Installing now...${NC}"
    # Use --no-cache-dir to prevent the "deserialization failed" loop
    pip install --no-cache-dir -q -r requirements.txt
    echo -e "${GREEN}[✓] Dependencies installed successfully.${NC}"
  fi
}

start_backend() {
  if [ ! -f "config.json" ]; then
    echo -e "${RED}[✗] config.json not found! Please create it from config_2.json.${NC}"
    exit 1
  fi

  # Extract port from config or default to 8080[cite: 11]
  PORT=$(python3 -c "import json; d=json.load(open('config.json')); print(d.get('SERVER_PORT',8080))" 2>/dev/null || echo 8080)

  echo -e "${CYAN}[*] Starting QuantumGlobe Backend...${NC}"
  # Run the backend in the background
  python3 quantum_backend.py &
  BACKEND_PID=$!
  
  # Brief sleep to allow Flask to bind to the port[cite: 14]
  sleep 2

  URL="http://localhost:${PORT}"
  echo -e "${GREEN}[✓] System online. Opening ${URL}${NC}"

  # Cross-platform browser opener[cite: 14]
  if command -v xdg-open &>/dev/null; then
    xdg-open "$URL" 2>/dev/null &
  elif command -v open &>/dev/null; then
    open "$URL" 2>/dev/null &
  fi

  # Wait for the backend process so the script doesn't close immediately[cite: 14]
  wait $BACKEND_PID
}

# --- Execution ---
banner
check_python
setup_venv
install_deps
start_backend