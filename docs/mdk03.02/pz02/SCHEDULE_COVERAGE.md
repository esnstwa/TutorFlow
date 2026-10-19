# Анализ покрытия — расписание Артёма (ПЗ №2)

**Дата:** 2026-10-12. **Текущая область тестового запуска:** только `tests/test_schedule_pz02.py` (36 собранных вариантов); никаких других pytest-тестов не участвовало в coverage-запуске.
**Риск-ориентированный пересмотр:** [SCHEDULE_RISK_REGISTER.md](SCHEDULE_RISK_REGISTER.md). Общий локальный `TEST_PLAN.md` не отслеживается Git; его замечание о pytest-cov/coverage — исторический baseline, не текущее состояние и не утверждённое требование. Предложенное уточнение FR-07 со статусом PENDING описано в [`../pz01/FR07_OVERLAP_CHANGE_PROPOSAL.md`](../pz01/FR07_OVERLAP_CHANGE_PROPOSAL.md). Общая `tests/conftest.py` всё ещё создаёт свою session-scoped seed-БД, но проверки расписания используют отдельную in-memory SQLite-БД на каждый test case; seed не вызывает расписание-сервисы или router endpoints.

## Среда

- Windows 11; Python 3.12.10; pytest 8.4.2.
- `pytest-cov` 7.1.0 и его dependency `coverage` 7.16.2.
- DB тестов — SQLite `:memory:`; GitHub Actions job — Ubuntu, Python 3.12 и PostgreSQL 16.
- `pytest-cov>=7.1,<8.0` добавлен в `[project.optional-dependencies].dev`; новых прямых библиотек кроме него нет.

## Команда и результаты

Параметры `--cov=app.services --cov=app.web.router --cov-branch` ограничивают сбор этими двумя модулями и включают branch arcs. XML/JSON в команде создаются относительно корня репозитория; `.coverage` — локальный файл данных pytest-cov:

```text
python -m pytest tests/test_schedule_pz02.py -q --cov=app.services --cov=app.web.router --cov-branch --cov-report=term-missing --cov-report=xml:coverage-schedule.xml --cov-report=json:coverage-schedule.json
36 passed, 0 failed, 0 skipped, 1 warning (3.94s)

python -m pytest -q
222 passed, 0 failed, 0 skipped, 1 warning (10.67s)
```

Предупреждение обоих запусков: `StarletteDeprecationWarning` о deprecated-использовании `httpx` с `starlette.testclient`; все тесты завершились успешно. Замеры coverage по двум источникам (вывод `pytest-cov`; колонка Cover объединяет statements и ветвления):

| Область отчёта | Statements покрыто | Branch arcs покрыто | Cover из отчёта |
|---|---:|---:|---:|
| `app/services.py` целиком | 115/173 (66.5%) | 26/48 (54.2%) | 64% |
| `app/web/router.py` целиком | 230/527 (43.6%) | 22/134 (16.4%) | 38% |
| Оба файла целиком | 345/700 (49.3%) | 48/182 (26.4%) | 45% |

**Эти проценты не являются покрытием только расписания:** файлы содержат student, homework, material, review и другие endpoints. Более того, отчёт собран одним сфокусированным запуском, но модульные итоги суммируют непроверенные несмежные функции из тех же файлов.

### Выделенные участки расписания

Исполнительные строки и branch arcs для выбранных функций/строк расписания посчитаны из JSON coverage по диапазонам исходников; границы диапазонов указаны явно, чтобы не выдавать whole-file metrics за schedule-only metrics.

| Участок | Диапазон | Statements | Branch arcs |
|---|---:|---:|---:|
| `local_datetime`, `localize`, `student_dict`, `lesson_dict`, `scoped_student`, `scoped_lesson` (`app/services.py`) | 37–45, 57–75, 122–144, 181–197 | 100% в каждом участке | 100% по ветвям `localize`; в остальных диапазонах ветвей нет |
| Calendar events для занятий (`app/services.py::calendar_events`) | 264–286 | 11/11 | 6/6 |
| Создание занятия (`app/services.py::create_entity`, только `kind == "lesson"`) | 301–327 | 27/27 | 14/14 |
| Страница расписания (`app/web/router.py::schedule`) | 91–93 | 3/3 | Условных ветвей нет |
| Валидация payload для совместимого маршрута (`app/web/router.py::payload_dict`) | 60–63 | 4/4 | 2/2 |
| API расписания (`app/web/router.py`: create compatible, reschedule, update, delete, list, get, create) | 215–249, 252–292, 359–381 | 100% в каждом участке | 100% по всем условным веткам в этих участках |
| Commit guard (`app/web/router.py::commit_or_422`) | 66–71 | 6/6 | Ошибочный IntegrityError path выполнен; отдельной условной ветки в отчёте coverage.py нет |

Это анализ выбранных диапазонов; он не означает 100% всей `services.py` или `router.py`.

## Существенные непроверенные участки и решения

- `app/services.py:252,255,258` — ветви `activity_feed` для отправленной работы, просроченного задания и последнего сообщения. `/schedule` вызывает общий `cabinet_data`, поэтому пустые ветви выполнены, но положительные пути не покрыты: у изолированного учителя нет таких synthetic records. Это риск для общего teacher-shell activity feed, не FR-07; тесты домашки/сообщений вне данного участка.
- `app/services.py:288–290` — календарное событие проверки отправленного домашнего задания. При тестовом GET `/schedule` submitted homework отсутствует, поэтому цикл не выполняется. Это отдельный calendar/review сценарий; FR-07 описывает сохранение и отображение занятия, а не review workflow, поэтому его не фиксировали здесь.
- `app/services.py:295–300, 301, 322–340` — ветви общего `create_entity` для student/assignment/material и альтернативные типы. Schedule-тесты проверяют lesson-путь, не поведение чужих типов; их следует покрывать тестами соответствующих участков.
- По API расписания первоначально оставался guard для JSON не-объекта в `payload_dict` (`app/web/router.py:61–62`); добавлен вариант A-SCH-18. Теперь страница `/schedule` (91–93), payload guard и выбранные lesson API участки имеют 100% строк и всех conditional branch arcs в измеренных диапазонах.
- В `app/web/router.py` ещё пропущены ветви других teacher/student/homework endpoints; в целом модуль имеет 112 непокрытых branch arcs, но 0 partially covered branch points. Это не расписание-специфичные проверки и новые тесты за пределами FR-07 не добавлялись.
- Правило, блокируют ли занятое время занятия со статусом `cancelled`, и политика касания `end == next.start` не определены FR-07. A-SCH-09/A-SCH-12 остаются на согласование; тесты не закрепляют ни текущую реализацию, ни рекомендованный вариант.
- Schedule error paths проверены: чужой/архивный ученик, пустая тема через совместимый и прямой POST, неизвестный статус при создании/обновлении, отсутствие поля переноса, отсутствующий ID, удаление, не-объектный payload и rollback при DB CHECK error; прямое создание также покрывает заметки длиной 0/500/501 и отсутствие записи при отказе. A-SCH-14…20 и A-SCH-25/26 описаны в `SCHEDULE_TEST_CASES.md`.

### Базовый замер до дополнительных coverage-кейсов

Историческое сравнение: самый ранний branch-coverage запуск на 20 вариантах дал `app/services.py` — 41% Cover (167 statements, 92 missed, 44 branch arcs, 3 partial); `app/web/router.py` — 33% (527, 323, 134, 5 partial); суммарно — 35% (694, 415, 178, 8 partial). После A-SCH-14…20, на предыдущем наборе из 31 проверки, показатели whole-file Cover составляли 62%, 38% и 44%; текущий повторный замер на 36 вариантах приведён выше. В историческом отчёте `BrPart` router снизился 5→0, services изменился 3→6. Baseline-отчёт сохранил totals, но не отдельные branch arcs, поэтому сравнение partial-branch origins ограничено. Финальный GET `/schedule` дополнительно заходит в общий teacher-shell `activity_feed` и review-calendar loop; их пустые/неподготовленные данные теперь видны как частично покрытые ветви, перечисленные выше.

## CI

`quality-gate.yml` сохраняет compileall, полный `pytest`, JavaScript и PostgreSQL/Alembic-проверки. Теперь последовательность job: полный Python-набор → JavaScript → PostgreSQL/Alembic → focused coverage → загрузка артефакта. Coverage выполняется только после остальных проверок; его ненулевой exit code завершает job ошибкой. Шаг upload-artifact с `if: always()` следует за coverage и сохраняет XML/JSON под именем `coverage-schedule` (если файлы не созданы — warning). Порог покрытия не установлен; проверки не отключались и не ослаблялись.

Локально подтверждены разбор `pyproject.toml` через `tomllib`, разбор workflow через PyYAML, порядок обязательных шагов и политика сохранения артефакта при ошибке. `pip check` чист; финальный `pip install --dry-run -e '.[dev]'` с build isolation завершился успешно: editable-пакет и зависимости разрешены без установки. Ранее пробный dry-run с `--no-build-isolation` завершился `Cannot import 'setuptools.build_meta'` (setuptools отсутствовал в активной venv); стандартный build isolation устранил ограничение. `actionlint` в окружении отсутствует, поэтому семантическая lint-проверка workflow локально недоступна. При финальном аудите Actions обновлены до Node 24-совместимых major versions; команды JS-тестов и миграций сохранены.

Для опубликованного коммита `54bf940b9e428fb4eae92a4488059542451055eb` GitHub Actions run [#38267883377](https://github.com/esnstwa/TutorFlow/actions/runs/38267883377) завершился со статусом `Success`; job `verify` также завершился `Success`. Создан артефакт `coverage-artem`, содержащий `coverage-artem.xml` и `coverage-artem.json`. Для последующего документационного коммита `b565cae71c72680495849a072376f522a1f9e653` run [#38269437931](https://github.com/esnstwa/TutorFlow/actions/runs/38269437931) также завершился успешно. Каждый результат относится только к указанному SHA; локальные замеры выше остаются отдельными локальными запусками.

Для review-коммита `8c60b666848cf5cd723796de707f4ddf1d9d6bb3` GitHub Actions run [#38282040226](https://github.com/esnstwa/TutorFlow/actions/runs/38282040226) завершился со статусом `Success`; job `verify` также завершился `Success`. Артефакт `coverage-artem` проверен и содержит `coverage-artem.xml` и `coverage-artem.json`; JSON-итоги совпадают с локальным фокусным coverage-запуском выше.

Coverage XML/JSON отчёты хранятся как CI artifact, а не коммитятся в репозиторий. Порог намеренно не задан. Мутационный эксперимент выполнен после этого этапа; фактические результаты и patch приведены в [SCHEDULE_MUTATION_EXPERIMENT.md](SCHEDULE_MUTATION_EXPERIMENT.md). Последующий риск-ориентированный пересмотр и оставшиеся интеграционные ограничения приведены в [SCHEDULE_RISK_REGISTER.md](SCHEDULE_RISK_REGISTER.md).
