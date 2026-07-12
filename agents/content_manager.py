import json
import os

BACKLOG_FILE = "data/content/content_backlog.json"


def load_content_backlog():
    if not os.path.exists(BACKLOG_FILE):
        return []

    with open(BACKLOG_FILE, "r") as file:
        return json.load(file)


def save_content_backlog(backlog):
    os.makedirs(os.path.dirname(BACKLOG_FILE), exist_ok=True)

    with open(BACKLOG_FILE, "w") as file:
        json.dump(backlog, file, indent=2)


def get_next_content_actions(limit=5):
    backlog = load_content_backlog()

    open_items = [
        item for item in backlog
        if item.get("status") not in ["completed", "done"]
    ]

    open_items.sort(
        key=lambda item: item.get("priority", 0),
        reverse=True
    )

    return open_items[:limit]


def mark_content_status(content_id, status):
    backlog = load_content_backlog()

    for item in backlog:
        if item.get("id") == content_id:
            item["status"] = status
            save_content_backlog(backlog)
            return item

    raise ValueError(f"No content item found with id: {content_id}")
