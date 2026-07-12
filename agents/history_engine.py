import os
import json
from datetime import datetime, timedelta
from pathlib import Path


HISTORY_ROOT = Path("data/history")


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def load_json(path):
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r") as file:
            return json.load(file)
    except Exception:
        return None


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w") as file:
        json.dump(data, file, indent=2)


def save_sensor_snapshot(sensor_name, signals):
    safe_name = sensor_name.lower().replace(" ", "_").replace("/", "_")
    folder = HISTORY_ROOT / safe_name
    path = folder / f"{today_key()}.json"

    snapshot = {
        "date": today_key(),
        "sensor_name": sensor_name,
        "signal_count": len(signals),
        "average_score": average_score(signals),
        "signals": [signal.to_dict() for signal in signals],
    }

    save_json(path, snapshot)
    return str(path)


def average_score(signals):
    if not signals:
        return 0

    scores = [signal.business_value_score for signal in signals]
    return round(sum(scores) / len(scores), 2)


def load_history(sensor_name, days=30):
    safe_name = sensor_name.lower().replace(" ", "_").replace("/", "_")
    folder = HISTORY_ROOT / safe_name

    results = []

    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        path = folder / f"{date.strftime('%Y-%m-%d')}.json"
        data = load_json(path)

        if data:
            results.append(data)

    return list(reversed(results))


def percent_change(current, previous):
    if previous in [0, None]:
        return None

    return round(((current - previous) / previous) * 100, 2)


def build_trend_summary(sensor_name):
    history_30 = load_history(sensor_name, days=30)

    if not history_30:
        return {
            "sensor_name": sensor_name,
            "status": "No history yet",
        }

    latest = history_30[-1]

    last_7 = history_30[-7:]
    last_30 = history_30[-30:]

    latest_count = latest.get("signal_count", 0)
    latest_score = latest.get("average_score", 0)

    avg_7_count = round(sum(item.get("signal_count", 0) for item in last_7) / len(last_7), 2)
    avg_30_count = round(sum(item.get("signal_count", 0) for item in last_30) / len(last_30), 2)

    avg_7_score = round(sum(item.get("average_score", 0) for item in last_7) / len(last_7), 2)
    avg_30_score = round(sum(item.get("average_score", 0) for item in last_30) / len(last_30), 2)

    yesterday = history_30[-2] if len(history_30) >= 2 else None

    return {
        "sensor_name": sensor_name,
        "latest_date": latest.get("date"),
        "latest_signal_count": latest_count,
        "latest_average_score": latest_score,
        "yesterday_signal_count": yesterday.get("signal_count") if yesterday else None,
        "yesterday_average_score": yesterday.get("average_score") if yesterday else None,
        "one_day_signal_change_percent": percent_change(
            latest_count,
            yesterday.get("signal_count") if yesterday else None,
        ),
        "one_day_score_change_percent": percent_change(
            latest_score,
            yesterday.get("average_score") if yesterday else None,
        ),
        "seven_day_average_signal_count": avg_7_count,
        "thirty_day_average_signal_count": avg_30_count,
        "seven_day_average_score": avg_7_score,
        "thirty_day_average_score": avg_30_score,
        "momentum": calculate_momentum(latest_score, avg_7_score, avg_30_score),
    }


def calculate_momentum(latest, avg_7, avg_30):
    if latest > avg_7 > avg_30:
        return "Accelerating"

    if latest > avg_7:
        return "Improving"

    if latest < avg_7 < avg_30:
        return "Cooling"

    if latest < avg_7:
        return "Softening"

    return "Stable"


def save_all_trends(sensor_names):
    trends = [build_trend_summary(name) for name in sensor_names]

    output = {
        "generated_at": datetime.now().isoformat(),
        "trends": trends,
    }

    save_json("data/history/latest_trends.json", output)

    return output