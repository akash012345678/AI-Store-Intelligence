#!/bin/bash
# ==============================================================================
# PurpleInsight — Production Stack Deployment Orchestrator
# ==============================================================================

# Premium Terminal Colors
export PURPLE='\033[0;35m'
export BLUE='\033[0;34m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export RED='\033[0;31m'
export NC='\033[0m' # No Color

clear
echo -e "${PURPLE}======================================================================${NC}"
echo -e "${PURPLE}  ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗     ███████╗██╗███╗   ██╗ ██████╗██╗  ${NC}"
echo -e "${PURPLE}  ██╔══██╗██║   ██║██╔══██╗██╔══██╗██║     ██╔════╝██║████╗  ██║██╔════╝██║  ${NC}"
echo -e "${PURPLE}  ██████╔╝██║   ██║██████╔╝██████╔╝██║     █████╗  ██║██╔██╗ ██║██║  ███╗██║  ${NC}"
echo -e "${PURPLE}  ██╔═══╝ ██║   ██║██╔══██╗██╔═══╝ ██║     ██╔══╝  ██║██║╚██╗██║██║   ██║╚═╝  ${NC}"
echo -e "${PURPLE}  ██║     ╚██████╔╝██║  ██║██║     ███████╗███████╗██║██║ ╚████║╚██████╔╝██╗  ${NC}"
echo -e "${PURPLE}  ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ${NC}"
echo -e "${PURPLE}======================================================================${NC}"
echo -e "${BLUE}        PurpleInsight AI Store Intelligence — Full Stack Ingestion & UI${NC}"
echo -e "${PURPLE}======================================================================${NC}"
echo ""

# 1. Prerequisite Checks
echo -e "${BLUE}[1/4] Checking environment requirements...${NC}"
if ! [ -x "$(command -v docker)" ]; then
  echo -e "${RED}Error: Docker is not installed or not available on the current PATH.${NC}"
  echo -e "${YELLOW}Please install Docker Desktop (or docker-ce) and retry.${NC}"
  exit 1
fi

if ! [ -x "$(command -v docker-compose)" ] && ! docker compose version &>/dev/null; then
  echo -e "${RED}Error: Docker Compose is not installed.${NC}"
  echo -e "${YELLOW}Please verify your Docker Desktop setup and retry.${NC}"
  exit 1
fi
echo -e "${GREEN}  ✓ Docker & Docker Compose are available.${NC}"
echo ""

# 2. Variable Compilation
echo -e "${BLUE}[2/4] Compiling deployment context...${NC}"
DB_URL="postgresql://purple_user:purple_pass@postgres:5432/purple_store"
API_URL="http://localhost:8000/api/v1"
UI_URL="http://localhost:3000"

echo -e "  - Relational Database : ${YELLOW}PostgreSQL 15 (Alpine)${NC}"
echo -e "  - Database Conn URL   : ${YELLOW}${DB_URL}${NC}"
echo -e "  - Core API Gateway    : ${YELLOW}FastAPI (uvicorn)${NC}"
echo -e "  - Active Store Context: ${YELLOW}store-7ef38ab2-1456-42d4-a0fb-365922e3914a (Brigade Road)${NC}"
echo -e "  - Seeder Source Dataset: ${YELLOW}Brigade_Bangalore_10_April_26 (1)bc6219c.csv${NC}"
echo ""

# 3. Building and Spinning Up
echo -e "${BLUE}[3/4] Launching PurpleInsight full stack via docker compose...${NC}"
echo -e "${YELLOW}This will compile the multi-stage backend layers, spin up PostgreSQL,${NC}"
echo -e "${YELLOW}run schema auto-migrations, seed 1,462 orders, and serve the dashboard.${NC}"
echo -e "${BLUE}Command: docker compose up --build -d${NC}"
echo ""

docker compose up --build -d

if [ $? -ne 0 ]; then
  echo -e "${RED}Error: docker compose up failed to launch successfully.${NC}"
  exit 1
fi

echo ""
# 4. Service Discovery
echo -e "${BLUE}[4/4] Verifying health checks and endpoints...${NC}"
echo -e "${YELLOW}Waiting for relational PostgreSQL database layers and FastAPI health checks to settle...${NC}"
sleep 5

echo ""
echo -e "${GREEN}======================================================================${NC}"
echo -e "${GREEN}   Deployment successfully initiated in background!${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "   Access the high-fidelity UI Dashboard at  : ${YELLOW}${UI_URL}${NC}"
echo -e "   Access the Swagger Interactive API Docs at: ${YELLOW}${API_URL}/docs${NC}"
echo -e "   Access direct health statistics check at  : ${YELLOW}${API_URL}/health${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "   To inspect live compilation logs, run     : ${YELLOW}docker compose logs -f${NC}"
echo -e "   To tear down the containers, run          : ${YELLOW}docker compose down -v${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo ""
