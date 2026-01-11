import json
import os
import requests # Replaced aiohttp with requests
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN set in the .env file or environment variables")

API_URL = os.getenv("RAP_API_URL")

bot = Bot(token=BOT_TOKEN)
app = ApplicationBuilder().token(BOT_TOKEN).build()

def format_string(s):
    lines = s.split('\n')
    formatted_lines = [line.strip() for line in lines]
    return '\n'.join(formatted_lines)

async def send_rap_request(update: Update):
    await update.message.reply_text("🎤 Начинаю генерацию рэп-текста...")
    await update.message.reply_text("⏳ Подождите 10-30 секунд, создаю seed-слова и пишу рэп...")
    json_data = {
        "artist_name": f"{update.message.from_user.username or update.message.from_user.first_name}",
        "invite_code": "SECRET123"
    }
    try:
        # Synchronous request using the 'requests' library, similar to predictbot.py
        response = requests.post(API_URL, json=json_data, timeout=240)
        response.raise_for_status()
        data = response.json() # Parse JSON data from the synchronous response object

        await update.message.reply_text("🔥 Рэп готов!")
        seed_info = f"🌱 *Seed-слова (основа сюжета):*\n`{data['seed_words']}`"
        await update.message.reply_text(seed_info, parse_mode='Markdown')
        await update.message.reply_text("📝 *Рэп-текст:*", parse_mode='Markdown')
        rap_text = data['rap_text']
        message_limit = 4096
        message_chunks = [rap_text[i:i + message_limit] for i in range(0, len(rap_text), message_limit)]
        for chunk in message_chunks:
            await update.message.reply_text(chunk)
    except requests.RequestException as e: # Change exception type for 'requests' library errors
        await update.message.reply_text(f"❌ Ошибка при генерации: {str(e)}")
    #except Exception as e:
     #   await update.message.reply_text(f"❌ Неожиданная ошибка: {str(e)}")

async def start_command(update: Update, context):
    welcome_message = """
🎤 *Добро пожаловать в Рэп-Генератор!*

Этот бот создаёт уникальные рэп-тексты на русском языке, используя seed-слова (мнемонические фразы) как основу сюжета.

*Как использовать:*
Просто отправьте команду /rap и получите свой уникальный рэп-текст!

*Что такое seed-слова?*
Это специальные слова, которые становятся основой сюжета вашего рэпа. Каждый раз генерируются новые слова, а значит - новая история!

Готов? Отправь /rap и получи свой рэп! 🔥
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def rap_command(update: Update, context):
    await send_rap_request(update)

def main():
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('rap', rap_command))
    print("🎤 Рэп-бот запущен и готов к работе!")
    app.run_polling()

if __name__ == '__main__':
    main()