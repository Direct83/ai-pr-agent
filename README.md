# PR AI Reviewer (LangGraph)

Агент для автоматического ревью Pull Request: параллельно проверяет Code Style и Security, публикует инлайн‑комментарии и отвечает в инлайн‑треде по `@ai` с учётом контекста треда.

## Возможности
- Параллельный анализ (LangGraph): CodeStyle + Security
- Инлайн‑комментарии в PR (по точному номеру строки или совпадению фрагмента)
- Ответы бота в инлайн‑треде по упоминанию `@ai` (через `in_reply_to`) с учётом полного контекста нитки
- Фильтр: анализируются только файлы, чьи пути начинаются с `src/` (чтобы не комментировать служебные файлы)

## Требования
- Python 3.11+
- Аккаунт OpenAI (модель по умолчанию: `gpt-4o-mini`)

## Установка (локально)
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
- `BOT_MENTION` — ник‑упоминание бота, по умолчанию `@ai`
- `REVIEW_ONLY_PREFIXES` — список префиксов для анализа (по умолчанию `src/`). Пример: `REVIEW_ONLY_PREFIXES=src/,app/`

Важно:
- `.env` используется ТОЛЬКО для локальной отладки. В GitHub Actions файл `.env` не применяется.
- В Actions значения передаются через `secrets` и `env` шагов/джоб.

## Локальный запуск ревью PR
Запустить ревью для конкретного PR (нужны `GITHUB_TOKEN` и `GITHUB_REPO` в окружении):
```bash
python -m src.main <PR_NUMBER>
```
Что произойдёт:
1) Скачаем список файлов PR → отфильтруем по `REVIEW_ONLY_PREFIXES` (по умолчанию `src/**`)
2) Сформируем дифф только по выбранным файлам
3) Запустим параллельно агентов CodeStyle и Security (LangGraph)
4) Опубликуем инлайн‑комменты

## GitHub Actions — готовые рабочие конфигурации
Ниже — YAML, которыми можно пользоваться «как есть» в целевом репозитории.

### 1) Ответы на `@ai` в инлайн‑тредах
`.github/workflows/mention_responder.yml`
```yaml
name: AI Mention Responder

on:
  pull_request_review_comment:
    types: [created]

jobs:
  responder:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - name: Checkout agent repo
        uses: actions/checkout@v4
        with:
          repository: Direct83/ai-pr-agent
          ref: main
          path: agent
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: pip install -r agent/requirements.txt
      - name: Respond to mention
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          BOT_MENTION: "@ai"
        working-directory: agent
        run: python -m src.comment_responder
```

### 2) Авто‑ревью PR (CodeStyle+Security)
`.github/workflows/pr_review.yml`
```yaml
name: AI PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]
jobs:
  pr-review:
    uses: Direct83/ai-pr-agent/.github/workflows/pr_review.yml@main
    permissions:
      contents: read
      pull-requests: write
    secrets: inherit
```

Примечания:
- `BOT_MENTION` можно менять (по умолчанию в агенте — `@ai`).
- При желании можно добавить `REVIEW_ONLY_PREFIXES: "src/"` в `env` шага запуска — по умолчанию и так `src/`.

## Структура проекта (основные файлы)
- `src/config.py` — загрузка настроек; `BOT_MENTION`, `REVIEW_ONLY_PREFIXES`
- `src/utils.py` — `extract_json`, `path_included`, `build_filtered_files`, `build_diff_text_from_files`, `build_diff_index`, `resolve_positions`
- `src/github_client.py` — GitHub API (PR info, diff/files, inline‑комментарии, сбор треда, ответ в треде)
- `src/agents/codestyle_agent.py` — агент проверки code style (ChatOpenAI)
- `src/agents/security_agent.py` — агент проверки безопасности (ChatOpenAI)
- `src/graph.py` — LangGraph: параллельные ветки CodeStyle и Security, узел публикации
- `src/main.py` — точка запуска ревью
- `src/comment_responder.py` — inline‑responder по `@ai` (только `pull_request_review_comment`)

## Примечания
- Настройку области анализа меняйте через `REVIEW_ONLY_PREFIXES`
- Ник бота меняйте через `BOT_MENTION` (по умолчанию `@ai`)
- Помните о лимитах и стоимости запросов к LLM
