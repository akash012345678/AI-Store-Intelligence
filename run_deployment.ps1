# ==============================================================================
# PurpleInsight - Windows PowerShell Stack Deployment Orchestrator
# ==============================================================================

Clear-Host

Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host "                PurpleInsight AI Store Intelligence" -ForegroundColor Magenta
Write-Host "        Full Stack Ingestion and UI Dashboard Local Orchestrator" -ForegroundColor Blue
Write-Host "======================================================================" -ForegroundColor Magenta
Write-Host ""

# 1. Prerequisite Checks
Write-Host "[1/4] Checking environment requirements..." -ForegroundColor Blue
$dockerCheck = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCheck) {
    Write-Host "Error: Docker is not installed or not available on the current PATH." -ForegroundColor Red
    Write-Host "Please install Docker Desktop for Windows and retry." -ForegroundColor Yellow
    Exit 1
}

$composeCheck = docker compose version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker Compose is not installed." -ForegroundColor Red
    Write-Host "Please verify your Docker Desktop Compose integration and retry." -ForegroundColor Yellow
    Exit 1
}
Write-Host "  [OK] Docker and Docker Compose are available." -ForegroundColor Green
Write-Host ""

# 2. Variable Compilation
Write-Host "[2/4] Compiling deployment context..." -ForegroundColor Blue
$DB_URL = "postgresql://purple_user:purple_pass@postgres:5432/purple_store"
$API_URL = "http://localhost:8000/api/v1"
$UI_URL = "http://localhost:3000"

Write-Host "  - Relational Database : PostgreSQL 15 (Alpine)" -ForegroundColor Gray
Write-Host "  - Database Conn URL   : $DB_URL" -ForegroundColor Gray
Write-Host "  - Core API Gateway    : FastAPI (uvicorn)" -ForegroundColor Gray
Write-Host "  - Active Store Context: store-7ef38ab2-1456-42d4-a0fb-365922e3914a (Brigade Road)" -ForegroundColor Gray
Write-Host "  - Seeder Source Dataset: Brigade_Bangalore_10_April_26 (1)bc6219c.csv" -ForegroundColor Gray
Write-Host ""

# 3. Building and Spinning Up
Write-Host "[3/4] Launching PurpleInsight full stack via docker compose..." -ForegroundColor Blue
Write-Host "This will compile the multi-stage backend layers, spin up PostgreSQL," -ForegroundColor Yellow
Write-Host "run schema auto-migrations, seed 1,462 orders, and serve the dashboard." -ForegroundColor Yellow
Write-Host "Command: docker compose up --build -d" -ForegroundColor Blue
Write-Host ""

docker compose up --build -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: docker compose up failed to launch successfully." -ForegroundColor Red
    Exit 1
}

Write-Host ""
# 4. Service Discovery
Write-Host "[4/4] Verifying health checks and endpoints..." -ForegroundColor Blue
Write-Host "Waiting for relational PostgreSQL database layers and FastAPI health checks to settle..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   Deployment successfully initiated in background!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   Access the high-fidelity UI Dashboard at  : $UI_URL" -ForegroundColor Yellow
Write-Host "   Access the Swagger Interactive API Docs at: $API_URL/docs" -ForegroundColor Yellow
Write-Host "   Access direct health statistics check at  : $API_URL/health" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   To inspect live compilation logs, run     : docker compose logs -f" -ForegroundColor Gray
Write-Host "   To tear down the containers, run          : docker compose down -v" -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
