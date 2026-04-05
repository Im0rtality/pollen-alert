"""Pushover notification client."""

import requests

PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def send(
    token: str,
    user_key: str,
    title: str,
    message: str,
    priority: int,
    url: str | None = None,
    url_title: str | None = None,
) -> None:
    data: dict[str, str] = {
        "token": token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": str(priority),
    }
    if url:
        data["url"] = url
    if url_title:
        data["url_title"] = url_title

    resp = requests.post(PUSHOVER_URL, data=data, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    if result.get("status") != 1:
        raise RuntimeError(f"Pushover error: {result}")
