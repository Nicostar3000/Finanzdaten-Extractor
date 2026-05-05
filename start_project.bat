@echo off
setlocal enabledelayedexpansion

echo ============================
echo Python Projekt LF5 Setup
echo ============================

REM === CONFIG ===
set REPO_URL=https://github.com/Nicostar3000/Python-Projekt-LF5/archive/refs/tags/test.zip
set ZIP_FILE=project.zip
set PROJECT_FOLDER=Python-Projekt-LF5

REM ============================
REM SCRIPT-PFAD
REM ============================
cd /d "%~dp0"
set SCRIPT_DIR=%cd%
echo Script Pfad: %SCRIPT_DIR%

REM ============================
REM PROJEKTORDNER FINDEN
REM ============================
set FOUND_PROJECT=

REM 1) Prüfen, ob der aktuelle Ordner selbst der Projektordner ist
for %%I in (.) do set CURRENT_FOLDER=%%~nxI
echo Aktueller Ordner: %CURRENT_FOLDER%
echo %CURRENT_FOLDER% | findstr /I "^%PROJECT_FOLDER%" >nul
if %errorlevel%==0 (
    set FOUND_PROJECT=%CURRENT_FOLDER%
)

REM 2) Prüfen, ob ein Unterordner existiert, der mit Projektname beginnt
if not defined FOUND_PROJECT (
    for /d %%D in (*) do (
        echo %%D | findstr /I "^%PROJECT_FOLDER%" >nul
        if not errorlevel 1 (
            set FOUND_PROJECT=%%D
        )
    )
)

REM ============================
REM DOWNLOAD, FALLS NICHT VORHANDEN
REM ============================
if not defined FOUND_PROJECT (
    echo Projekt nicht gefunden - lade herunter...
    powershell -Command "Invoke-WebRequest '%REPO_URL%' -OutFile '%ZIP_FILE%'"

    if not exist "%ZIP_FILE%" (
        echo FEHLER: Download fehlgeschlagen!
        pause
        exit /b
    )

    echo Entpacke...
    powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '.' -Force"
    del "%ZIP_FILE%"

    REM GitHub ZIP umbenennen
    for /d %%D in (*) do (
        echo %%D | findstr /I "^%PROJECT_FOLDER%" >nul
        if not errorlevel 1 (
            ren "%%D" "%PROJECT_FOLDER%"
        )
    )

    set FOUND_PROJECT=%PROJECT_FOLDER%
)

REM ============================
REM IN PROJEKTORDNER WECHSELN
REM ============================
cd /d "%SCRIPT_DIR%\%FOUND_PROJECT%"

echo Verwende Projektordner: %FOUND_PROJECT%
echo Aktueller Pfad: %cd%

:SETUP

REM ============================
REM PYTHON
REM ============================
set PYTHON=C:\Python\python.exe

if not exist "%PYTHON%" (
    echo FEHLER: Python nicht gefunden unter %PYTHON%
    pause
    exit /b
)

"%PYTHON%" --version >nul 2>nul
if %errorlevel% neq 0 (
    echo FEHLER: Python existiert, startet aber nicht!
    pause
    exit /b
)

echo Python gefunden:
"%PYTHON%" --version

REM ============================
REM VENV ERSTELLEN
REM ============================
if not exist "venv\" (
    echo Erstelle virtuelle Umgebung...
    "%PYTHON%" -m venv venv
) else (
    echo venv existiert bereits.
)

call venv\Scripts\activate

REM ============================
REM PIP UPDATE
REM ============================
"%PYTHON%" -m pip install --upgrade pip

REM ============================
REM REQUIREMENTS INSTALLIEREN
REM ============================
if exist "requirements.txt" (
    echo Installiere Abhaengigkeiten...
    pip install -r requirements.txt
) else (
    echo WARNUNG: requirements.txt fehlt!
)

echo.
echo ============================
echo Setup abgeschlossen!
echo ============================

REM ============================
REM GUI STARTEN
REM ============================
if exist "gui.py" (
    echo Starte gui.py...
    start "" pythonw gui.py
) else (
    echo WARNUNG: gui.py nicht gefunden!
)
