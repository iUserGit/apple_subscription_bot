import json
import base64
import os
import requests

from fastapi import FastAPI, Request
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

app = FastAPI()

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
APPLE_PUBLIC_KEY_URL_PROD = "https://appleid.apple.com/auth/keys"
APPLE_PUBLIC_KEY_URL_SANDBOX = "https://sandbox.itunes.apple.com/verifyReceipt"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def get_apple_public_keys(environment):
    url = APPLE_PUBLIC_KEY_URL_SANDBOX if environment == "sandbox" else APPLE_PUBLIC_KEY_URL_PROD
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get("keys", [])
    return []


def load_public_key(pem_data):
    return serialization.load_pem_public_key(pem_data.encode(), backend=default_backend())


def verify_signature(data, signature, public_key):
    try:
        signature_bytes = base64.b64decode(signature)
        data_bytes = json.dumps(data).encode("utf-8")
        public_key.verify(
            signature_bytes,
            data_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        print(f"Ошибка при проверке подписи: {e}")
        return False


def extract_purchase_data(notification_data):
    return (
        notification_data.get("auto_renew_status", "Неизвестный статус"),
        notification_data.get("product_id", "Неизвестный продукт"),
        notification_data.get("bundle_id", "Неизвестный Bundle ID"),
        notification_data.get("version", "Неизвестная версия"),
        notification_data.get("purchase_date", "Неизвестная дата")
    )


def send_telegram_message(message: str):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(TELEGRAM_API_URL, data=payload)


@app.post("/apple-webhook")
async def apple_webhook(request: Request):
    data = await request.json()

    if "signed_data" not in data:
        return {"error": "Нет данных для обработки"}, 400

    signed_data = data["signed_data"]
    environment = data.get("environment", "production")

    public_keys = get_apple_public_keys(environment)
    if not public_keys:
        return {"error": "Не удалось получить публичные ключи Apple"}, 400

    try:
        public_key = load_public_key(public_keys[0]["publicKey"])
    except Exception as e:
        return {"error": f"Ошибка загрузки публичного ключа: {str(e)}"}, 400

    if not verify_signature(signed_data["data"], signed_data["signature"], public_key):
        return {"error": "Подпись уведомления невалидна"}, 400

    auto_renew_status, product_id, bundle_id, version, purchase_date = extract_purchase_data(signed_data["data"])

    message = f"""
📬 Изменён статус автообновления: *{'отключил' if auto_renew_status == 'disabled' else 'включил'}*
📦 Продукт: `{product_id}`
📱 Bundle ID: `{bundle_id}`
📦 Версия приложения: `{version}`
🕒 Дата покупки: `{purchase_date}`
"""

    send_telegram_message(message)
    return {"status": "ok"}
