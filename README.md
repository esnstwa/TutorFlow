# TutorFlow

TutorFlow — веб-платформа для взаимодействия частных репетиторов и учеников.

## Architecture

Технические решения, границы модулей и правила организации проекта описаны в [docs/architecture.md](docs/architecture.md).

## Запуск backend

```bash
docker compose up --build
```

Перед первым запуском приложения примените миграции и явно загрузите демонстрационные данные:

```bash
alembic upgrade head
python -m app.seed
```

`app.seed` предназначен только для development-окружения и идемпотентен. В production он автоматически не запускается.
Development-кабинет использует пользователя `DEV_TEACHER_EMAIL`; в production необходимо установить `ENABLE_DEV_TEACHER_FALLBACK=false`, чтобы принимать только пользователя из auth middleware (`request.state.user`).

Проверка состояния приложения: [http://localhost:8000/health](http://localhost:8000/health).
