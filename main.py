import json
import requests
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from flask import Flask, request
import os

# Получаем данные из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
APPLE_PUBLIC_KEY_URL_PROD = 'https://appleid.apple.com/auth/keys'  # для production
APPLE_PUBLIC_KEY_URL_SANDBOX = 'https://sandbox.itunes.apple.com/verifyReceipt'  # для sandbox

# Устанавливаем URL для отправки сообщения в Telegram
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Получаем публичные ключи Apple для проверки подписи
def get_apple_public_keys(environment):
    if environment == "sandbox":
        response = requests.get(APPLE_PUBLIC_KEY_URL_SANDBOX)
    else:
        response = requests.get(APPLE_PUBLIC_KEY_URL_PROD)
        
    if response.status_code == 200:
        return response.json()['keys']
    return None

# Функция для загрузки и десериализации публичного ключа
def load_public_key(pem_data):
    return serialization.load_pem_public_key(pem_data.encode(), backend=default_backend())

# Функция для проверки подписи
def verify_signature(data, signature, public_key):
    try:
        # Распаковываем base64-закодированные данные
        signature = base64.b64decode(signature)
        data = json.dumps(data).encode('utf-8')
        
        # Проверка подписи с помощью публичного ключа
        public_key.verify(
            signature,
            data,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        print(f"Ошибка при проверке подписи: {e}")
        return False

# Функция для извлечения данных из уведомления
def extract_purchase_data(notification_data):
    # Извлекаем необходимые поля
    auto_renew_status = notification_data.get("auto_renew_status", "Неизвестный статус")
    product_id = notification_data.get("product_id", "Неизвестный продукт")
    bundle_id = notification_data.get("bundle_id", "Неизвестный Bundle ID")
    version = notification_data.get("version", "Неизвестная версия")
    purchase_date = notification_data.get("purchase_date", "Неизвестная дата")
    
    return auto_renew_status, product_id, bundle_id, version, purchase_date

# Функция для отправки сообщения в Telegram
def send_telegram_message(message: str):
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'  # чтобы использовать форматирование Markdown
    }
    response = requests.post(TELEGRAM_API_URL, data=payload)
    return response.json()

# Создаем Flask приложение
app = Flask(__name__)

# Обработчик POST запроса с данными
@app.route('/apple-webhook', methods=['POST'])
def apple_webhook():
    try:
        # Получаем данные из запроса
        data = request.json
        print(f"Получены данные: {data}")  # Добавим логирование

        # Проверяем, что есть данные
        if 'signed_data' not in data:
            print("Нет поля 'signed_data' в запросе.")  # Логируем ошибку
            return "Нет данных для обработки", 400

        signed_data = data['signed_data']
        
        # Получаем информацию об окружении (production или sandbox)
        environment = data.get("environment", "production")

        # Получаем публичные ключи Apple
        public_keys = get_apple_public_keys(environment)
        if not public_keys:
            print("Не удалось получить публичные ключи Apple.")  # Логируем ошибку
            return "Не удалось получить публичные ключи Apple", 400

        # Для простоты возьмем первый ключ (можно улучшить обработку нескольких ключей)
        public_key = load_public_key(public_keys[0]['publicKey'])

        # Проверяем подпись уведомления
        if not verify_signature(signed_data['data'], signed_data['signature'], public_key):
            print("Подпись уведомления невалидна.")  # Логируем ошибку
            return "Подпись уведомления невалидна", 400

        # Извлекаем данные уведомления
        auto_renew_status, product_id, bundle_id, version, purchase_date = extract_purchase_data(signed_data['data'])

        # Формируем сообщение для отправки в Telegram
        message = f"""
> Изменён статус автообновления ({'отключил автообновление' if auto_renew_status == 'disabled' else 'включил автообновление'})
📦 Продукт: {product_id}
📱 Bundle ID: {bundle_id}
📦 Версия приложения: {version}
🕒 Дата покупки: {purchase_date}
        """
        
        # Отправляем сообщение в Telegram
        telegram_response = send_telegram_message(message)
        print(f"Ответ от Telegram: {telegram_response}")  # Логируем ответ от Telegram
        
        return "OK", 200

    except Exception as e:
        print(f"Произошла ошибка: {e}")  # Логируем исключения
        return str(e), 500

if __name__ == '__main__':
    # Используем динамический порт из переменной окружения
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
