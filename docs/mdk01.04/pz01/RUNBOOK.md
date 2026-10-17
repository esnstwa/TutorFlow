# ПЗ №1 — запуск, сборка и воспроизведение

## Назначение компонента

Проверяемый минимальный компонент — запускаемый пакет приложения и smoke-сценарий `GET /health` плюс `GET /static/css/schedule.css`. Это не отдельный микросервис: wheel содержит отслеживаемые Python-модули `app/`, шаблоны/статику, metadata `build-info.json` и зависимости, необходимые приложению. Корневые миграции, тесты, документация и неотслеживаемые файлы в staging не копируются. Данный сценарий не подключается к БД, поэтому миграции для него не требуются.

Самостоятельная часть для зоны расписания — обеспечить сохранение `app/web/templates/pages/schedule.html` и `app/web/static/css/schedule.css` при поставке wheel; `scripts/build_component.py` проверяет наличие обоих файлов в собранном пакете. Общая часть каркаса — безопасная runtime-диагностика и проверка конфигурации/SHA. Изменения не меняют бизнес-логику расписания, авторизацию или экраны.

## Настройки и штатная проверка

Создать `.env` из `.env.example` можно только если `.env` ещё нет. Пример уже содержит `APP_NAME=TutorFlow` и `APP_ENV=development`; не переносить реальные секреты в пример конфигурации.

В чистом checkout (внешний путь окружения не затрагивает существующий `.venv`):

```powershell
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:TEMP "tutorflow-pz01-dev"
uv sync --locked --extra dev
uv run --locked --no-sync python -m app.core.runtime_diagnostics
uv run --locked --no-sync python -m pytest -q
uv run --locked --no-sync python scripts/check_component.py
```

Успешный CLI выводит JSON со `status=ok`, `app_name`, `environment`, `version` и `git_sha`, а также `component_start`/`component_result` в stderr. Source checkout берёт SHA через Git и отмечает затронутое незакоммиченное состояние суффиксом `-dirty`; короткие/невалидные SHA отклоняются. Wheel берёт revision из собственного `app/build-info.json` и не ищет Git-репозиторий вокруг `site-packages`. `unknown` не считается идентификацией исходника.

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

Во втором терминале выполнить `Invoke-RestMethod http://127.0.0.1:8000/health` и запросить `http://127.0.0.1:8000/static/css/schedule.css`. `/health` сохраняет совместимый ответ только `{"status":"ok"}`; версия/SHA пишутся один раз в событиях запуска/остановки, не вычисляются на каждый health-запрос. Остановить сервер `Ctrl+C` и повторить запуск. `/health` не проверяет PostgreSQL.

## Режим разработки и поставочный режим

Сценарий сравнения — один и тот же вызов `GET /health` с одинаковыми `APP_NAME` и `APP_ENV`.

| Параметр | Разработка | Поставка |
|---|---|---|
| Подготовка | `uv sync --locked --extra dev`; исходный checkout | Сборка wheel во внешние каталоги; verifier устанавливает wheel в отдельный target-каталог с locked runtime dependencies |
| Запуск | Uvicorn из исходного checkout | Uvicorn запускается verifier из внешнего каталога внутри другого Git-репозитория; импорт должен идти из установленного wheel, без `--reload` и IDE |
| Преобразование кода | CPython загружает `.py`-модули; байткод может кэшироваться по правилам Python | Тот же Python-код в wheel; в поставочном пакете также есть шаблоны, static-файлы и `build-info.json` |
| Оптимизации | Нет отдельной native Debug-сборки | Нет отдельной native Release-сборки; не заявляется выигрыш в скорости |
| Диагностика | CLI, журнал Uvicorn, совместимый `/health`, `pdb` | Те же HTTP-проверки; версия и SHA берутся из `build-info.json` wheel |
| Состав результата | Checkout, виртуальное окружение и исходные файлы | Wheel `tutorflow-*.whl`, установленный в отдельный target-каталог; runtime-зависимости из dev-окружения, подготовленного по `uv.lock` |

Собирать wheel следует через `scripts/build_component.py`: staging получает только `pyproject.toml` и отслеживаемые Git файлы из `app/`, затем сборщик добавляет `app/build-info.json`. Путь вывода и временный каталог должны быть вне checkout; существующий wheel не перезаписывается.

Сборка и end-to-end проверка установленного wheel вне исходников:

```powershell
$stamp = Get-Date -Format yyyyMMddHHmmss
$out = Join-Path $env:TEMP "tutorflow-wheel-$stamp"
$work = Join-Path $env:TEMP "tutorflow-wheel-work-$stamp"
New-Item -ItemType Directory -Force $work | Out-Null
uv run --locked --no-sync python scripts/build_component.py wheel --out-dir $out --work-dir $work
$wheel = (Get-ChildItem $out -Filter "tutorflow-*.whl").FullName
$expected = (git rev-parse --short=12 HEAD).Trim()
if (git status --porcelain --untracked-files=all -- app pyproject.toml uv.lock scripts/build_component.py) { $expected += "-dirty" }
uv run --locked --no-sync python scripts/verify_wheel_runtime.py --wheel $wheel --expected-sha $expected
```

Verifier создаёт временный посторонний Git-репозиторий, устанавливает wheel туда, проверяет импорт из установленного каталога, запускает отдельный Uvicorn и выполняет настоящие HTTP-запросы `/health` и CSS. Временный репозиторий и процесс удаляются/останавливаются после проверки; база данных не используется.

Docker-путь использует те же lock и версию сборщика:

```powershell
python scripts/build_component.py image
docker compose up -d
docker compose exec -T web alembic upgrade head
```

Сборщик передаёт SHA/`-dirty` как build-arg. Docker-команда требует запущенного Docker Desktop; если демон недоступен, этот путь помечается непроверенным, а не заменяется успешным выводом wheel-сборки.

## Путь исполнения Python/FastAPI

`pyproject.toml` и `uv.lock` → `uv sync --locked` подготавливает интерпретатор и фиксированные зависимости → `setuptools` собирает wheel → CPython загружает Python-модули и формирует/использует bytecode → Uvicorn импортирует `app.main:app` как ASGI-приложение → FastAPI маршрутизирует `/health` к неизменному ответу `{"status":"ok"}`. При старте/остановке lifespan один раз записывает runtime-версию и SHA; отдельный запрос `/health` не вычисляет их и не вызывает Git. В приложении нет собственной native-компиляции; стадий C/C++-компоновки здесь нет.

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
