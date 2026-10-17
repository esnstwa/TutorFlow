# Декларация инструментального контура

Статус **подключено** означает, что у средства есть команда/маршрут проверки в проекте; это не утверждение о выполнении на чистой машине или успешном GitHub Actions для любого SHA. Результаты конкретного локального запуска указаны в [EVIDENCE.md](EVIDENCE.md), удалённый статус относится только к HEAD PR.

| № | Позиция | Средство | Назначение и подключение | Статус и границы |
|---:|---|---|---|---|
| 1 | Подготовка к исполнению | CPython 3.12+, setuptools, `uv build`; Docker Compose для полного сервиса | `uv sync --locked` подготавливает зависимости; CPython запускает модуль/ASGI; `scripts/build_component.py wheel` собирает wheel во внешнем каталоге. Docker Compose остаётся путём полного приложения. | Подключено. Локальный интерпретатор и целевой CI могут отличаться по patch-версии; см. EVIDENCE. Docker требует доступного daemon. |
| 2 | Управление зависимостями | `pyproject.toml`, `uv.lock`, `uv==0.11.21` | Диапазоны прямых зависимостей задаются в `pyproject.toml`; `uv.lock` фиксирует разрешённый runtime/dev-граф и контрольные хэши. Установка: `uv sync --locked --extra dev`. | Подключено; проверка lock — `uv lock --check`. |
| 3 | Тестирование | pytest и Node.js `node:test` | Python: `uv run --locked --no-sync python -m pytest -q`. JS: `node --test tests/auth-wizard.test.cjs tests/student-lifecycle.test.cjs` и `node tests/test_session_fetch.cjs`. | Подключено; фактические результаты локального запуска приведены в EVIDENCE. |
| 4 | Статический анализ | `compileall` из стандартной библиотеки | `python -m compileall -q app` проверяет синтаксис и компиляцию Python-модулей без запуска приложения; команда включена в Quality Gate. | Подключено в ограниченном объёме. Это не линтер и не type checker; Ruff не включён. |
| 5 | Динамическая диагностика | `pdb` | `python -m pdb -c continue -m app.core.runtime_diagnostics` запускает runtime-диагностику под отладчиком; на остановке можно исследовать кадры/переменные. | Команда доступна; вывод конкретного запуска — в EVIDENCE. |
| 6 | Профилирование | `cProfile` и `pstats` | `python -m cProfile -o <внешний-файл>.pstats -m app.core.runtime_diagnostics`; результат можно прочитать модулем `pstats`. | Демонстрация инструмента для короткого CLI, не benchmark веб-сервиса и не доказательство выигрыша производительности. |
| 7 | Автоматические проверки | GitHub Actions `Quality Gate` | На `pull_request` и `push` в `main` job `verify` ставит locked-зависимости, выполняет `compileall`, проверку допустимой/ошибочной конфигурации и SHA, pytest/Node, PostgreSQL migrations, сборку wheel, установку wheel внутри постороннего Git-репозитория и HTTP smoke-проверку. Отдельный шаг обязан получить код 1 при заведомо неверном SHA. | Реализация workflow подключена. `check_component.py` берёт эталон только через `git rev-parse HEAD`, очищает Git/GitHub/TutorFlow override-переменные из команды чтения HEAD и не передаёт подменяющие SHA runtime-процессу. Успех GitHub Actions утверждается только для совпадающего HEAD PR. |

## Ограничения

- `requires-python` задаёт `>=3.12`; Docker и CI используют ветку 3.12. Фактическую локальную patch-версию нужно фиксировать по `python --version` в протоколе.
- `/health` проверяет доступность HTTP-приложения, а не PostgreSQL; миграции — отдельный CI/production-процесс для полного сервиса.
- Wheel smoke-сценария не включает миграции: для `GET /health` и статического ресурса соединение с БД не нужно.
- Независимое воспроизведение другим студентом, ручная проверка интерфейса, Docker-путь и production-инфраструктура не заменяются локальным тестом/CI.
- Не подключённые Redis, Celery, Ruff, type checker и отдельная система мониторинга не объявляются действующими средствами.
