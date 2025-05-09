import os
import json
import httpx
from fastapi import FastAPI, Request
from jose import jwt
from jose.exceptions import JWTError
from datetime import datetime, timezone

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
APPLE_JWKS_URL = os.getenv("APPLE_JWKS_URL", "https://api.storekit.itunes.apple.com/in-app/v1/jwsPublicKeys")

# === MAPS OMITTED HERE for brevity ===
# notification_map and subtype_map оставим как у тебя

def format_date(ms_timestamp: str) -> str:
    try:
        ts = int(ms_timestamp) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d %B %Y, %H:%M UTC")
    except Exception:
        return "неизвестна"

async def fetch_apple_public_key(kid: str, alg: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(APPLE_JWKS_URL)
        keys = response.json().get("keys", [])
        for key in keys:
            if key["kid"] == kid and key["alg"] == alg:
                return key
    raise ValueError("Публичный ключ не найден для kid=" + kid)

@app.post("/apple-webhook")
async def apple_webhook(request: Request):
    payload = await request.json()
    print(f"Полученный запрос: {json.dumps(payload, indent=2)}")

    signed_payload = payload.get("signedPayload")
    if not signed_payload:
        await send_telegram_message("⚠️ Получен запрос без signedPayload")
        return {"status": "ignored"}

    try:
        # Получаем заголовки JWT
        headers = jwt.get_unverified_header(signed_payload)
        kid = headers["kid"]
        alg = headers["alg"]

        # Получаем публичный ключ Apple по kid
        public_key_jwk = await fetch_apple_public_key(kid, alg)

        # Декодируем JWT с проверкой подписи
        decoded_payload = jwt.decode(
            signed_payload,
            key=public_key_jwk,
            algorithms=[alg],
            options={"verify_aud": False}  # Обычно аудитория не используется
        )

        print(f"✅ Подпись подтверждена. Payload: {json.dumps(decoded_payload, indent=2)}")

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

    except JWTError as e:
        await send_telegram_message(f"❌ Ошибка валидации JWT: {str(e)}")
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
