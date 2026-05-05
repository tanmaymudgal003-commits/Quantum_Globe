
set -euo pipefail

BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

banner() {
  echo -e "${CYAN}"
  echo "╔═══════════════════════════════════════════════════╗"
  echo "║   ⚛  QUANTUM GLOBE  ·  QCC × QML Weather AI      ║"
  echo "║   Map Tiles · Aerial View · QCC.SO · OpenWeather  ║"
  echo "╚═══════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

check_python() {
  if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[✗] Python 3 not found. Install Python 3.10+${NC}"; exit 1
  fi
  PY=$(python3 --version 2>&1)
  echo -e "${GREEN}[✓] ${PY}${NC}"
}

check_config() {
  if [ ! -f "config.json" ]; then
    echo -e "${RED}[✗] config.json not found. Run from the quantum_globe directory.${NC}"; exit 1
  fi
  echo -e "${GREEN}[✓] config.json found${NC}"

  if grep -q '""' config.json; then
    echo -e "${YELLOW}[!] Some API keys may not be set in config.json${NC}"
  fi
}

setup_venv() {
  echo -e "${CYAN}[*] Setting up virtual environment...${NC}"
  if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}[✓] Virtual environment created${NC}"
  fi
  source venv/bin/activate
  echo -e "${GREEN}[✓] Virtual environment activated${NC}"
}

install_deps() {
  echo -e "${CYAN}[*] Installing Python dependencies...${NC}"
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
  echo -e "${GREEN}[✓] Dependencies installed${NC}"
}

start_backend() {
  PORT=$(python3 -c "import json; d=json.load(open('config.json')); print(d.get('SERVER_PORT',8080))" 2>/dev/null || echo 8080)
  MODE=${1:-"dev"}

  if [ "$MODE" = "--prod" ]; then
    echo -e "${CYAN}[*] Starting backend in PRODUCTION mode (gunicorn)...${NC}"
    gunicorn -w 4 -b "0.0.0.0:${PORT}" --timeout 120 "quantum_backend:app" &
  else
    echo -e "${CYAN}[*] Starting backend in DEVELOPMENT mode (Flask)...${NC}"
    python3 quantum_backend.py &
  fi

  BACKEND_PID=$!
  echo $BACKEND_PID > .backend.pid
  
  echo -e "${CYAN}[*] Waiting for backend to be ready...${NC}"
  for i in {1..10}; do
    if curl -s "http://localhost:${PORT}/api/health" > /dev/null; then
      echo -e "${GREEN}[✓] Backend ready on port ${PORT}${NC}"
      break
    fi
    sleep 1
    if [ $i -eq 10 ]; then
      echo -e "${RED}[✗] Backend failed to start or respond to health check.${NC}"
    fi
  done
}

open_browser() {
  if [[ " ${@:-} " =~ " --no-browser " ]]; then
    return
  fi
  PORT=$(python3 -c "import json; d=json.load(open('config.json')); print(d.get('SERVER_PORT',8080))" 2>/dev/null || echo 8080)
  URL="http://localhost:${PORT}"
  echo -e "${CYAN}[*] Opening browser at ${URL}${NC}"
  if command -v xdg-open &>/dev/null;  then xdg-open  "$URL" 2>/dev/null &
  elif command -v open &>/dev/null;    then open       "$URL" 2>/dev/null &
  elif command -v start &>/dev/null;   then start      "$URL" 2>/dev/null &
  fi
}

stop_signal() {
  echo -e "\n${YELLOW}[*] Shutting down QuantumGlobe...${NC}"
  if [ -f .backend.pid ]; then
    kill "$(cat .backend.pid)" 2>/dev/null || true
    rm -f .backend.pid
  fi
  echo -e "${GREEN}[✓] Stopped.${NC}"
  exit 0
}

trap stop_signal SIGINT SIGTERM

banner
check_python
check_config
setup_venv
install_deps
start_backend "${1:-}"
open_browser "$@"

echo ""
echo -e "${GREEN}${BOLD}QuantumGlobe is running!${NC}"
echo -e "  Backend/Frontend  →  http://localhost:$(python3 -c "import json; d=json.load(open('config.json')); print(d.get('SERVER_PORT',8080))" 2>/dev/null || echo 8080)"
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop."
echo ""

wait
