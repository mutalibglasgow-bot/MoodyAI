import os
import json
from datetime import datetime

from agents.sensors.followupboss_sensor import FollowUpBossSensor
from agents.sensors.search_console_sensor import SearchConsoleSensor
from agents.sensors.bsw_sensor import BSWSensor
from agents.sensors.tedc_sensor import TEDCSensor
from agents.history_engine import save_sensor_snapshot, save_all_trends


SENSORS = [
    FollowUpBossSensor(),
    SearchConsoleSensor(),
    BSWSensor(),
    TEDCSensor(),
]


def normalize_score(score):
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 0

    if score < 0:
        return 0

    if score > 100:
        return 100

    return int(round(score))


def normalize_signal(signal):
    signal.business_value_score = normalize_score(signal.business_value_score)

    try:
        signal.confidence = float(signal.confidence)
    except (TypeError, ValueError):
        signal.confidence = 0.0

    if signal.confidence > 1:
        signal.confidence = signal.confidence / 100

    if signal.confidence < 0:
        signal.confidence = 0.0

    if signal.confidence > 1:
        signal.confidence = 1.0

    return signal


def dedupe_signals(signals):
    seen = set()
    unique = []

    for signal in signals:
        key = (
            signal.signal_name.strip().lower(),
            signal.signal_type.strip().lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(signal)

    return unique


def collect_all_signals():
    all_signals = []
    sensor_names = []

    for sensor in SENSORS:
        print(f"Running sensor: {sensor.name}")

        try:
            signals = sensor.collect()
            signals = [normalize_signal(signal) for signal in signals]

            save_sensor_snapshot(sensor.name, signals)
            sensor_names.append(sensor.name)

            all_signals.extend(signals)

            print(f"  Found {len(signals)} signals.")
        except Exception as e:
            print(f"  ERROR in {sensor.name}: {e}")

    all_signals = dedupe_signals(all_signals)

    all_signals.sort(
        key=lambda signal: (
            signal.business_value_score,
            signal.confidence,
        ),
        reverse=True,
    )

    trends = save_all_trends(sensor_names)

    return all_signals, trends


def save_signals(signals, trends):
    os.makedirs("data/signals", exist_ok=True)

    output = {
        "generated_at": datetime.now().isoformat(),
        "signal_count": len(signals),
        "signals": [signal.to_dict() for signal in signals],
        "trend_summary": trends,
    }

    latest_path = "data/signals/latest_signals.json"
    dated_path = f"data/signals/signals_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"

    with open(latest_path, "w") as file:
        json.dump(output, file, indent=2)

    with open(dated_path, "w") as file:
        json.dump(output, file, indent=2)

    return latest_path, dated_path


def main():
    print("Collecting signals from sensors...\n")

    signals, trends = collect_all_signals()

    print("\nTODAY'S SIGNALS")
    print("=" * 50)

    for i, signal in enumerate(signals, start=1):
        print(f"\n{i}. {signal.signal_name}")
        print(f"   Type: {signal.signal_type}")
        print(f"   Source: {signal.source}")
        print(f"   Value Score: {signal.business_value_score}")
        print(f"   Confidence: {signal.confidence}")
        print(f"   Summary: {signal.summary}")

    print("\nTREND SUMMARY")
    print("=" * 50)

    for trend in trends.get("trends", []):
        print(f"\n{trend.get('sensor_name')}")
        print(f"   Momentum: {trend.get('momentum')}")
        print(f"   Latest Count: {trend.get('latest_signal_count')}")
        print(f"   7-Day Avg Count: {trend.get('seven_day_average_signal_count')}")
        print(f"   30-Day Avg Count: {trend.get('thirty_day_average_signal_count')}")
        print(f"   Latest Avg Score: {trend.get('latest_average_score')}")
        print(f"   7-Day Avg Score: {trend.get('seven_day_average_score')}")
        print(f"   30-Day Avg Score: {trend.get('thirty_day_average_score')}")

    latest_path, dated_path = save_signals(signals, trends)

    print(f"\nSaved latest signals to: {latest_path}")
    print(f"Saved dated signals to: {dated_path}")
    print("Saved latest trends to: data/history/latest_trends.json")


if __name__ == "__main__":
    main()