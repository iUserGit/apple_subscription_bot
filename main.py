import json
import requests
import base64
import os
from flask import Flask, request
from jose import jwk
from jose.utils import base64url_decode

# Получаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
APPLE_PUBLIC_KEY_URL_PROD = 'https://appleid.apple.com/auth/keys'
APPLE_PUBLIC_KEY_URL_SANDBOX = 'https://appleid.apple.com/auth/keys'

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

app = Flask(__name__)

def get_apple_public_keys(environment):
    url = APPLE_PUBLIC_KEY_URL_SANDBOX if environment == "sandbox" else APPLE_PUBLIC_KEY_URL_PROD
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('keys', [])
    return []

def load_jwk_key(key_data):
    try:
        return jwk.construct(key_data)
    except Exception as e:
        print(f"Ошибка при разборе JWK: {e}")
        return None

def verify_signature(payload: dict, signature: str, key_data: dict) -> bool:
    key = load_jwk_key(key_data)
    if not key:
        return False

    try:
        decoded_signature = base64url_decode(signature.encode())
        message = json.dumps(payload, separators=(',', ':')).encode('utf-8')

        if key.verify(message, decoded_signature):
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
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    response = requests.post(TELEGRAM_API_URL, data=payload)
    return response.json()

@app.route('/apple-webhook', methods=['POST'])
def apple_webhook():
    data = request.json

    if 'signed_data' not in data:
        return json.dumps({"error": "Нет signed_data"}), 400

    signed_data = data['signed_data']
    environment = data.get("environment", "production")

    public_keys = get_apple_public_keys(environment)
    if not public_keys:
        return json.dumps({"error": "Не удалось получить публичные ключи"}), 400

    # Берем первый ключ (можно улучшить, проверяя по 'kid' заголовку JWT)
    if not verify_signature(signed_data['data'], signed_data['signature'], public_keys[0]):
        return json.dumps({"error": "Подпись не прошла проверку"}), 400

    auto_renew_status, product_id, bundle_id, version, purchase_date = extract_purchase_data(signed_data['data'])

    message = f"""
> Изменён статус автообновления ({'отключил автообновление' if auto_renew_status == 'disabled' else 'включил автообновление'})
📦 Продукт: {product_id}
📱 Bundle ID: {bundle_id}
📦 Версия приложения: {version}
🕒 Дата покупки: {purchase_date}
    """
    send_telegram_message(message)
    return "OK", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
