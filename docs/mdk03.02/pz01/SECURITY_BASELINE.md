# Security Baseline ПЗ №1

Это ранние ограничения, не полноценная threat model.

## Что защищаем

- аккаунты, роли, password hash;
- server sessions, CSRF и invitation tokens;
- связь преподаватель–ученик и email;
- расписание, приватные заметки, задания, submissions/reviews;
- имена и содержимое загруженных файлов;
- целостность истории и миграций.

## Недоверенный ввод

- JSON/form login, registration и CRUD API;
- URL/query/path identifiers и invitation token;
- заголовки Origin, CSRF и filename/content-type;
- текст тем, комментариев, заметок и сообщений;
- байты файлов и внешние URL;
- переменные окружения и ответы будущих интеграций.

## Роли и доступ

- Anonymous: только public/auth/invitation preview в разрешённых границах.
- Teacher: только собственные Student/Lesson/Homework/Recipient/FileResource.
- Student: только профиль, связанный с его `User`, и собственные recipients/submissions.
- UI не является границей доверия; backend повторяет все проверки роли и ownership.

## Реалистичный ущерб

- захват сессии и чтение учебной/персональной информации;
- подмена сдачи/проверки или назначение чужому ученику;
- связывание invitation не с тем аккаунтом;
- XSS через пользовательский текст/имя файла;
- заполнение диска большим файлом, malware upload;
- потеря БД или файлов из-за отсутствия backup/volume;
- утечка секрета через Git/лог.

## Базовые меры

- Argon2, непрозрачная случайная cookie, SHA-256 token hashes, срок и отзыв;
- HttpOnly/SameSite/Secure в production;
- Origin + CSRF для изменяющих запросов;
- ORM-параметризация, Pydantic validation, DB constraints/FK;
- ownership queries и role dependencies;
- UUID stored filename, `safe_storage_file` ограничивает удаление storage root;
- `.gitignore` исключает `.env`, БД, build и uploads;
- CI работает с тестовыми credentials PostgreSQL, не production secrets.

## Запрещено логировать/публиковать

Пароли и hash diagnostics, cookie/session token, invitation token/полный URL, CSRF token, `.env`, персональные файлы, произвольный request body auth/upload, production DB URL и резервные копии.

## Связанные требования и будущая проверка

| Риск/мера | Требования | Проверка |
|---|---|---|
| Auth/session/CSRF | FR-01–FR-03, NFR-01–NFR-03, NFR-06 | существующие pytest auth/session/security |
| Ownership | FR-04, FR-08, FR-10–FR-12 | cross-user/role integration tests |
| Invitation race | FR-05–FR-06 | текущий concurrency test + повтор на PostgreSQL с N запросами |
| Upload limits/types | FR-14, NFR-09 | TODO: 413/415 tests, лимит и allowlist после согласования |
| Backup/restore | FR-16, NFR-10 | TODO: persistent volume и restore drill |
| XSS | NFR-07 и все текстовые FR | TODO: browser tests с HTML/script payload и проверкой text rendering |
| Brute force/recovery | FR-02, открытый вопрос | TODO: rate-limit policy, email verification/recovery design |

## Раннее решение

До согласования NFR-09 production-приём файлов считать риском; до NFR-10 не заявлять production-ready. Invitation URL передавать только целевому ученику и считать секретом до использования/истечения.
