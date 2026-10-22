@echo off
setlocal
cd /d "%~dp0"
set "COMPOSE_PROJECT_NAME=tutorflow-local"

echo === TutorFlow local launcher ===
echo Using isolated Docker Compose project: %COMPOSE_PROJECT_NAME%
echo The existing default Compose database volume is left untouched.
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is unavailable. Start Docker Desktop and try again.
    pause
    exit /b 1
)

echo [1/4] Building the web image...
docker compose -p "%COMPOSE_PROJECT_NAME%" build web
if errorlevel 1 goto :error

echo.
echo [2/4] Starting the database...
docker compose -p "%COMPOSE_PROJECT_NAME%" up -d db
if errorlevel 1 goto :error

echo.
echo Database migrations can change the local database schema.
echo Back up important database data before continuing.
choice /C YN /N /M "Apply Alembic migrations now? [Y/N] "
if errorlevel 2 goto :migration_skipped

echo.
echo [3/4] Applying database migrations...
docker compose -p "%COMPOSE_PROJECT_NAME%" run --rm web alembic upgrade head
if errorlevel 1 goto :error

:start_web
echo.
echo [4/4] Starting TutorFlow...
docker compose -p "%COMPOSE_PROJECT_NAME%" up -d web
if errorlevel 1 goto :error

echo.
echo TutorFlow is starting at http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
echo.
echo To view logs: docker compose -p "%COMPOSE_PROJECT_NAME%" logs -f web
pause
exit /b 0

:migration_skipped
echo.
echo Migration was skipped, so the site was not started.
echo Run this file again and approve migrations to start the site.
pause
exit /b 1

:error
echo.
echo Startup failed. Check the Docker output above.
pause
exit /b 1
