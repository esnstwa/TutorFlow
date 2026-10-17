# Фактические доказательства и карта рисунков

Дата локальной проверки: **17.10.2026**. Это рабочий протокол по текущему дереву, а не готовый протокол независимого студента и не ссылка на GitHub Actions.

## Среда и состояние репозитория

- Ветка: `feature/mdk0104-pz01-instrumental-contour`.
- Последний `git fetch origin main`: локальный `HEAD` и `origin/main` совпали на `8592ed601fae`.
- Рабочее дерево намеренно не чистое: в нём текущие незакоммиченные изменения; отдельный ранее существовавший `start_tutorflow.bat` оставлен нетронутым. Код не зафиксирован; текущая диагностическая версия показывает `8592ed601fae-dirty`.
- Локальная среда: Python **3.14.7**, `uv` **0.11.21**, Node **v26.7.0**, pytest **8.4.2**. В проекте `requires-python >=3.12`; Docker и CI выбирают ветку Python 3.12. Проверка на конкретном patch-релизе Python 3.12.x в этой сессии не выполнена. В checkout уже есть игнорируемая `.venv`, у которой `uv` сообщил ссылку на отсутствующий интерпретатор; её не удаляли и не пересоздавали, проектные установки выполнялись во внешнем scratch-окружении.
- Свежая изолированная dev-среда создана командой `uv sync --locked --extra dev` через внешний `UV_PROJECT_ENVIRONMENT`: `Resolved 47 packages`, `Installed 46 packages`; полный набор прошёл в ней.
- Сборочный backend закреплён как `setuptools==84.0.0`; `uv.lock` фиксирует 47 разрешённых пакетов. `uv lock --check` завершился кодом 0 с предупреждением об игнорировании устаревшей локальной `.venv`.
- Wheel — `tutorflow-0.1.0-py3-none-any.whl`. Артефакт проверен вне checkout по адресу `C:\Users\artem\AppData\Local\hermes\cache\scratch\tutorflow-pz01-delivery-v1\tutorflow-0.1.0-py3-none-any.whl`.

## Выполненные команды и результаты

### Р3 — запуск, конфигурация и диагностика

Штатный CLI:

```text
APP_NAME=TutorFlow-PZ01 APP_ENV=test python -m app.core.runtime_diagnostics
INFO component_start
INFO component_result status=ok version=0.1.0 git_sha=8592ed601fae-dirty
{"app_name": "TutorFlow-PZ01", "environment": "test", "git_sha": "8592ed601fae-dirty", "status": "ok", "version": "0.1.0"}
exit code: 0
```

Ошибочная конфигурация:

```text
APP_ENV=invalid-pz01-value python -m app.core.runtime_diagnostics
INFO component_start
configuration_error: app_env: Input should be 'production', 'development', 'local' or 'test'
INFO component_result status=error
exit code: 2
```

Последовательность восстановления также проверена в одном процессе оболочки: корректная конфигурация → `APP_ENV=invalid-pz01-value` → повторная корректная конфигурация; коды возврата `0 → 2 → 0`.

Тесты дополнительно проверяют, что безопасная диагностика не выводит контрольную строку, помещённую в `DATABASE_URL`; реальное значение подключения в доказательства не включено.

`python scripts/check_component.py` завершился сообщением `component_check PASS version=0.1.0 git_sha=8592ed601fae-dirty valid_config=0 invalid_config=2`. Это проверяет обе ветви конфигурации и ожидаемый SHA.

### Р4–Р5 — результат и один сценарий в двух режимах

Финальная сборка прошла командой:

```text
python scripts/build_component.py wheel --out-dir <вне checkout> --work-dir <вне checkout>
BUILD_OK artifact=...\tutorflow-0.1.0-py3-none-any.whl version=0.1.0 git_sha=8592ed601fae-dirty packaged_files=5
```

Проверяющий сборщик подтвердил пять обязательных файлов: `app/main.py`, `app/core/runtime_diagnostics.py`, `app/build-info.json`, шаблон расписания и `schedule.css`. В полном wheel — 107 файлов. Отдельная проверка архива показала `required_present=5 required_total=5`.

Изолированное runtime-окружение создано по `uv.lock` вне репозитория; wheel установлен без повторного разрешения зависимостей. Для одного и того же `APP_NAME=TutorFlow-PZ01`, `APP_ENV=test` дважды выполнен сценарий `GET /health` + `GET /static/css/schedule.css`:

```text
mode=source app_import=<checkout>\app\__init__.py
launch=1 health=200 static=200 css_bytes=23199 version=0.1.0 git_sha=8592ed601fae-dirty app_env=test
launch=2 health=200 static=200 css_bytes=23199 version=0.1.0 git_sha=8592ed601fae-dirty app_env=test

mode=wheel app_import=<внешний runtime-env>\Lib\site-packages\app\__init__.py
launch=1 health=200 static=200 css_bytes=23199 version=0.1.0 git_sha=8592ed601fae-dirty app_env=test
launch=2 health=200 static=200 css_bytes=23199 version=0.1.0 git_sha=8592ed601fae-dirty app_env=test
```

В обоих режимах Uvicorn напечатал `application_start` и `application_stop`. Wheel импортировался из внешнего `site-packages`, запросы проходили при текущем каталоге вне исходников и без IDE. Это проверка упаковки и запуска, не замер производительности. Нативных Debug/Release-оптимизаций Python-пакету не приписываем.

Внешнее runtime-окружение разрешило по lock девять прямых runtime-зависимостей: `alembic 1.20.0`, `argon2-cffi 25.1.0`, `email-validator 2.3.0`, `fastapi 0.143.2`, `jinja2 3.1.6`, `psycopg 3.3.6`, `pydantic-settings 2.16.0`, `sqlalchemy 2.1.4`, `uvicorn 0.54.0`.

Состав Python подтверждён командами `python -m dis app/core/runtime_diagnostics.py` и `uv pip tree --package tutorflow --depth 1 --python <внешний-python.exe>`. Вывод `dis` сохранён в `C:\Users\artem\AppData\Local\hermes\cache\scratch\tutorflow-diagnostics-dis-final.txt`. `cProfile` обработал CLI: 220 960 вызовов и 2 196 функций; файл профиля — `C:\Users\artem\AppData\Local\hermes\cache\scratch\tutorflow-runtime-final.pstats`. Это демонстрация инструментария, не benchmark веб-сервиса. Запуск через `pdb -c continue` завершился кодом 0 и вывел тот же JSON.

### Р7 — проверка с намеренным нарушением

```text
python scripts/check_component.py --expected-sha 000000000000
component_check ERROR: SHA не совпал; ожидался 000000000000, получен 8592ed601fae
exit code: 1
```

Отрицательная проверка завершилась именно ожидаемой ошибкой. Исходные файлы не подменялись ради отрицательного запуска; нарушено только входное условие `--expected-sha`.

### Общие проверки

- `uv lock --check` — код 0.
- `python -m compileall -q app` — код 0.
- Полный `pytest -q` — **258 passed**, один предупреждающий `StarletteDeprecationWarning` о `httpx`/`starlette.testclient`; падений нет.
- Node: **34 теста passed**, `tests/test_session_fetch.cjs` — **6 checks passed**.
- YAML workflow разобран парсером; Docker Compose конфигурация проходит `docker compose config --quiet`.
- `scripts/build_component.py image --dry-run` показал план `docker compose build web` и текущий SHA.
- Фактическая Docker-сборка/запуск невозможны в текущем сеансе: `docker info` вернул код 1, Docker API не найден (`dockerDesktopLinuxEngine`). Docker-образ не объявляется проверенным.
- GitHub Actions для этой незакоммиченной и незапушенной ветки не запускался. Публиковать workflow ради запуска запрещено текущим заданием.

## Карта обязательных снимков экрана 1–7

**Фактических изображений здесь пока нет.** Таблица указывает, что именно нужно захватить настоящим редактором/терминалом; не заменять эти снимки макетом, текстом из этого файла или изображением-заглушкой.

| Рисунок | Что должно попасть в кадр и откуда взять | Статус |
|---:|---|---|
| 1 | В редакторе показать самостоятельный участок расписания: `pyproject.toml` (пакетные ресурсы) и `scripts/build_component.py` (проверка `schedule.html`/`schedule.css`); при необходимости рядом `app/core/runtime_diagnostics.py`. Подпись — «Поставка ресурсов расписания и runtime-диагностика». | Код готов; настоящий снимок редактора сделать вручную. |
| 2 | Терминал с двумя режимами: сначала внешний путь `UV_PROJECT_ENVIRONMENT=<вне checkout>` и `uv sync --locked --extra dev`, затем `python scripts/build_component.py wheel --out-dir ... --work-dir ...`, с выводом `BUILD_OK`. Не писать про `-O`/native Release: таких настроек у этого Python-wheel нет. | Обе команды и wheel фактически проверены; снимок терминала сделать вручную. |
| 3 | Терминал из внешнего каталога: путь `app.__file__` внутри `runtime-env\Lib\site-packages`, запуск Uvicorn, успешные `health=200` и `static=200`. Команда сравнения — `python <scratch>\verify_tutorflow_modes.py compare ...`; либо повторить ручную команду из `RUNBOOK.md`. | Wheel фактически запущен вне checkout; снимок сделать вручную. |
| 4 | Штатный запуск `python -m app.core.runtime_diagnostics`: команда, JSON с `version=0.1.0`, `git_sha=...-dirty`, `status=ok`, успешная диагностика и код 0. | Фактический вывод есть выше; снимок терминала сделать вручную. |
| 5 | Та же команда с `APP_ENV=invalid-pz01-value`: `configuration_error`, отсутствие секретных значений и код 2. | Фактический вывод есть выше; снимок терминала сделать вручную. |
| 6 | Чистое окружение другого студента, точный commit, установленные версии, команды, запуск и результат; заполнить [шаблон протокола](REPRODUCTION_PROTOCOL_TEMPLATE.md). | Не выполнялось. Нужен другой студент и проверяемая неизменяемая версия исходника. |
| 7 | Терминал с `python scripts/check_component.py --expected-sha 000000000000`, понятным несовпадением и кодом 1. | Фактический отрицательный вывод есть выше; снимок терминала сделать вручную. |

## Что ещё нужно закрыть

1. Сделать и вставить семь подлинных снимков в отчёт; рисунок 6 — только после проверки другим студентом.
2. Провести независимое воспроизведение на чистом окружении и заполнить протокол. Текущий авторский запуск этим не считается.
3. После разрешённой публикации PR/ветки дождаться GitHub Actions и добавить ссылку на фактический run. Сейчас коммит/PR/push/merge/tag не создавались по прямому ограничению задания.
4. Если для сдачи требуют точного совпадения patch-версии Python, провести проверку на целевом Python 3.12.x; локальный фактический запуск выполнен на Python 3.14.7.
5. Docker-образ проверить после запуска Docker Desktop; текущая проверка ограничена YAML/Compose-конфигурацией и dry-run.

## Примечание о локальных build-артефактах

Во время ранней базовой сборки `uv build`, выполненной до появления staging-сборщика, setuptools обновил игнорируемые генерируемые файлы каталога `build/`. Этот каталог существовал заранее и содержит пользовательские материалы; никакие файлы из него не удалялись намеренно, но прежнее содержимое генерируемых package-artifacts не восстанавливается из Git. Финальная подтверждённая сборка выполнялась безопасным staging-скриптом во внешнем scratch-каталоге. База данных/пользовательские файлы не заменялись намеренно.
