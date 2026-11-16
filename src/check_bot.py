"""Read-only Telegram Bot API credential and channel permission check."""
import os
import requests


def call(token: str, method: str, params: dict | None = None) -> dict:
    response = requests.get(
        "https://api.telegram.org/bot" + token + "/" + method,
        params=params, timeout=20,
    )
    response.raise_for_status()
    obj = response.json()
    if not obj.get("ok"):
        raise RuntimeError(method + ": " + str(obj.get("description", "unknown error")))
    return obj["result"]


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret or TELEGRAM_CHAT_ID variable")
    me = call(token, "getMe")
    info = call(token, "getChat", {"chat_id": chat})
    status = call(token, "getChatMember", {"chat_id": chat, "user_id": me["id"]})
    print("Bot username:", me.get("username"))
    print("Destination:", info.get("title"), info.get("username"))
    print("Bot member status:", status.get("status"))
    if (status.get("status") not in ("administrator", "creator") or
            (status.get("status") == "administrator" and
             not status.get("can_post_messages", False))):
        raise RuntimeError("Bot lacks administrator post permission for this channel")
    print("Telegram preflight OK. No messages were sent.")


if __name__ == "__main__":
    main()
