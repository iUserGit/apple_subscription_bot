import os
import json
import telegram
import asyncio
from quart import Quart, request, jsonify
import jwt
from jwt.exceptions import InvalidSignatureError

app = Quart(__name__)

# Получаем ключи из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
APPLE_SHARED_SECRET = os.getenv('APPLE_SHARED_SECRET')

# Создаем экземпляр бота Telegram
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

@app.route('/apple_webhook', methods=['POST'])
async def apple_webhook():
    data = await request.get_json()

    if not data or 'signedPayload' not in data:
        app.logger.error("No signedPayload provided.")
        return jsonify({'error': 'No signedPayload'}), 400

    signed_payload = data['signedPayload']

    try:
        # Расшифровка JWT-подписи от Apple
        decoded = jwt.decode(
            signed_payload,
            APPLE_SHARED_SECRET,
            algorithms=['HS256'],
            options={"verify_exp": False}  # Отключаем проверку срока действия
        )
        app.logger.info(f"Decoded payload: {json.dumps(decoded, indent=2)}")
    except InvalidSignatureError:
        app.logger.error("Invalid signature from Apple.")
        return jsonify({'error': 'Invalid signature'}), 400
    except Exception as e:
        app.logger.error(f"JWT decode error: {e}")
        return jsonify({'error': 'JWT decode error'}), 400

    # Извлечение полезных данных из расшифрованного payload
    notification_type = decoded.get("notificationType", "Неизвестный тип")
    subtype = decoded.get("subtype", "")
    data_object = decoded.get("data", {})
    product_id = data_object.get("productId", "Неизвестный продукт")
    bundle_id = data_object.get("bundleId", "Неизвестный Bundle ID")
    purchase_date = data_object.get("purchaseDate", "Неизвестная дата")

    message = (
        f"📩 Уведомление от Apple: {notification_type} {f'({subtype})' if subtype else ''}\n"
        f"📦 Продукт: {product_id}\n"
        f"📱 Bundle ID: {bundle_id}\n"
        f"🕒 Дата покупки: {purchase_date}"
    )

    app.logger.info(f"Sending message to Telegram: {message}")

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        app.logger.info("Message sent to Telegram successfully.")
    except Exception as e:
        app.logger.error(f"Failed to send message to Telegram: {e}")

    return jsonify({'status': 'success'}), 200

@app.route('/', methods=['GET'])
async def root():
    return jsonify({"status": "running"}), 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
