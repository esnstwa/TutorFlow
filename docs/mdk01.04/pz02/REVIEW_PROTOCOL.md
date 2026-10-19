# Протокол взаимной проверки ПЗ №2 — `PasswordVerifier`

Статус: **техническая проверка выполнена; результаты записаны ниже**. В GitHub отправлен review с аккаунта `esnstwa`; автор PR — `iver-ks`.

- Проверяющий (GitHub): `esnstwa`
- Проект: TutorFlow (`esnstwa/TutorFlow`)
- Дата локального воспроизведения: **20 октября 2026 г.**, UTC+03:00
- Проверенный commit: `9a25e754fd6824e39fa0f7bb0b5f6d0081e85c44`
- Репозиторий/ветка: `esnstwa/TutorFlow`, `feature/0104-pz02-ksenia`
- Pull Request: [#17 — ПЗ №2: контракт и реализации проверки пароля](https://github.com/esnstwa/TutorFlow/pull/17)
- GitHub review: `APPROVED` на указанном commit; PR впоследствии смержен.

## Команды и фактические результаты

Проверка выполнялась в отдельном detached worktree на точном SHA выше.

```text
git fetch origin pull/17/head
exit code: 0
FETCH_HEAD: 9a25e754fd6824e39fa0f7bb0b5f6d0081e85c44

git worktree add --detach <путь-временного-worktree> 9a25e754fd6824e39fa0f7bb0b5f6d0081e85c44
exit code: 0
HEAD: 9a25e754fd6824e39fa0f7bb0b5f6d0081e85c44

uv sync --locked --extra dev
exit code: 0
Среда: CPython 3.14.7; разрешено 47 пакетов, установлено 46.

uv run --locked --no-sync python -m pytest tests/test_auth_module_contract.py tests/test_auth_sessions.py -q
exit code: 0
59 passed, 1 warning in 8.92s
Предупреждение: StarletteDeprecationWarning о связке httpx и starlette.testclient.

uv run --locked --no-sync python -m compileall -q app tests
exit code: 0
```

## Проверяемые случаи

- [x] Штатная пара для `Argon2PasswordVerifier`.
- [x] Пустой пароль возвращает `False`.
- [x] Неправильный пароль возвращает `False`.
- [x] Пустой и искажённый хэш не дают успешной аутентификации.
- [x] Один и тот же `/api/auth/login` проверен с production-реализацией и `FixedPasswordVerifier`.
- [x] Проверен общий HTTP 401 при некорректном хэше; сессия не создаётся.
- [x] Сверены фактические импорты и зависимости модульной карты.

## CI и результат review

- Обязательная проверка GitHub Actions `verify` прошла на том же SHA; run `39334059300`, длительность 58 секунд.
- В diff и проверенных сценариях критических или блокирующих ошибок не обнаружено.
- Review `APPROVED` отправлен аккаунтом `esnstwa` на SHA `9a25e754fd6824e39fa0f7bb0b5f6d0081e85c44`.
- PR #17 смержен 20 октября 2026 г.; merge commit `2a5d92638ab387de51a61f16ce7e1099973ebeb0`.
- Замечаний, требующих исправления и повторной проверки, нет.

## Примечание к комплекту отчёта

`EVIDENCE.md`, `README.md` и DOCX-отчёт фиксируют состояние авторской локальной проверки на **19 октября 2026 г.**, до создания commit и PR. Этот протокол — отдельная запись последующей проверки; исходные материалы с датой 19 октября не переписаны.

В протоколе указан проверяющий GitHub-аккаунт. ФИО и учебная группа в данных GitHub не указаны и не добавлялись по предположению.
