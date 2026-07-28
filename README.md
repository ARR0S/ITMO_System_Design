# Автоматизация обработки тикетов поддержки

Минимальный Proof of Concept системы, которая классифицирует обращения
пользователей, определяет маршрут обработки, ищет релевантную инструкцию
в базе знаний и безопасно формирует автоматический ответ.

Система предназначена не для автоматического закрытия всех тикетов,
а для разгрузки операторов на типовых низкорисковых обращениях.
Высокорисковые, неизвестные и low-confidence обращения передаются человеку.
Отказ LLM не блокирует приём, классификацию и маршрутизацию тикетов,
а каждое итоговое решение сохраняется для аудита.

## Бизнес-задача

Сервис обрабатывает около 200 тысяч тикетов в день.
Во время инцидентов поток может возрастать до 10–20 тысяч обращений
за 10 минут.

Ручная обработка одного тикета занимает около 8 минут
и стоит в среднем 150 рублей. Около 40% обращений являются типовыми
или повторяющимися, поэтому их безопасная автоматизация потенциально
сокращает время первого ответа и нагрузку на операторов.

Основная цель решения — увеличить долю безопасно обработанных тикетов,
не ухудшая:

- CSAT;
- reopen rate;
- SLA первого ответа;
- безопасность пользователей;
- качество обработки высокорисковых обращений.

## Что демонстрирует PoC

PoC реализует три детерминированных сценария.

### 1. Happy path

Типовое низкорисковое обращение:

```text
Как отключить email-уведомления?
```

Система:

1. валидирует и сохраняет тикет;
2. проверяет и маскирует PII;
3. определяет категорию `notification_settings`;
4. направляет тикет в `general_support`;
5. находит инструкцию в локальной базе знаний;
6. вызывает mock LLM;
7. проверяет сформированный ответ;
8. возвращает:

```text
AUTO_ANSWER + AUTO_RESOLVED
```

### 2. High-risk path

Финансовое обращение:

```text
Верните деньги за неизвестное списание с моей карты.
```

Система определяет:

```text
category = payment_refund
team = billing_support
risk = HIGH
```

Даже при высокой уверенности классификатора тикет не закрывается
автоматически и получает:

```text
HUMAN_REVIEW + WAITING_FOR_HUMAN
```

Retrieval и LLM в этом сценарии не вызываются.

### 3. LLM failure

Низкорисковый тикет успешно классифицируется и маршрутизируется,
но mock LLM имитирует недоступность внешнего сервиса.

Система сохраняет тикет, категорию, маршрут и найденный источник,
после чего возвращает:

```text
ROUTE_ONLY + DEGRADED
```

Таким образом, LLM не является критической зависимостью
для основной обработки обращения.

## Быстрый запуск

### Требования

- Python 3.11 или новее;
- Git.

### Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Запуск тестов

```powershell
python -m pytest
```

Тесты проверяют:

- правила двух стадий `PolicyEngine`;
- приоритет high-risk над confidence;
- граничное значение confidence `0.80`;
- happy path;
- обязательный human review;
- degraded mode при отказе LLM;
- сохранность исходного тикета;
- идемпотентность повторной обработки.

### Запуск демонстрации

Исполняемая демонстрация PoC реализована в виде end-to-end тестов:

```powershell
python -m pytest tests/test_scenarios.py -v
```

## Архитектурный подход

Решение построено как модульный монолит с явными интерфейсами
заменяемых компонентов.

```text
Ticket
  ↓
Validation
  ↓
Save original ticket
  ↓
PII inspection
  ↓
Classification
  ↓
Policy Engine: eligibility gate
  ├─ unsafe / high-risk / low-confidence → HUMAN_REVIEW
  └─ eligible
       ↓
     Retrieval
       ↓
     Mock LLM
       ↓
     Output validation
       ↓
     Policy Engine: final decision
       ↓
     Result + Audit + Metrics
```

Ключевые принципы:

- classifier prediction отделён от бизнес-решения;
- confidence отделён от business risk;
- команда и риск определяются конфигурацией `CategoryPolicy`;
- Policy Engine не вызывает модели и внешние сервисы;
- тикет сохраняется до необязательного slow path;
- raw-текст не передаётся в audit storage;
- retrieval получает только текст после PII-проверки;
- неожиданные ошибки не скрываются под fallback;
- high-risk всегда требует участия оператора.

## Реализация PoC и production-дизайн

| Область | Реализовано в PoC | Целевая production-реализация |
|---|---|---|
| Архитектура | Модульный монолит | Web–Queue–Worker |
| Хранилище | In-memory repositories | Надёжная транзакционная БД |
| Очереди | Последовательный локальный вызов | Message broker, retries, DLQ |
| Классификация | Детерминированный mock | TF-IDF + Logistic Regression как baseline |
| Risk policy | Реальный Policy Engine | Версионируемые бизнес-правила |
| PII | Regex-baseline | Правила + специализированная NER-модель |
| Retrieval | Keyword matching | BM25 или hybrid retrieval |
| LLM | Детерминированный mock | Корпоративный gateway или локальная модель |
| Аудит | In-memory structured events | Централизованное защищённое хранилище |
| Метрики | Локальные счётчики | Prometheus, dashboards и alerts |
| Human review | In-memory review items | Интеграция с рабочим местом оператора |

PoC подтверждает data flow, safety-правила и degraded behavior,
но не является production-ready системой.

## Структура проекта

```text
.
├── src/
│   └── support_ticket_poc/
│       ├── models.py
│       ├── interfaces.py
│       ├── policy.py
│       ├── components.py
│       ├── repositories.py
│       ├── observability.py
│       ├── service.py
│       └── data/
│           └── knowledge_base.json
├── tests/
│   ├── test_policy.py
│   └── test_scenarios.py
├── docs/
│   ├── task_analysis.md
│   ├── architecture.md
│   ├── ml.md
│   ├── monitoring.md
│   └── risks-and-ops.md
├── AI_USAGE.md
├── SELF_REVIEW.md
├── AGENTS.md
├── pyproject.toml
└── README.md
```

## Что является реальной реализацией

В коде реализуются:

- доменные dataclasses и enums;
- контракты компонентов через `Protocol`;
- двухстадийный `PolicyEngine`;
- детерминированная валидация;
- regex-проверка PII;
- mock-классификатор;
- локальный keyword retriever;
- mock LLM с режимом отказа;
- output validator;
- in-memory repositories;
- review и audit events;
- локальные счётчики;
- orchestration service;
- end-to-end тесты;
- CLI-демонстрация.

## Что осталось на уровне архитектурного дизайна

Не реализуются:

- HTTP API;
- реальная многоканальная интеграция;
- PostgreSQL, Redis и message broker;
- асинхронные workers;
- retries, circuit breaker и DLQ;
- Transactional Outbox;
- production-grade PII detector;
- обучение и serving ML-модели;
- embeddings, vector search и reranker;
- настоящий внешний LLM;
- интерфейс оператора;
- production monitoring stack;
- model registry;
- drift pipeline;
- shadow и canary rollout.

## Основные допущения

- Confidence `0.80` используется только как демонстрационный порог.
- Keyword match является PoC-заменой полноценной retrieval-оценки.
- Mock-компоненты демонстрируют контракты и data flow,
  но не качество реальных ML-моделей.
- Неизвестная категория всегда передаётся оператору.
- High-risk категория не может быть автоматически закрыта.
- Входные сценарии PoC детерминированы.
- Production-пороги должны определяться на размеченных данных
  с учётом стоимости ошибок и доступной ёмкости операторов.

## Ограничения

- Regex не обеспечивает полное обнаружение PII.
- Keyword retrieval плохо обрабатывает сложные перефразирования.
- Mock classifier не измеряет реальное качество классификации.
- Mock LLM не моделирует галлюцинации production-моделей.
- In-memory storage не переживает перезапуск процесса.
- PoC не подтверждает работу под production-нагрузкой.
- Экономический эффект требует проверки на пилотном трафике.

## Документация

- [`docs/task_analysis.md`](docs/task_analysis.md) — требования, scope и assumptions;
- [`docs/architecture.md`](docs/architecture.md) — целевая архитектура и data flow;
- [`docs/ml.md`](docs/ml.md) — ML/LLM-дизайн, данные и валидация;
- [`docs/monitoring.md`](docs/monitoring.md) — метрики, drift и алерты;
- [`docs/risks-and-ops.md`](docs/risks-and-ops.md) — ключевые эксплуатационные и safety-риски;
- [`AI_USAGE.md`](AI_USAGE.md) — журнал использования AI;
- [`SELF_REVIEW.md`](SELF_REVIEW.md) — самооценка решения и production gaps.