# ПЗ №1 — запуск, сборка и воспроизведение

## Назначение компонента

Проверяемый минимальный компонент — существующий HTTP-сервис TutorFlow и новый модуль `app.core.runtime_diagnostics`. Он сообщает имя приложения и окружение из настроек, версию пакета и Git SHA, пишет безопасные записи о начале/результате запуска и поддерживает `/health`. Модуль не подключается к БД и не печатает `DATABASE_URL`, пароли, токены или содержимое `.env`.

Самостоятельная часть для зоны расписания — обеспечить сохранение `app/web/templates/pages/schedule.html` и `app/web/static/css/schedule.css` при поставке wheel; `scripts/build_component.py` проверяет наличие обоих файлов в собранном пакете. Общая часть каркаса — безопасная runtime-диагностика и проверка конфигурации/SHA. Изменения не меняют бизнес-логику расписания, авторизацию или экраны.

## Настройки и штатная проверка

Создать `.env` из `.env.example` можно только если `.env` ещё нет. Пример уже содержит `APP_NAME=TutorFlow` и `APP_ENV=development`; не переносить реальные секреты в пример конфигурации.

В чистом checkout:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\путь\вне\репозитория\tutorflow-dev"
uv sync --locked --extra dev
uv run --locked --no-sync python -m app.core.runtime_diagnostics
uv run --locked --no-sync python -m pytest tests/test_health.py tests/test_runtime_diagnostics.py -q
uv run --locked --no-sync python scripts/check_component.py
```

Для этой рабочей копии используй внешний путь для окружения: `uv lock --check` обнаружил игнорируемый `.venv`, связанный с отсутствующим интерпретатором. Его не удалять и не пересоздавать; в чистом клоне этой локальной помехи может не быть.

Ожидаемый успешный вывод диагностического CLI — JSON со `status=ok`, `app_name`, `environment`, `version` и `git_sha`, а также записи `component_start` и `component_result` в stderr. Для чистого состояния SHA — 12 шестнадцатеричных символов; если изменены файлы приложения, манифест, lock или скрипт сборки — к SHA добавляется `-dirty`. Значение `unknown` не считается доказательством идентификации исходника.

`APP_NAME` влияет на заголовок приложения и диагностический JSON. `APP_ENV` валидируется как `production`, `development`, `local` или `test`; ошибочное значение останавливает запуск с кодом 2 и сообщением о поле, без печати входного значения:

```powershell
$env:APP_ENV = "invalid-pz01-value"
uv run --locked --no-sync python -m app.core.runtime_diagnostics
$LASTEXITCODE   # ожидается 2
Remove-Item Env:APP_ENV
```

Для проверки HTTP-сценария в режиме разработки:

```powershell
$env:APP_ENV = "development"
uv run --locked --no-sync python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Во втором терминале выполнить `Invoke-RestMethod http://127.0.0.1:8000/health`; ожидаются `status=ok`, версия и SHA. Остановить сервер `Ctrl+C`; повторить команду запуска и запрос. `/health` не проверяет доступность PostgreSQL — это прямо указано в README.

## Режим разработки и поставочный режим

Сценарий сравнения — один и тот же вызов `GET /health` с одинаковыми `APP_NAME` и `APP_ENV`.

| Параметр | Разработка | Поставка |
|---|---|---|
| Подготовка | `uv sync --locked --extra dev`; исходный checkout | `python scripts/build_component.py wheel --out-dir <вне checkout> --work-dir <вне checkout>`; установка wheel в отдельное окружение по lock-файлу |
| Запуск | `uv run ... uvicorn app.main:app --reload` из каталога репозитория | `python -m uvicorn app.main:app` из каталога вне репозитория; код загружается из установленного wheel, без `--reload` и IDE |
| Преобразование кода | CPython загружает `.py`-модули; байткод может кэшироваться по правилам Python | Тот же Python-код в wheel; в поставочном пакете также есть шаблоны, static-файлы и `build-info.json` |
| Оптимизации | Нет отдельной native Debug-сборки | Нет отдельной native Release-сборки; не заявляется выигрыш в скорости |
| Диагностика | stdout/stderr, журнал Uvicorn, `/health`, `pdb` | Тот же `/health` и JSON; версия и SHA читаются из установленного пакета |
| Состав результата | Checkout, виртуальное окружение и исходные файлы | Wheel `tutorflow-*.whl` и отдельное виртуальное окружение с зависимостями из `uv.lock` |

Собирать wheel следует через `scripts/build_component.py`, а не запускать setuptools-сборку в существующем каталоге `build/`: в этом локальном репозитории там уже лежат пользовательские файлы. Скрипт копирует только манифест и каталог приложения во временную staging-копию, добавляет SHA в пакет и отказывает при попытке записать wheel внутрь репозитория или поверх существующего wheel.

Пример PowerShell для проверки wheel вне исходников (подставить новый внешний каталог):

```powershell
$root = (Get-Location).Path
$out = "C:\путь\вне\репозитория\tutorflow-wheel"
$work = "C:\путь\вне\репозитория\tutorflow-temp"
New-Item -ItemType Directory -Force $work | Out-Null
python scripts/build_component.py wheel --out-dir $out --work-dir $work
$wheel = (Get-ChildItem $out -Filter "tutorflow-*.whl").FullName
$runtime = Join-Path $out "runtime-env"
$env:UV_PROJECT_ENVIRONMENT = $runtime
uv sync --locked --no-dev --no-install-project
uv pip install --python (Join-Path $runtime "Scripts\python.exe") --no-deps $wheel
Set-Location $work
$env:APP_NAME = "TutorFlow-PZ01"
$env:APP_ENV = "test"
& (Join-Path $runtime "Scripts\python.exe") -c "import app; print(app.__file__)"
& (Join-Path $runtime "Scripts\python.exe") -m app.core.runtime_diagnostics
```

В последней команде `app.__file__` должен указывать на `site-packages`, а текущий каталог — на внешний `$work`, не на checkout. Для одной и той же HTTP-проверки в этом окружении запустить `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` без `--reload` и выполнить тот же `Invoke-RestMethod`. Для остановки использовать `Ctrl+C`; никаких файлов БД эта проверка не меняет.

Docker-путь использует те же lock и версию сборщика:

```powershell
python scripts/build_component.py image
docker compose up -d
docker compose exec -T web alembic upgrade head
```

Сборщик передаёт SHA/`-dirty` как build-arg. Docker-команда требует запущенного Docker Desktop; если демон недоступен, этот путь помечается непроверенным, а не заменяется успешным выводом wheel-сборки.

## Путь исполнения Python/FastAPI

`pyproject.toml` и `uv.lock` → `uv sync --locked` разрешает Python-интерпретатор и фиксированные зависимости → `setuptools` собирает wheel → CPython загружает Python-модули и формирует/использует bytecode → Uvicorn импортирует `app.main:app` как ASGI-приложение → FastAPI сопоставляет маршрут `/health` → `runtime_info` возвращает версию и SHA → HTTP-клиент получает JSON. В приложении нет собственной native-компиляции; стадий C/C++-компоновки здесь нет.

Команды для подтверждения состава пакета и кода:

```powershell
python -m compileall -q app
python -m dis app/core/runtime_diagnostics.py
python -m zipfile -l <путь-к-wheel>
uv pip tree --python <путь-к-runtime-python.exe>
```

`build_component.py wheel` отдельно проверяет наличие `app/main.py`, диагностического модуля, `build-info.json`, шаблона расписания и CSS расписания в wheel. `uv.lock` фиксирует runtime/dev-граф пакетов с хэшами; Python-ветка фиксируется `pyproject`, Docker и CI как 3.12, конкретный patch-релиз записывается в протоколе вместе с фактическим `python --version`.

## Повторный запуск и восстановление

1. Остановить Uvicorn через `Ctrl+C`; он завершает процесс без удаления данных.
2. Исправить конфигурацию и повторить штатную команду.
3. В wheel-сценарии для нового результата использовать новый внешний каталог; скрипт не перезаписывает существующий wheel.
4. В Docker-сценарии штатная остановка — `docker compose down`; **не добавлять `-v`**, чтобы не удалять volume с данными.
5. Для повторного запуска выполнить снова сборку и команды запуска. Миграции/seed не запускать, если сценарий этого не требует.

## Ограничения доказательств

- Локальный запуск самим автором не является независимым воспроизведением.
- Отчёт о mode comparison заполняется по фактическому результату двух запусков; нельзя подменять наблюдения предположениями о скорости или native-оптимизациях.
- Успешный wheel-тест не доказывает успешность сборки Docker-образа.
- Система CI подтверждает автоматический результат только после фактического GitHub Actions run для соответствующего SHA.
