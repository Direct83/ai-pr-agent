# PR AI Reviewer (LangGraph)

Агент для автоматического ревью Pull Request: параллельно проверяет Code Style и Security, публикует инлайн-комментарии и умеет отвечать по `@ai` в инлайн‑тредах.

## Возможности
- Параллельный анализ (LangGraph): CodeStyle + Security
- Инлайн-комментарии в PR (по точному номеру строки или совпадению фрагмента)
- Ответы бота в инлайн‑треде по упоминанию `@ai` (через `in_reply_to`) с учётом полного контекста треда
- Готовые GitHub Actions для автозапуска

## Требования
- Python 3.11+
- Аккаунт OpenAI (модель по умолчанию: `gpt-4o-mini`)

## Установка
```bash
pip install -r requirements.txt
```

## Настройка окружения
Создайте `.env` из примера и заполните значения:
```bash
cp .env.example .env
```
Переменные:
- `OPENAI_API_KEY` — ключ OpenAI
- `OPENAI_MODEL` — модель, по умолчанию `gpt-4o-mini`
- `GITHUB_TOKEN` — токен с правами на чтение репозитория и запись комментариев в PR
- `GITHUB_REPO` — для локального запуска, формат `owner/repo` (в Actions подставляется автоматически через `GITHUB_REPOSITORY`)
- `BOT_MENTION` — ник-упоминание бота, по умолчанию `@ai`

### Использование упоминания @ai (inline-only)
- В инлайн‑обсуждении строки оставьте review‑комментарий с `@ai ...` — бот ответит прямо в треде и учтёт контекст всей нитки.

## Локальный запуск ревью PR
Запустить ревью для конкретного PR (нужны `GITHUB_TOKEN` и `GITHUB_REPO` в окружении):
```bash
python -m src.main <PR_NUMBER>
```
Что произойдёт:
1) Получим метаданные PR и `head_sha`
2) Скачаем unified diff и список файлов
3) Запустим параллельно агентов CodeStyle и Security (LangGraph)
4) Сопоставим комментарии с позициями в новой версии и опубликуем инлайн‑комменты

## GitHub Actions
- `.github/workflows/pr_review.yml` — запускает ревью на событиях PR (`opened`, `synchronize`, `reopened`).
- `.github/workflows/mention_responder.yml` — повторно используемый workflow для inline‑ответов по `@ai`. Достаточно разрешения `pull-requests: write`.

Необходимые секреты репозитория:
- `OPENAI_API_KEY`
- `GITHUB_TOKEN`

## Структура проекта (основные файлы)
- `src/config.py` — загрузка настроек из окружения
- `src/utils.py` — `extract_json`, `build_diff_index`, `resolve_positions`
- `src/github_client.py` — GitHub API (PR info, diff, files, inline‑комментарии, тред и ответы в треде)
- `src/agents/codestyle_agent.py` — агент проверки code style (ChatOpenAI)
- `src/agents/security_agent.py` — агент проверки безопасности (ChatOpenAI)
- `src/graph.py` — LangGraph: параллельные ветки CodeStyle и Security, узел публикации
- `src/main.py` — точка запуска ревью
- `src/comment_responder.py` — inline‑responder по упоминанию `@ai` (только `pull_request_review_comment`)

## Примечания
- Модель OpenAI и параметры можно менять через `.env`
- Позиции комментариев уточняются по номеру строки или совпадению фрагмента
- Помните о лимитах и стоимости запросов к LLM
