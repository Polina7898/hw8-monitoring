"""
Минимальный ML-сервис для домашки HW8
Эмулирует рекомендательный сервис для онлайн-кинотеатра
и выставляет /metrics для Prometheus
"""
import os
import random
import time

from flask import Flask, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

app = Flask(__name__)

# === Метрики ===
LATENCY = Histogram(
    "request_latency_seconds",
    "Время отклика ML-сервиса",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)
REQUESTS = Counter(
    "http_requests_total",
    "Количество HTTP запросов",
    ["method", "endpoint", "status"],
)
INFLIGHT = Gauge(
    "inflight_requests",
    "Запросы в обработке",
)
MODEL_SCORE = Histogram(
    "model_prediction_score",
    "Распределение скоров модели",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
DRIFT_GAUGE = Gauge(
    "data_drift_share",
    "Доля признаков с дрифтом по последнему отчету Evidently",
)

# Эмулируем «деградацию»: после флага SLOW=1 сервис искусственно тормозит
SLOW_MODE = os.getenv("SLOW", "0") == "1"


@app.route("/recommend", methods=["GET"])
def recommend():
    INFLIGHT.inc()
    start = time.time()
    try:
        # имитация работы модели
        base = random.uniform(0.02, 0.2)
        if SLOW_MODE:
            base += 2.0  # принудительно превышаем SLO
        time.sleep(base)

        score = random.betavariate(2, 5)
        MODEL_SCORE.observe(score)

        status = "200"
        if random.random() < 0.005:
            status = "500"

        REQUESTS.labels("GET", "/recommend", status).inc()
        return jsonify({"movie_id": random.randint(1, 1000), "score": score}), int(status)
    finally:
        LATENCY.observe(time.time() - start)
        INFLIGHT.dec()


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
