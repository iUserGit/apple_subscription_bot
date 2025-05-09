import os
import json
import base64
from fastapi import FastAPI, Request
import httpx
from jose import jwt  # pip install python-jose

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

@app.post("/apple-webhook")
async def apple_webhook(request: Request):
    payload = await request.json()

    # Берём JWT из поля signedPayload
    signed_payload = payload.get("signedPayload")
    if not signed_payload:
        await send_telegram_message("⚠️ Получен запрос без signedPayload")
        return {"status": "ignored"}

    try:
        # Декодируем JWT без проверки подписи (Apple её подписывает, но проверка не обязательна на этом этапе)
        decoded_payload = jwt.get_unverified_claims(signed_payload)

        notification_type = decoded_payload.get("notificationType", "UNKNOWN")
        subtype = decoded_payload.get("subtype", "NONE")
        product_id = decoded_payload.get("data", {}).get("productId", "N/A")

        message = (
            f"📬 Уведомление от Apple:\n"
            f"Событие: {notification_type}\n"
            f"Подтип: {subtype}\n"
            f"Продукт: {product_id}"
        )
        await send_telegram_message(message)
    except Exception as e:
        await send_telegram_message(f"❌ Ошибка при декодировании payload: {str(e)}")

    return {"status": "processed"}

async def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }

    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
