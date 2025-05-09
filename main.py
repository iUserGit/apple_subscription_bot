import os
import json
import requests
from flask import Flask, request
from telegram import Bot
from datetime import datetime

# Получаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# URL для проверки чека (App Store)
APPLE_RECEIPT_URL = "https://sandbox.itunes.apple.com/verifyReceipt"  # Для теста, используйте продакшн URL для реальных покупок
# APPLE_RECEIPT_URL = "https://buy.itunes.apple.com/verifyReceipt"

# Инициализируем бота Telegram
bot = Bot(token=TELEGRAM_BOT_TOKEN)

app = Flask(__name__)

def verify_receipt(receipt_data):
    """
    Отправка чека в Apple для валидации
    """
    payload = {
        'receipt-data': receipt_data,
        'password': os.getenv('APPLE_SHARED_SECRET')  # Ваш shared secret
    }
    response = requests.post(APPLE_RECEIPT_URL, json=payload)
    
    # Получаем ответ от Apple
    if response.status_code == 200:
        result = response.json()
        if result.get('status') == 0:
            return result
        else:
            return None
    return None

@app.route('/appstore', methods=['POST'])
def appstore_notification():
    # Получаем данные уведомления от App Store
    data = request.json

    # Проверяем, что данные не пустые
    if not data:
        return 'No data received', 400

    # Извлекаем данные о чеке
    receipt_data = data.get('receipt-data')

    # Проводим валидацию чека через Apple
    receipt_verification = verify_receipt(receipt_data)
    
    if receipt_verification is None:
        return 'Receipt verification failed', 400

    # Извлекаем нужные данные из уведомления
    auto_renewal = data.get('auto_renewal', 'Не указано')
    product_id = data.get('product_id', 'Не указано')
    bundle_id = data.get('bundle_id', 'Не указано')
    app_version = data.get('app_version', 'Не указано')
    purchase_date = data.get('purchase_date', 'Не указано')

    # Форматируем дату, если она есть
    if purchase_date != 'Не указано':
        purchase_date = datetime.strptime(purchase_date, '%Y-%m-%dT%H:%M:%SZ').strftime('%d %B %Y, %H:%M')

    # Формируем сообщение для Telegram
    message = f"""
    > Изменён статус автообновления ({'отключил' if auto_renewal == 'false' else 'включил'} автообновление)
    📦 Продукт: {product_id}
    📱 Bundle ID: {bundle_id}
    📦 Версия приложения: {app_version}
    🕒 Дата покупки: {purchase_date}
    """

    # Отправляем сообщение в Telegram
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

    return 'Notification received', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
