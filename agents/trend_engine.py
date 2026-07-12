import json
import os
from datetime import datetime

HISTORY_FILE = "data/intelligence/history.json"


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    with open(HISTORY_FILE, "r") as file:
        return json.load(file)


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

    with open(HISTORY_FILE, "w") as file:
        json.dump(history, file, indent=2)


def calculate_topic_scores(opportunities):
    scores = {}

    for item in opportunities:
        topic = item.get("topic", "General")
        score = item.get("score", 0)
        scores[topic] = scores.get(topic, 0) + score

    return scores


def save_daily_snapshot(intelligence):
    history = load_history()

    today = datetime.now().strftime("%Y-%m-%d")
    topic_scores = calculate_topic_scores(intelligence.get("opportunities", []))

    snapshot = {
        "date": today,
        "topic_scores": topic_scores,
    }

    history = [item for item in history if item.get("date") != today]
    history.append(snapshot)

    save_history(history)

    return snapshot


def compare_to_previous(snapshot):
    history = load_history()

    if len(history) < 2:
        return {
            "message": "Not enough history yet. Trend tracking starts after multiple reports.",
            "trends": []
        }

    previous = history[-2]
    current_scores = snapshot.get("topic_scores", {})
    previous_scores = previous.get("topic_scores", {})

    trends = []

    all_topics = set(current_scores.keys()) | set(previous_scores.keys())

    for topic in all_topics:
        current = current_scores.get(topic, 0)
        previous_value = previous_scores.get(topic, 0)
        change = current - previous_value

        if previous_value > 0:
            percent_change = round((change / previous_value) * 100, 1)
        else:
            percent_change = None

        trends.append({
            "topic": topic,
            "current_score": current,
            "previous_score": previous_value,
            "change": change,
            "percent_change": percent_change,
            "direction": "up" if change > 0 else "down" if change < 0 else "flat"
        })

    trends.sort(key=lambda x: abs(x["change"]), reverse=True)

    return {
        "message": "Trend comparison generated.",
        "trends": trends
    }
