# Домашнее задание 8. Мониторинг

Автор: Кузнецова Полина Глебовна
Курс: ML в продакшене, модуль 8

## Что сделано

Поднимала локально через docker-compose стек Prometheus + Grafana + ML-сервис на Flask. Отдельно: Evidently для дрифта, DQOps для качества данных, схема Kappa-архитектуры для VPP через библиотеку diagrams. Основной notebook лежит в корне, к нему по шагам собраны все артефакты

## Структура

```
hw8_monitoring/
├── HW8_Monitoring_Кузнецова_Полина.ipynb
├── docker-compose.yml
├── ml_service/
│   ├── app.py            # Flask сервис с эндпоинтом /metrics
│   ├── Dockerfile
│   └── requirements.txt
├── prometheus/
│   ├── prometheus.yml    # scrape_configs
│   └── alerts.yml        # 3 правила алертов
├── grafana/
│   ├── provisioning/datasources/datasources.yml
│   ├── provisioning/dashboards/dashboards.yml
│   └── dashboards/ml_service_dashboard.json
├── screenshots/
│   ├── grafana_dashboard.png
│   ├── grafana_alert.png
│   ├── prometheus_targets.png
│   └── dqops_incident.png
└── README.md
```

## SLO которые выбрала

Сервис рекомендаций онлайн-кинотеатра, основные показатели:

* Latency p95 < 1 сек
* Error rate (5xx) < 1 %
* Availability > 99 %

PromQL для p95:
```
histogram_quantile(0.95, sum(rate(request_latency_seconds_bucket{job="ml_service"}[5m])) by (le))
```

На каждый показатель прописан свой алерт в `prometheus/alerts.yml`: `HighLatencyP95`, `HighErrorRate`, `ServiceDown`

## Как запускать

```bash
git clone <repo>
cd hw8_monitoring
docker-compose up -d --build
```

Адреса после старта:

* ML-сервис: http://localhost:8000/recommend и http://localhost:8000/metrics
* Prometheus: http://localhost:9090 (вкладка Status → Targets, должны быть все UP)
* Grafana: http://localhost:3000, логин admin/admin, дашборд подгружается сам через provisioning

Чтобы посмотреть как срабатывает алерт, перезапустила ML-сервис с переменной SLOW=1, тогда к каждому ответу добавляется `time.sleep(2)` и через пару минут HighLatencyP95 уходит в FIRING

```bash
docker compose run -e SLOW=1 -p 8000:8000 ml_service
```

## По шагам

### Шаг 1. Дерево метрик

Разделила метрики на 4 ветки: бизнес (выручка, DAU, CTR, retention), приложение (RPS, latency p50/p95/p99, error rate), ML (hitrate@k, NDCG, дрифт, доля fallback) и инфра (CPU/RAM/GPU, network, up, состояние Postgres и Redis). Само дерево записала в Mermaid внутри notebook

Из всего этого выбрала на мониторинг одну метрику, `request_latency_seconds`, потому что она прямо отражает SLO p95 < 1 c

### Шаг 2. Prometheus + Grafana + ML-сервис

В `ml_service/app.py` повесила метрики через `prometheus_client`: Histogram для latency, Counter для http_requests_total, Gauge для inflight_requests и data_drift_share

`prometheus.yml` собирает метрики с ml_service каждые 5 секунд, с node_exporter и cadvisor каждые 15. Дашборд в Grafana показывает квантили latency, error rate, throughput по статусам, drift share и медианный скор модели. Отдельный indicator показывает что target ml_service: UP

Скрины: `screenshots/grafana_dashboard.png`, `screenshots/prometheus_targets.png`, `screenshots/grafana_alert.png`

### Шаг 3. Дрифт через Evidently

Сгенерировала 2 синтетических батча по 5000 строк. В reference аудитория средняя 32 года, смотрит немного, скоры модели Beta(2,5). В current "состарила" аудиторию до 41 года, увеличила watch_minutes, сместила распределение устройств в сторону smart_tv и подменила скоры на Beta(5,2)

DataDriftPreset поймал дрифт по всем 4 признакам, `share_of_drifted_columns = 1.0`. Это значение пушу как Prometheus-метрику `data_drift_share` и вывожу на дашборд

### Шаг 4. Data Quality Ops

Подняла DQOps, подключила локальный PostgreSQL, импортировала профиль таблицы `public.movie_ratings`. Дальше SQL-скриптом сломала качество данных:

1. Сняла NOT NULL с device, занулила каждую третью строку, отвалился чек `nulls_count`
2. Расширила тип rating и записала значения 99.99 (вне диапазона 0..10), чек `value_in_range`
3. Переименовала колонку `rated_at` в `created_at`, сработал `schema_change`
4. Продублировала 5000 строк, нарушение `duplicate_records`

На вкладке Incidents висят 4 OPEN инцидента: 2 со статусом error и 2 со статусом warning. Скрин: `screenshots/dqops_incident.png`

### Шаг 5. Схема ML-системы для Virtual Product Placement

Выбрала Kappa-архитектуру. Аргумент простой: на входе видеопоток в реальном времени, для онлайн-замены бренда задержка должна быть минимальной, разделение на батч и стрим только усложнило бы поддержку

Один стрим обрабатывает всё: дискриминативная сеть YOLO11 находит человека, SDXL + ControlNet дорисовывает логотип на футболке, composer склеивает кадр, готовые annotated_frames улетают через CDN зрителю

Параллельно идёт ветка ретрейна (на схеме пунктиром): сэмплируется 1% кадров в S3, раз в неделю job переобучает модели, веса публикуются в MLflow Registry, стрим-сервисы их подтягивают без даунтайма

Схема построена библиотекой `diagrams`, код в последней ячейке notebook, результат сохраняется в `vpp_kappa_architecture.png`
