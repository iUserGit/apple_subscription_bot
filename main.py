import os
import json
from fastapi import FastAPI, Request
import httpx
from jose import jwt
from datetime import datetime, timezone

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

notification_map = {
    "DID_CHANGE_RENEWAL_PREF": "Пользователь изменил подписку",
    "DID_RENEW": "Подписка успешно продлена",
    "CANCEL": "Подписка отменена",
    "INITIAL_BUY": "Первая покупка подписки",
    "DID_FAIL_TO_RENEW": "Не удалось продлить подписку",
    "DID_RECOVER": "Подписка восстановлена",
    "DID_CHANGE_RENEWAL_STATUS": "Изменён статус автообновления",
    "REFUND": "Произведён возврат",
}

subtype_map = {
    "DOWNGRADE": "понизил уровень",
    "UPGRADE": "повысил уровень",
    "AUTO_RENEW_ENABLED": "включил автообновление",
    "AUTO_RENEW_DISABLED": "отключил автообновление",
    "VOLUNTARY": "отменил вручную",
}

def format_date(ms_timestamp: str) -> str:
    try:
        ts = int(ms_timestamp) / 1000  # из миллисекунд в секунды
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d %B %Y, %H:%M UTC")
    except Exception:
        return "неизвестна"

@app.post("/apple_webhook")
async def apple_webhook(request: Request):
    payload = await request.json()

    signed_payload = payload.get("signedPayload")
    if not signed_payload:
        await send_telegram_message("⚠️ Получен запрос без signedPayload")
        return {"status": "ignored"}

    try:
        decoded_payload = jwt.get_unverified_claims(signed_payload)

        notification_type = decoded_payload.get("notificationType", "UNKNOWN")
        subtype = decoded_payload.get("subtype", "NONE")

        data = decoded_payload.get("data", {})
        product_id = data.get("productId", "N/A")
        bundle_id = data.get("bundleId", "N/A")
        bundle_version = data.get("bundleVersion", "N/A")
        purchase_date_raw = data.get("purchaseDate", None)
        purchase_date = format_date(purchase_date_raw) if purchase_date_raw else "не указана"

        readable_type = notification_map.get(notification_type, notification_type)
        readable_subtype = subtype_map.get(subtype, subtype)

        message = (
            f"📬 {readable_type}"
            + (f" ({readable_subtype})" if readable_subtype else "") + "\n\n"
            f"📦 Продукт: {product_id}\n"
            f"📱 Bundle ID: {bundle_id}\n"
            f"📦 Версия приложения: {bundle_version}\n"
            f"🕒 Дата покупки: {purchase_date}"
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
