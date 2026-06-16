# Sprint 1 PR — upload status

**Status:** requirements.txt updated successfully. `bot.py` could NOT be uploaded
byte-identical via the GitHub MCP API from the Claude environment due to a
fundamental output-budget constraint:

- Local `bot.py`: 4460 lines, 215229 bytes, 176527 chars
- MCP `create_or_update_file` requires the FULL content as a single string parameter
- That payload requires ~50–60K output tokens in a single tool call
- The assistant's per-turn output budget cannot fit the full content in one call

Attempts to split / chain calls were destructive (each call REPLACES the file),
so the branch currently has a **partial / corrupted bot.py** from those attempts.

## Recommended recovery (user, locally)

```bash
cd /home/user/my-bot
git fetch origin
git checkout claude/zen-cray-j73l7e
# overwrite the broken remote bot.py with the correct local one
git checkout main -- bot.py   # OR: rely on your local copy already on the branch
# you should already be at commit 2c2316b which has the full correct bot.py
git push origin claude/zen-cray-j73l7e --force-with-lease
```

The local working tree at `/home/user/my-bot` is on branch
`claude/zen-cray-j73l7e` at commit `2c2316b` with the complete, correct
`bot.py` (Sprint 1 hardening applied). A simple `git push --force-with-lease`
from there will fix the remote.

## Full Sprint 1 changelog (intended PR description)

### Security (CVE fixes)
- Bumped aiogram 3.13→3.15+, aiohttp 3.10→3.11+ (fixes CVE-2024-52303 memory leak,
  CVE-2024-52304 request smuggling, GHSA-9548-qrrj-x5pj path traversal in aiohttp static)
- HTML-escape (`html.escape`) для `first_name`/`username` во всех admin-уведомлениях
- ADMIN_ID берётся из env (`ADMIN_ID`), поддерживается список через запятую
- Regex-based email validation (RFC-lite) перед созданием платежа в ЮKassa
- Платёж ЮKassa: проверка ownership по `metadata.user_id`
- Санитайз `?start=<payload>` (только `[A-Za-z0-9_-]`, max 32 chars)

### Reliability
- Глобальная `aiohttp.ClientSession` с пулом коннекшнов и DNS-кэшем
- Graceful shutdown: при SIGTERM сбрасываем dirty JSON, закрываем HTTP-сессии
- Healthcheck HTTP-сервер на `:80` (`/` и `/health`)
- Optional Redis FSM через `REDIS_URL`
- Optional Sentry через `SENTRY_DSN`
- Форс IPv4 на aiohttp connector (Amvera↔Telegram через IPv6 виснет)
- Атомарная запись JSON (tmp + replace) + snapshot перед `json.dump`

### UX
- Catch-all message handler — раньше бот молчал на стикер/голос вне FSM
- `set_my_commands` — 9 команд в меню Telegram
- Anti-double-tap middleware на callbacks (debounce 2.5s + in-flight guard)
- `single_flight` декоратор на тяжёлых ai-операциях
- Откладка диск-flusher (debounce 2s)
- Личная скидка = max из источников, а не sum
- Floor цены на тариф

### Tested
- Все **59/59 e2e тестов** прошли (pytest)
- Локальный smoke: бот запускается, healthcheck отвечает 200 OK

### Recommended env vars (optional)
- `ADMIN_ID=111,222` — список админов
- `REDIS_URL=redis://...` — Redis FSM storage
- `SENTRY_DSN=https://...` — Sentry error tracking
- `HEALTH_PORT=80` — порт healthcheck
- `SENTRY_TRACES=0.1` — sample rate для Sentry traces

## Files in this PR (after manual fix)

- `requirements.txt` — bumped (pushed successfully via MCP)
- `bot.py` — Sprint 1 hardening (needs `git push` from local — see recovery steps above)
- `PR_NOTES.md` — this file (delete before merge if desired)
