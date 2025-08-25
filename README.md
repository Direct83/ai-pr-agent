# PR AI Reviewer (LangGraph)

Агент для автоматического ревью Pull Request: параллельно проверяет Code Style и Security, публикует инлайн-комментарии и умеет отвечать по @упоминанию.

## Возможности
- Параллельный анализ (LangGraph): CodeStyle + Security
- Инлайн-комментарии в PR (по точному номеру строки или совпадению фрагмента)
- Responder по упоминанию `@ai-reviewer` в комментариях PR
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
- `GITHUB_TOKEN` — токен с правами на чтение репозитория и запись комментариев в PR/Issues
- `GITHUB_REPO` — для локального запуска, формат `owner/repo` (в Actions подставляется автоматически через `GITHUB_REPOSITORY`)
- `BOT_MENTION` — ник-упоминание бота, по умолчанию `@ai-reviewer`

## Локальный запуск ревью PR
Запустить ревью для конкретного PR (нужны `GITHUB_TOKEN` и `GITHUB_REPO` в окружении):
```bash
python -m src.main <PR_NUMBER>
```
Что произойдёт:
1) Получим метаданные PR и `head_sha`
2) Скачаем unified diff и список файлов
3) Запустим параллельно агентов CodeStyle и Security (LangGraph)
4) Сопоставим комментарии с позициями в новой версии и опубликуем инлайн-комменты

## Responder по @упоминанию
В Actions обработчик `src/comment_responder.py` реагирует на событие `issue_comment` при наличии упоминания `@ai-reviewer` в тексте. Он видит последние ~20 сообщений обсуждения и отвечает кратко по делу.

Локально этот сценарий ориентирован на GitHub Actions (читает событие из `GITHUB_EVENT_PATH`).

## GitHub Actions
В проекте есть два workflow:
- `.github/workflows/pr_review.yml` — запускает ревью на событиях PR (`opened`, `synchronize`, `reopened`)
- `.github/workflows/mention_responder.yml` — отвечает на новые комментарии с упоминанием бота

Необходимые секреты репозитория:
- `OPENAI_API_KEY`
- `GITHUB_TOKEN`

## Структура проекта (основные файлы)
- `src/config.py` — загрузка настроек из окружения
- `src/utils.py` — `extract_json`, `build_diff_index`, `resolve_positions`
- `src/github_client.py` — работа с GitHub API (PR info, diff, files, комментарии)
- `src/agents/codestyle_agent.py` — агент проверки code style (ChatOpenAI)
- `src/agents/security_agent.py` — агент проверки безопасности (ChatOpenAI)
- `src/graph.py` — LangGraph: параллельные ветки CodeStyle и Security, узел публикации
- `src/main.py` — точка запуска ревью
- `src/comment_responder.py` — обработчик упоминаний в комментариях PR

## Примечания
- Модель OpenAI и параметры можно менять через `.env`
- Агент возвращает JSON-списки; позиции комментариев уточняются по номеру строки или совпадению фрагмента
- Помните о лимитах и стоимости запросов к LLM
