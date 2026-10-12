# Мутационный эксперимент — расписание Артёма (ПЗ №2)

**Дата:** 2026-10-12. Эксперимент выполнен только в копии репозитория под Hermes scratch; искусственный дефект не вносился в рабочее дерево.
**Риск-ориентированный пересмотр:** [RISK_REGISTER_ARTEM.md](RISK_REGISTER_ARTEM.md).

## Исходное состояние и правило

- Репозиторий: `main`, исходный commit `3b23f19eb90883f000b3edb091eff279bf686cc9`.
- До эксперимента в рабочем дереве уже были незакоммиченные изменения: `.github/workflows/quality-gate.yml`, `pyproject.toml`, индивидуальный тест Артёма и документы ПЗ №2, включая не принадлежащий Артёму `TEST_CASES_KSENIA.md`. Все они сохранены; коммита, merge и push не было.
- Требование FR-07, `docs/mdk03.02/pz01/REQUIREMENTS.md:27`: преподаватель создаёт занятие **своего активного ученика**.
- Проверяемый кейс: **A-SCH-04**, вариант существующего параметризованного теста:

  ```text
  tests/test_schedule_pz02.py::test_a_sch_04_05_reject_foreign_or_archived_student[foreign]
  ```

- Версия теста зафиксирована SHA-256: `f08c29e76608087a3108e076fed884070cb0d0c791187b44d936c27fe8a8cf3a` (до и после эксперимента одинаковая).
- Синтетические данные тестовой фикстуры: in-memory SQLite, свой преподаватель ID 1, второй преподаватель, собственный активный ученик и активный чужой ученик ID 4. В POST отправляется чужой ID с валидным интервалом `2026-11-10 10:00–11:00`, темой `Алгебра`; проверка ожидает отказ (4xx) и отсутствие новой записи.
- В `Lesson` есть ограничения БД на статус и порядок времени, но нет ограничения владения учеником конкретным преподавателем. Поэтому этот дефект не сводится к срабатыванию DB constraint.

## Изменение в изолированной копии

Минимальный искусственный дефект: убрать `Student.teacher_id == teacher_id` из `scoped_student`. Это ослабляет tenant-scope: преподаватель получает найденного по ID активного ученика другого преподавателя и может создать для него занятие.

Точный patch сохранён в [`mutation_artem.patch`](mutation_artem.patch) и воспроизведён ниже:

```diff
diff --git a/app/services.py b/app/services.py
--- a/app/services.py
+++ b/app/services.py
@@ -182,1 +182,1 @@ def scoped_student(db: Session, teacher_id: int, student_id: int) -> Student | None:
-    return db.scalar(select(Student).options(selectinload(Student.user)).where(Student.id == student_id, Student.teacher_id == teacher_id))
+    return db.scalar(select(Student).options(selectinload(Student.user)).where(Student.id == student_id))
```

Проверка применимости: `patch --dry-run -p1 < docs/mdk03.02/pz02/mutation_artem.patch` успешно проверила файл без его изменения. `git apply --check` в текущем Windows checkout не сопоставил LF patch с CRLF-файлом `app/services.py`; поэтому patch dry-run проверен GNU `patch`.

Копия находилась в `C:/Users/gdddg/AppData/Local/hermes/cache/scratch/TutorFlow-mutation-artem`; `.git` и `.venv` не копировались. Запуски использовали оригинальный venv, но `PYTHONPATH` и `cwd` указывали на копию. Импорт был проверен: `app.services.__file__` указывал на файл в scratch-копии. Сравнение diff подтвердило ровно одну изменённую строку; test SHA копии совпал с исходным.

## Команды и фактические результаты

Окружение: Windows 11, Python 3.12.10, pytest 8.4.2. Во всех pytest-запусках присутствовало одно предупреждение Starlette о deprecated-интеграции `httpx`/`starlette.testclient`; оно не влияло на exit status.

### Исходная логика — рабочее дерево

```text
./.venv/Scripts/python.exe -m pytest 'tests/test_schedule_pz02.py::test_a_sch_04_05_reject_foreign_or_archived_student[foreign]' -q -vv
1 passed, 1 warning

./.venv/Scripts/python.exe -m pytest tests/test_schedule_pz02.py -q
31 passed, 0 failed, 0 skipped, 1 warning
```

### Искусственный дефект — только scratch-копия

```text
PYTHONPATH='C:/Users/gdddg/AppData/Local/hermes/cache/scratch/TutorFlow-mutation-artem' C:/Users/gdddg/Projects/TutorFlow/.venv/Scripts/python.exe -m pytest 'tests/test_schedule_pz02.py::test_a_sch_04_05_reject_foreign_or_archived_student[foreign]' -q -vv
FAILED: `assert response.status_code >= 400`
       `actual: 200 >= 400` (`Response [200 OK]`)
1 failed, 1 warning (0.50s)

PYTHONPATH='C:/Users/gdddg/AppData/Local/hermes/cache/scratch/TutorFlow-mutation-artem' C:/Users/gdddg/Projects/TutorFlow/.venv/Scripts/python.exe -m pytest tests/test_schedule_pz02.py -q
1 failed, 30 passed, 1 warning (2.35s)
```

Это поведенческий FAIL: endpoint вернул **HTTP 200**, хотя FR-07 требует отказ для чужого ученика. Assertion сработал на статусе ответа (тест `tests/test_schedule_pz02.py:164`), а не на импорте, сборке или DB-ошибке.

Дополнительная проверка тем же фикстурным состоянием в копии подтвердила успешную запись: `MUTANT_RESPONSE_STATUS=200`, `LESSON_COUNT=1`, сохранённые `teacher_id=1`, `student_id=4` (ожидаемые ID совпали). Валидный FK не блокировал вставку; mutation действительно обошёл только проверку владельца.

### После эксперимента — восстановленное рабочее дерево

```text
./.venv/Scripts/python.exe -m pytest 'tests/test_schedule_pz02.py::test_a_sch_04_05_reject_foreign_or_archived_student[foreign]' -q -vv
1 passed, 1 warning (0.18s)

./.venv/Scripts/python.exe -m pytest tests/test_schedule_pz02.py -q
31 passed, 0 failed, 0 skipped, 1 warning (2.05s)
```

Production-файл рабочего дерева не изменялся: `app/services.py` SHA-256 до и после — `a383bbf29d947d9371e1cc1fed5874854ce3b25986b4f74f116665e92c1dfc7b`. `tests/test_schedule_pz02.py` SHA-256 также неизменен. Сравнение с копией подтвердило, что приложенный patch точно соответствует единственной mutation-строке.

| Состояние | Выбранный тест | Весь индивидуальный набор |
|---|---|---|
| Исходный код | PASS — 1 passed | PASS — 31 passed |
| Искусственный дефект | **FAIL** — HTTP 200 вместо отказа | **FAIL** — 1 failed, 30 passed |
| После восстановления | PASS — 1 passed | PASS — 31 passed |

Все указанные состояния также имели одно предупреждение Starlette; пропусков не было.

## Дополнительная диагностическая оговорка

Первая отдельная проверка сохранённой строки была запущена вне pytest и не загрузила метаданные моделей, которые регистрирует `tests/conftest.py`; она завершилась `no such table: student_invitations`. Этот запуск не засчитывался ни как FAIL выбранного теста, ни как результат mutation. После загрузки `app.main` перед созданием тестовой схемы проверка в копии завершилась успешно и подтвердила HTTP 200 и сохранённую запись. Основные результаты чувствительности получены стандартными pytest-командами с исходным test module.

## Вывод и ограничения

A-SCH-04 обнаруживает нарушение правила FR-07: если удалить фильтр владения ученика, запрос с действительным чужим `student_id` проходит и сохраняет занятие, после чего существующий assertion фиксирует HTTP 200 вместо ожидаемого отказа. Это свидетельствует о чувствительности конкретного параметризованного варианта к данному классу дефекта. Эксперимент проверяет одну mutation и не является общим mutation score или доказательством чувствительности ко всем дефектам. Спорные правила A-SCH-09/A-SCH-12 не менялись и не проверялись.

Копия была изолирована от рабочего дерева; искусственная логика не попала в `app/services.py` основного репозитория. Артефакты эксперимента: этот отчёт и `mutation_artem.patch`.
