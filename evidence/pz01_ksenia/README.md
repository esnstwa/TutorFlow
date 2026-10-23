# Доказательная база индивидуальной части ПЗ №1

Проект: TutorFlow
Зона ответственности: регистрация и авторизация
Техническая задача: конфигурация и диагностика компонента авторизации
Дата локальной проверки: 19.10.2026

## Базовая версия и изоляция

- Базовый `origin/main`: `3a3f23e2743b4798b9402fa3cc7c298c3a9d834c`.
- Рабочая копия: `C:/Users/kseni/AppData/Local/hermes/cache/scratch/tutorflow-pz01-auth-config-20261019`.
- Рабочая копия создана отдельным `git worktree` в detached HEAD.
- Основная копия `D:/TutorFlow` не изменялась: её локальные изменения сохранены.
- Доказательная база подготовлена отдельно от основной копии; итоговые commit, push и PR фиксируются в метаданных Pull Request.

## Состав локального вклада

1. В `app/core/config.py` добавлены настройки:
   - `SESSION_LIFETIME_SECONDS`, по умолчанию `43200` секунд;
   - `REMEMBER_SESSION_LIFETIME_SECONDS`, по умолчанию `2592000` секунд.
2. Для обоих значений добавлена проверка `> 0`.
3. Для обоих TTL не добавлялось новое cross-field-правило `remember >= обычная сессия`: методичка и существующий путь его не обосновывают.
4. В `app/auth/router.py` жёстко заданные значения заменены выбором соответствующей настройки в общем пути `authenticated_response`.
5. Добавлен отдельный файл `tests/test_auth_configuration.py` с 10 тестами.
6. Существующий `app.core.runtime_diagnostics` переиспользован без вывода секретных значений.

## Фактические проверки

| Доказательство | Фактический результат | Файл / PNG |
|---|---|---|
| Настройки и неверные значения | 10 passed, 2 warnings | `02_auth_configuration_tests.txt` |
| Маршруты регистрации и входа в двух режимах | 1 passed; HTTP 201 Created и HTTP 200 OK | `08_route_two_modes.txt` |
| Валидная конфигурация и диагностика | значения `60` и `120`, `status=ok`, код 0 | `06_diagnostic_valid.txt`, `method_screenshots/04_diagnostic_valid.png` |
| Неверный `APP_ENV` | понятная ошибка поля, код 2, без конфигурационного дампа | `method_screenshots/05_diagnostic_invalid_appenv.png` |
| Целевые auth-тесты | 74 passed, 2 warnings | `03_targeted_auth_tests.txt` |
| Полный регрессионный запуск | 295 passed, 2 warnings | `04_full_pytest.txt` |
| Синтаксис | `compileall` exit 0 | `05_compileall.txt` |
| Wheel вне исходного каталога | `WHEEL_RUNTIME PASS`, health 200, static 200 | `method_screenshots/03_wheel_runtime.png` |
| Отрицательная автоматическая проверка | SHA mismatch, exit 1 | `method_screenshots/07_negative_component_check.png` |

## Ограничения и честные границы

- Скриншоты показывают терминальный вывод; значения cookie, токены, CSRF и пароли в доказательства не выводились.
- Два предупреждения относятся к deprecated API `httpx`/`starlette.testclient` и не привели к падению тестов.
- R6 не повторялся. Использованы ранее подготовленные материалы независимой проверки:
  - `C:/Users/kseni/Desktop/TutorFlow_PZ01_R6_Screenshots/R6_protocol_ksenia.md`;
  - `C:/Users/kseni/Desktop/TutorFlow_PZ01_R6_Screenshots/06_R6_independent_reproduction.png`.
- Р6 повторно не выполнялся: используется существующий протокол и PNG независимой проверки ранее подготовленной версии общего компонента.
- Семь обязательных снимков находятся в `method_screenshots/`: 1 — package scope, 2 — locked toolchain/build, 3 — installed wheel, 4 — valid diagnostics, 5 — invalid APP_ENV, 6 — existing R6, 7 — negative component check.
