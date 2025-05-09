import os
import json
import base64
import hashlib
import hmac
import telegram
import asyncio
from quart import Quart, request, jsonify
import jwt
from jwt.exceptions import InvalidTokenError

app = Quart(__name__)

# Получаем ключи из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
APPLE_SHARED_SECRET = os.getenv('APPLE_SHARED_SECRET')

# Создаем экземпляр бота Telegram
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

def verify_apple_signature(payload, signature):
    """
    Функция для верификации подписи данных, полученных от Apple.
    """
    try:
        # Расшифровка подписи с использованием APPLE_SHARED_SECRET
        decoded_signature = base64.b64decode(signature)
        
        # Хешируем полученные данные с использованием APPLE_SHARED_SECRET
        expected_signature = hmac.new(APPLE_SHARED_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        
        # Сравниваем вычисленную подпись с полученной
        if decoded_signature == expected_signature:
            return True
        else:
            app.logger.error("Calculated signature does not match received signature")
            return False
    except Exception as e:
        app.logger.error(f"Ошибка при верификации подписи: {e}")
        return False

@app.route('/apple_webhook', methods=['POST'])
async def apple_webhook():
   data = await request.get_json()  # Получаем данные из POST-запроса асинхронно

    # Логируем полученные данные
    app.logger.info(f"Received data: {data}")

    if not data:
        app.logger.error('No data received!')
        return jsonify({'error': 'No data received'}), 400

    # Извлекаем и проверяем подпись
    payload = json.dumps(data.get('payload'))
    signature = data.get('signature')

    # Логирование полученной подписи и данных для отладки
    app.logger.info(f"Received signature: {signature}")
    app.logger.info(f"Payload for signature verification: {payload}")

    if not signature or not verify_apple_signature(payload, signature):
        app.logger.error("Invalid signature from Apple.")
        return jsonify({'error': 'Invalid signature'}), 400

    # Пример получения данных из payload
    product = data.get('product_id', 'Неизвестный продукт')
    bundle_id = data.get('bundle_id', 'Неизвестный Bundle ID')
    version = data.get('version', 'Неизвестная версия')
    purchase_date = data.get('purchase_date', 'Неизвестная дата покупки')

    message = (
        f"> Изменён статус автообновления\n"
        f"📦 Продукт: {product}\n"
        f"📱 Bundle ID: {bundle_id}\n"
        f"📦 Версия приложения: {version}\n"
        f"🕒 Дата покупки: {purchase_date}"
    )

    # Логируем сообщение, которое отправляем в Telegram
    app.logger.info(f"Sending message to Telegram: {message}")

    try:
        # Асинхронная отправка сообщения в Telegram
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        app.logger.info('Message sent to Telegram successfully.')
    except Exception as e:
        app.logger.error(f"Failed to send message to Telegram: {e}")

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    # Получаем порт из переменной окружения или по умолчанию 5000
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
