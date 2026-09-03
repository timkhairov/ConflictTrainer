@echo off
rem Запуск бота из корня проекта (использует локальное виртуальное окружение .venv)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Ошибка: не удалось установить зависимости ^(pip install завершился с ошибкой^).
        echo Проверь подключение к интернету и запусти run.bat ещё раз.
        exit /b 1
    )
)
.venv\Scripts\python -m bot.main
