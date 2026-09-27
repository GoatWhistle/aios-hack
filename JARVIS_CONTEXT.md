# Джарвис: актуальный контекст для финала

Снимок: 26.09.2026, база `d0da1c3` + рабочие изменения подключения NunAway. Фронтенд и Джарвиса можно дорабатывать; вычислительная цепочка поиска, OPM и ЧДД остаётся источником фактов. Исторический продуктовый замысел — [JARVIS.md](../aios-hack/aios/JARVIS.md); поведение ниже сверено с текущим кодом.

## Роль в решении

Джарвис — визуальный ассистент аналитической консоли. Он получает контекст текущего экрана (сценарий, шаг, дату, выбранную скважину, раздел и вид), обращается к предметным инструментам, показывает карточки с происхождением данных, краткую подпись и развёрнутый ответ. Действие карточки может открыть нужный экран, сценарий, шаг или скважину в консоли. Джарвис объясняет план и результаты; команды управления скважинами и заявляемый ЧДД формируются другими контекстами.

Точки входа: [JarvisProvider.tsx](frontend/src/jarvis/provider/JarvisProvider.tsx), [useSessionValue.ts](frontend/src/jarvis/provider/useSessionValue.ts), [JarvisScreen.tsx](frontend/src/jarvis/screen/JarvisScreen/JarvisScreen.tsx), [assistant_service.py](backend/contexts/assistant/application/assistant_service.py).

## Путь вопроса

```text
Консоль → JarvisProvider → POST /api/jarvis/ask → Orchestrator
  → LLM вызывает предметные инструменты → карточки + данные
  → LLM составляет подпись и ответ → проверка чисел и кода
  → SSE-события → сцена, орбита карточек, история
```

- Фронт формирует `context` из активного сценария, шага, даты, скважины и маршрута. Транспорт — [sseTransport.ts](frontend/src/jarvis/transport/sseTransport.ts); контракт событий и разбор — [events.ts](frontend/src/jarvis/transport/events.ts). Поток включает `scene`, `status`, `card`, `caption_delta`, `caption`, `answer_delta`, `answer`, `warning`, `suggestions`, `done`, `error`. Временные `*_delta` показываются до окончательной проверки; финальные `caption`/`answer` проходят guard.
- [Orchestrator](backend/contexts/assistant/application/orchestrator.py) собирает системный промпт с контекстом экрана и состоянием системы, ведёт до пяти раундов tool calling, хранит память сессии и передаёт события в SSE. Лимит одного ответа — 60 секунд в [orchestrator_events.py](backend/contexts/assistant/application/orchestrator_events.py).
- Каталог из 25 предметных инструментов находится в [tools/__init__.py](backend/contexts/assistant/application/tools/__init__.py), схемы и валидация аргументов — в [tools/registry.py](backend/contexts/assistant/application/tools/registry.py). Темы: скважина и её ряды, сравнение двух скважин, метрики поля, события, решения и правила, λ, сравнение сценариев и прогонов, ЧДД/сдача, ограничения, физический отчёт, документация и карта системы.
- Инструменты читают [JSON-витрину](frontend/public/data), каталог прогонов `out/runs`, [базу знаний](frontend/public/jarvis/knowledge) и индекс Markdown. Их общий контекст — [context.py](backend/contexts/assistant/application/tools/context.py), хранилища — [artifacts](backend/contexts/assistant/infrastructure/artifacts/). У каждого `Card` есть `type`, `title`, `payload`, `provenance` и возможное `action`.
- Проверка финального текста в [caption.py](backend/contexts/assistant/application/caption.py) и [guard.py](backend/contexts/assistant/domain/guard.py) удаляет числа без опоры на данные карточек/артефактов; для подписи возможна одна попытка переписать её. Блоки кода без подтверждения источником также отсекаются. Это ограничение на текстовый ответ, а не новая проверка физики.

## Что видит пользователь

- Кнопка со сферой [JarvisLauncher.tsx](frontend/src/jarvis/stage/JarvisLauncher/JarvisLauncher.tsx) открывает отдельную сцену через переход [JarvisStage.tsx](frontend/src/jarvis/stage/JarvisStage/JarvisStage.tsx). При слабой анимации включается crossfade; предпочтение reduced motion учитывается в провайдере.
- [JarvisScreen.tsx](frontend/src/jarvis/screen/JarvisScreen/JarvisScreen.tsx) показывает контекст, статус, карточки на орбите, подпись, раскрываемый ответ, историю, подсказки и поле ввода. Фронт ограничивает орбиту восемью карточками в [scenes.ts](frontend/src/jarvis/model/scenes.ts).
- Действия карточек применяются в порядке сценарий → маршрут → шаг → скважина → воспроизведение → подсветка в [consoleActions.ts](frontend/src/jarvis/actions/lib/consoleActions.ts). Это навигация и фокус интерфейса.
- Есть история сессий на сервере и локальный `session_id` в браузере: [sessions.ts](frontend/src/jarvis/model/sessions.ts), [session_store.py](backend/contexts/assistant/infrastructure/session_store.py). При первом открытии фронт пытается восстановить историю, затем запрашивает краткий briefing. Пустой/недоступный сервер превращается в сцену ошибки.
- Голос: ввод через браузерное SpeechRecognition; при его недоступности или сетевой ошибке возможна серверная расшифровка записи через OpenRouter. Вывод через `edge-tts`, с запасным браузерным `speechSynthesis`. Пути: [MicButton.tsx](frontend/src/jarvis/voice/MicButton/MicButton.tsx), [stt.py](backend/contexts/assistant/infrastructure/stt.py), [tts.py](backend/contexts/assistant/infrastructure/tts.py), [useVoiceOutput.ts](frontend/src/jarvis/voice/useVoiceOutput.ts).

## API, данные и деплой

- HTTP-сервис: [server.py](backend/interfaces/http/assistant/server.py). Маршруты: `GET /health`, `/briefing`, `/sessions`, `/sessions/{id}`, `/voices`; `POST /ask`, `/cancel`, `/speak`, `/transcribe`; `DELETE /sessions/{id}` — все под `/api/jarvis`.
- Провайдер LLM: в локальном `.env.local` выбран `openai-compatible`, NunAway `https://nunaway.lol/v1`, модель `gpt-5.5`. Ключ хранится в `JARVIS_API_KEY`. Без явного конфига сохраняется прежний выбор OpenRouter/Anthropic по наличию ключа; совместимый режим использует только свой ключ и URL. Выбор в [provider.py](backend/contexts/assistant/infrastructure/llm/provider.py). `JARVIS_MAX_TOKENS` по коду равен 2400. Для STT нужен `OPENROUTER_API_KEY`, для серверного TTS — установленный `edge-tts` и сеть.
- Локальный CLI: `.venv/bin/aios jarvis --host 127.0.0.1 --port 8010`, `.venv/bin/aios jarvis --check`; `.env.local` читается автоматически, экспортированные переменные имеют приоритет, есть `--env-file`; [jarvis.py](backend/interfaces/cli/jarvis.py). В compose отдельные `web` и `jarvis`: `web` проксирует `/api/jarvis/*` на сервис, а оба читают одну витрину; [docker-compose.yml](docker-compose.yml). Сессии в compose сохраняются в `/out/jarvis/sessions`.
- Индекс документов по умолчанию читает Markdown корня репозитория и соседний `../docs`, если он есть; в compose корни задаёт `AIOS_JARVIS_DOCS=/app;/data/docs`. На этой машине `../docs` отсутствует; в локальном env заданы `.;../aios-hack/docs;../aios-hack/aios`. Индекс загрузил 1201 фрагмент документов на момент проверки. При деплое нужны пути и монтирования контейнера. См. [sources.py](backend/contexts/assistant/infrastructure/docs_index/sources.py).

## Фактические ограничения текущей версии

1. **Без ключа нет автоматического демо.** `health` и `ask` возвращают `503 no-api-key`; [createTransport.ts](frontend/src/jarvis/transport/createTransport.ts) всегда выбирает SSE, а [vite.config.ts](frontend/vite.config.ts) удаляет фикстуры из production-сборки. Файлы [fixtures](frontend/public/jarvis/fixtures) существуют для записи и проверок. Старые описания демо-режима в историческом `JARVIS.md` не соответствуют этому коду; сообщения entrypoint исправлены.
2. **Часть ответов зависит от внешних артефактов.** Инструменты истории и сдачи читают каталог `AIOS_JARVIS_RUNS`; локально подключён `out/jarvis-evidence-20260926/runs` с двумя свежими прогонами. Финальный `candidate-018` найден в `artifacts/surrogate-trajectory-ab-20260910/final-submission`, совпадает с champion и reference-parity, а selfcheck проходит. Его пакет содержит план и проверочную историю, но оригинальный run manifest, журнал решений и response-файл локально отсутствуют. Реестр `artifacts/jarvis-scenario-registry.json` показывает результат плана и явно отмечает, что причины генерации недоступны.
3. **Наличие сервиса не равно готовности показа.** Нужно различать доступность API, наличие ключа, данные витрины, индекс документов, сессии и голосовые возможности. [health](backend/contexts/assistant/application/assistant_service.py) сообщает их раздельно; фронт показывает индикаторы в [ContextRibbon.tsx](frontend/src/jarvis/scene/ContextRibbon/ContextRibbon.tsx).
4. **Числовой guard применяется к окончательному тексту.** Промежуточные потоковые дельты появляются на экране раньше финального `caption`/`answer`. Это важно учитывать при подготовке живой демонстрации.
5. **Журнал решений подключён отдельно от витрины.** При чтении JSON 26.09 обнаружено: `base/trace.json` и `policy-plan/trace.json` содержат только метаданные; записи `whatif-injection-cut/trace.json` помечены `synthetic-demo`. В `frontend/public/data` отсутствуют `hierarchy.json` и `hierarchy-index.json`; загрузчик сообщает `available=false`, не ломая health и другие инструменты. Реальный диагностический журнал проиндексирован рядом с прогоном: 21 594 записи, ключ `(run_id, well, step)`, проверены хеш расписания и исходного журнала; импорт сверяет пары скважина/шаг с наблюдениями. `decision_journal` по конкретному `run_id` возвращает вход, стадии FIELD/GROUP/WELL, предложения, окончательные команды, отдельный статус OPM и допуска. Карточка `rule` показывает эти основания, включая отсутствие сработавших правил и различие предложения от окончательной команды. Для run-backed объяснения карточка дополнительно строит ряд входного отклика и итоговой уставки из записей именно этого прогона; сравнение явно показывает разные источники и не утверждает причинную связь. Ряд выделяет выбранный контрольный шаг и может оставаться в панели рядом с консолью. Дата берётся из OPM schedule deck: 224 шага от 01.01.2007 до 01.08.2025; терминальная дата 01.09.2025 не считается шагом решения. Проекция отдельно не записана, поэтому её причина не выдумывается. Повторный исторический OPM-прогон зарегистрирован как результат без журнала; он не получает выдуманных причин. `run_history` различает диагностический, исторический и сданный планы. Исходный файл response, соответствующий хешу обратной связи, локально не найден; для него нет `submitted`-сценария.

## Карта для будущей доработки

| Задача | Основные места |
|---|---|
| Поведение вопросов, инструментов и достоверность | `backend/contexts/assistant/application/{orchestrator.py,tools/}`, `backend/contexts/assistant/domain/guard.py`, ресурсы промпта |
| Состав и качество источников | `backend/contexts/assistant/infrastructure/{artifacts/,docs_index/,knowledge.py}`, `frontend/public/jarvis/knowledge/` |
| Сцена, карточки, навигация | `frontend/src/jarvis/{screen/,scene/,cards/,actions/,provider/}` |
| SSE, ошибки, история | `backend/interfaces/http/assistant/server.py`, `frontend/src/jarvis/{transport/,model/sessions.ts,model/scenes.ts}` |
| Голос | `backend/contexts/assistant/infrastructure/{stt.py,tts.py}`, `frontend/src/jarvis/voice/` |
| Сборка и показ | `docker-compose.yml`, `docker/entrypoint.sh`, `frontend/vite.config.ts`, `frontend/public/data/` |

Этот документ описывает текущую реализацию и точки изменений. План доработок для финала с приоритетами, зависимостями и критериями готовности — [JARVIS_BACKLOG.md](JARVIS_BACKLOG.md). Подключение и запуск завершены (J-00); J-03 выполнен частично, агрегирующий журнал решений и карточка подключены для импортированного диагностического прогона. Полный сценарий объяснения и остальные пункты плана ещё предстоит реализовать.

## Настоящие прогоны и основания объяснений — 26.09.2026

По просьбе команды выполнены два свежих OPM-прогона в `out/jarvis-evidence-20260926`. Полные деки и нормативы найдены в `../aios-hack/docs/models`; работоспособное Python-окружение — `../aios-hack/aios/.venv`, Docker-образ OPM уже установлен. Для этих расчётов LLM API-ключ не нужен. Сохранённый веб-прогон от 06.09 найден в `../aios-hack/aios/out/web-runs/web-20260906-173732-e33316c9` вместе с расписанием, откликом, исходными ограничениями, экономикой и файлами симулятора.

Для нового диагностического прохода текущей `make_policy` записаны фактические входы и результаты `run_step` непосредственно при формировании расписания: 224 шага, 52 125 записей правил, 21 594 пары «скважина — шаг», 103 скважины. Все 43 196 окончательных команд связаны с этими записями. Скрипт запуска и упаковщик находятся в каталоге эксперимента; код вычислительного решения не изменён. Используются существующие `default_theta`, измеренная λ и реальный базовый отклик; это один диагностический проход, а не новый результат оптимизации, не замкнутый цикл и не сданный план. Результат OPM и соблюдение ограничений следует брать из манифеста соответствующего прогона.

**Уточнение о старом экспорте:** `showcase/application/exporters/hierarchy_view.py:run_hierarchy_steps` заново вызывает политику с `default_theta` по переданной траектории. Такой экспорт сам по себе не доказывает, что именно эти рекомендации породили сохранённое расписание. Для объяснения выбранного действия нужны записанный при генерации журнал, происхождение входного отклика и окончательная команда после проекций/округления. Новые `decision-journal.jsonl`, `hierarchy-recorded.json` и `well-explanations.json` сохраняют это разделение.

Итоги: повтор исторического плана — `sound=true`, ЧДД 11 871 040 205,818085 ₽, точное совпадение с архивом; диагностический план — OPM OK, `sound=false`, 165 нарушений водного баланса. Детали, ограничения применимости и файлы: [JARVIS_RUNS_20260926.md](JARVIS_RUNS_20260926.md). Для завершения постобработки исправлены устаревшие пути исходников в хеше методики; формулы сохранены.

## Уточнение о провайдере ключа — 26.09.2026

Пользователь сообщил, что ключ из локального env выдан NunAway. Это не прямой Anthropic API: проверять и использовать его следует только на согласованном сервисе `https://nunaway.lol`, OpenAI-совместимый base URL — `https://nunaway.lol/v1`, Bearer-аутентификация. Значение ключа в документах не сохраняется. `POST /api/check` подтвердил `ok=true`, `GET /v1/models` вернул 39 моделей. При первой проверке генерация не была подтверждена: запрос к `claude-sonnet-4-6` с инструментом завершился таймаутом 40 с, простой запрос к `claude-haiku-4-5` — таймаутом 45 с. Модель `gpt-5.4-mini` из публичного примера сервиса отсутствует в доступном каталоге (`400 model_not_found`). Причина задержек не установлена.

Первоначальная проверка через прямой Anthropic дала 401: ключ относится к другому сервису. Сейчас factory поддерживает явный режим `openai-compatible`, который передаёт ключ только на настроенный URL. В `OpenRouterClient` добавлено доверие CA bundle `certifi` вместе с системными корнями; проверка TLS не отключалась.

Повторная проверка по подробному гайду NunAway: минимальный запрос `gpt-5.5` через `/v1/chat/completions` завершился HTTP 200 за 2,92 с. Проверен и штатный `OpenRouterClient` с явным `base_url` NunAway: SSE/tool calling, ответ инструмента и финальный текст «РАБОТАЕТ» — полный цикл за 4,36 с. Следовательно, ключ и этот маршрут генерации рабочие. Ранее короткий пример сайта с `gpt-5.4-mini` не соответствовал каталогу. Причина прежних таймаутов Claude не установлена; переносить успех GPT на доступность Claude нельзя. Постоянная конфигурация factory и переменные compose теперь добавлены; внешний деплой ещё не проверен.

Отдельный минимальный запрос `claude-sonnet-4-6` по тому же маршруту завершился таймаутом 120 с без полученных байтов. На момент проверки работоспособность этого model ID через NunAway не подтверждена.

## Рабочий запуск после интеграции — 26.09.2026

- Создано локальное Python 3.12 окружение `.venv` с `.[jarvis]`; фронтенд установлен через `npm ci` и собран через `npm run build`.
- `.env.local` содержит настройки NunAway и ключ в `JARVIS_API_KEY`, права файла `600`; файл исключён из Git и Docker context. Пример без секрета — [.env.example](.env.example).
- Поднят backend `127.0.0.1:8010` и Vite **http://127.0.0.1:5199/**. Команды повторного запуска — в [README.md](README.md#джарвис).
- Health: HTTP 200, provider `openai-compatible`, model `gpt-5.5`, источник витрины `model-z-base-run`; 71 термин, 11 экранов, 18 узлов карты системы, 1201 фрагмент в индексе документов при первом запуске.
- Настоящий `POST /api/jarvis/ask` через Vite: «Покажи состояние скважины 10 на выбранном шаге. Используй данные витрины.» Контекст `base`, шаг 0. За 11,60 с выполнен `well_snapshot`, получены карточка с происхождением, навигация и финальная подпись с `grounded=true`; поток завершился без ошибок. Свидетельство: `out/jarvis/live-check-20260926.json`.
- `POST /api/jarvis/speak`: HTTP 200, `audio/mpeg`, 14 256 байт, 0,77 с. Отдельный ключ для озвучки не понадобился.
- Проверка UI в настоящем браузере недоступна в текущем окружении инструмента управления браузером. Клики, микрофон, прерывание озвучки и внешний HTTPS остаются в приёмке J-16/J-17/J-18.
- Наличие рабочего LLM не означает готовность объяснений причин для всех планов: журнал доступен только у диагностического прогона через `AIOS_JARVIS_RUNS`, отдельно от витрины. Происхождение сданного расписания предстоит установить отдельно.

Полный план расширен задачами J-22–J-26: стартовая сводка, аудит всех 24 инструментов, история и уточнения, актуальная база знаний, наблюдаемость и устойчивость. Неверный перевод `sound` исправлен в RU/EN промптах и карточке статуса.
