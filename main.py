import os
import json
from fastapi import FastAPI, Request
import httpx
from jose import jwt, jwk
from jose.utils import base64url_decode
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

APPLE_JWKS_URLS = {
    "Sandbox": "https://api.storekit-sandbox.itunes.apple.com/in-app-purchase/v1/jwsPublicKeys",
    "Production": "https://api.storekit.itunes.apple.com/in-app-purchase/v1/jwsPublicKeys"
}

jwks_cache = {}

def format_date(ms_timestamp: str) -> str:
    try:
        ts = int(ms_timestamp) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d %B %Y, %H:%M UTC")
    except Exception:
        return "неизвестна"

async def fetch_jwks(environment: str):
    if environment not in jwks_cache:
        async with httpx.AsyncClient() as client:
            resp = await client.get(APPLE_JWKS_URLS[environment])
            resp.raise_for_status()
            jwks_cache[environment] = resp.json()
    return jwks_cache[environment]

@app.post("/apple-webhook")
async def apple_webhook(request: Request):
    payload = await request.json()
    print(f"Полученный запрос: {json.dumps(payload, indent=2)}")

    signed_payload = payload.get("signedPayload")
    if not signed_payload:
        await send_telegram_message("⚠️ Получен запрос без signedPayload")
        return {"status": "ignored"}

    try:
        # Распаковка заголовка, чтобы извлечь 'kid'
        header_segment = signed_payload.split(".")[0]
        header_bytes = base64url_decode(header_segment.encode() + b'=' * (-len(header_segment) % 4))
        header = json.loads(header_bytes)
        kid = header["kid"]

        # Получаем среду (Sandbox или Production) из payload без проверки подписи
        decoded_claims = jwt.get_unverified_claims(signed_payload)
        environment = decoded_claims.get("environment", "Production")

        jwks = await fetch_jwks(environment)

        key_data = next((key for key in jwks["keys"] if key["kid"] == kid), None)
        if not key_data:
            raise ValueError(f"Ключ с kid={kid} не найден в JWKS")

        public_key = jwk.construct(key_data)
        message, encoded_sig = signed_payload.rsplit('.', 1)
        decoded_sig = base64url_decode(encoded_sig.encode())

        if not public_key.verify(message.encode(), decoded_sig):
            raise ValueError("Подпись JWT недействительна")

        # Теперь можно использовать проверенный payload
        data = decoded_claims.get("data", {})
        notification_type = decoded_claims.get("notificationType", "UNKNOWN")
        subtype = decoded_claims.get("subtype", "NONE")

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
        await send_telegram_message(f"❌ Ошибка при обработке payload: {str(e)}")

    return {"status": "processed"}

async def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)
