from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    requests.post(url, data=payload)

@app.post("/apple-webhook")
async def apple_webhook(request: Request):
    data = await request.json()
    notification_type = data.get("notificationType", "unknown")
    subtype = data.get("subtype", "none")

    message = f"📬 New message from Apple:\Type: {notification_type}\nSubtype: {subtype}"
    send_telegram_message(message)

    return {"status": "ok"}
