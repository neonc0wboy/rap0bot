import os
import time
import secrets
import requests
import errno
import logging
import io
import re
from flask import Flask, request, jsonify, render_template, send_file
from mnemonic import Mnemonic
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter, Retry
from gtts import gTTS
from pydub import AudioSegment
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
app.json.ensure_ascii = False
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
CORS(app)
GOOGLE_API_KEY = 'AIzaSyA2wjcAQMSPwqV-7ne4y71u_7NoQqmXjmU' #os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("No GOOGLE_API_KEY set in the .env file or environment variables")

# Конфигурация моделей
# Сначала пробуем качественную, если ошибка/таймаут — быструю
PRIMARY_MODEL = "gemini-2.0-flash"
FALLBACK_MODEL = "gemini-3.0-pro"

VALID_INVITE_CODES = {"SECRET123", "MAGIC_KEY", "COWBOY_CODE"}

RAP_PROMPT_TEMPLATE_RU = """Напиши рэп-текст на русском языке.

Используй следующие seed-слова как основу сюжета: {seed_words}

Требования:
- Полностью на русском языке
- Длина: 32-48 строки (2-3 куплета + припевы)
- Используй близкие точные акцентные рифмы, желательно панторифмы и ритм, характерные для русского рэпа
- Сюжет должен ОБЯЗАТЕЛЬНО включать интерпретацию каждого seed-слова, желательно с акцентом на этом слове
- Стиль: современный русский рэп
- Включи припев (hook)
- Будь креативным и оригинальным
- Будь как @metac0wb0y
"""

RAP_PROMPT_TEMPLATE_EN = """Write a rap text in English.

Use the following seed words as the basis of the story: {seed_words}

Requirements:
- Fully in English
- Length: 32-48 lines (2-3 verses + chorus)
- Use rhymes and rhythm typical of modern rap
- The plot MUST include interpretation of each seed word
- Style: contemporary rap
- Include a chorus (hook)
- Be creative and original
- Be like @metac0wb0y
"""

mnemo_ru = Mnemonic("russian")
mnemo_en = Mnemonic("english")

def markdown_to_html(text: str) -> str:
    """Конвертирует Markdown жирный (**...**) в HTML <strong>...</strong>."""
    if not text:
        return ""
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text) # Убираем звездочки для читаемости или меняем на теги

def new_entropy(bytes_len=16):
    return secrets.token_bytes(bytes_len)

def generate_seed_RUwords():
    return mnemo_ru.to_mnemonic(new_entropy())

def generate_seed_ENGwords():
    return mnemo_en.to_mnemonic(new_entropy())

def make_session():
    """Создает сессию с автоматическими ретраями на уровне TCP/HTTP"""
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=2,
        read=1, # Меньше ретраев на чтение здесь, лучше обработаем логически
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

session = make_session()

def log_message(artist_name, seed_words, prompt, rap_text):
    log_entry = {
        "artist": artist_name,
        "seed_words": seed_words,
        "timestamp": time.time()
    }
    logging.info(f"Generated track for {artist_name}")
    # Лучше использовать logging вместо print для продакшена
    try:
        with open("logs.txt", "a", encoding='utf-8') as log_file:
            log_file.write(f"{log_entry}\n")
    except Exception as e:
        logging.error(f"Failed to write log: {e}")

def get_rap_from_gemini(prompt: str, model: str):
    """
    Делает запрос к Gemini.
    Таймаут выставлен жесткий (30с), чтобы не висеть вечно и быстрее переключиться на Fallback.
    """
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {
        'Content-Type': 'application/json',
        "x-goog-api-key": "AIzaSyA2wjcAQMSPwqV-7ne4y71u_7NoQqmXjmU"
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # 30 секунд - разумный предел для HTTP запроса перед тем, как Nginx выдаст 504
    timeout = 300

    try:
        resp = session.post(api_url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()

        data = resp.json()
        candidates = data.get('candidates', [])
        if not candidates:
            raise RuntimeError("Empty candidates from Gemini")

        parts = candidates[0].get('content', {}).get('parts', [])
        if not parts or 'text' not in parts[0]:
            # Иногда Gemini блокирует контент из-за Safety Settings, это нужно логировать
            finish_reason = candidates[0].get('finishReason')
            raise RuntimeError(f"No text in response. Finish reason: {finish_reason}")

        return parts[0]['text'].strip()

    except requests.exceptions.Timeout:
        logging.warning(f"Timeout exceeded for model {model}")
        raise RuntimeError("Gemini timeout")
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for {model}: {e}")
        raise RuntimeError(f"Gemini request failed: {e}")

def is_russian(text: str):
    return any('А' <= ch <= 'Я' or 'а' <= ch <= 'я' for ch in text)

def build_prompt(seed_words: str, lang: str, options: dict) -> str:
    base = RAP_PROMPT_TEMPLATE_RU if lang == "ru" else RAP_PROMPT_TEMPLATE_EN
    extra = []

    punch_amount = options.get('punch_amount', 0)
    if punch_amount > 0:
        extra.append(f"Punch intensity: {punch_amount} (0=min, 5=max).")

    if options.get('lyrics_love'):
        extra.append("Include romantic lyrical lines and references to love.")
    if options.get('storytelling'):
        extra.append("Include storytelling elements about the requester (first-person details).")
    if options.get('melancholy'):
        extra.append("Add a melancholic tone in parts of the track.")
    if options.get('one_vs_all'):
        extra.append("Include a 'one vs all' theme and references to confrontation.")

    mood = options.get('mood')
    if mood:
        extra.append(f"Mood level: {mood} on a 1-5 scale; adjust energy and tempo accordingly.")

    extras_text = "\n\nДополнительные настройки:\n- " + "\n- ".join(extra) if extra else ""
    return base.format(seed_words=seed_words) + extras_text

@app.errorhandler(OSError)
def handle_os_error(e):
    # Обработка обрыва соединения клиентом (Broken Pipe)
    if getattr(e, "errno", None) == errno.EPIPE:
        logging.warning("Client disconnected during response write")
        return "", 499
    return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception:
        return "Frontend template not found, use API endpoints.", 404

@app.route("/generate_random_seed", methods=["GET"])
def generate_random_seed():
    lang = request.args.get("lang", "ru")
    seed_words = generate_seed_RUwords() if lang == "ru" else generate_seed_ENGwords()
    return jsonify({"seed_words": seed_words})

@app.route("/generate_rap", methods=["GET"])
def generate_rap():
    invite_code = request.args.get("invite_code")
    artist_name = request.args.get("artist_name", "Anonymous")
    seed_words = request.args.get("seed_words")
    lang = request.args.get("lang", "ru")

    # Валидация параметров
    try:
        punch_amount = max(0, min(5, int(request.args.get("punch_amount", 0))))
        mood = max(1, min(5, int(request.args.get("mood", 3))))
    except (ValueError, TypeError):
        punch_amount = 0
        mood = 3

    lyrics_love = request.args.get("lyrics_love", "0").lower() in ("1", "true", "yes", "on")
    storytelling = request.args.get("storytelling", "0").lower() in ("1", "true", "yes", "on")
    melancholy = request.args.get("melancholy", "0").lower() in ("1", "true", "yes", "on")
    one_vs_all = request.args.get("one_vs_all", "0").lower() in ("1", "true", "yes", "on")

    if not invite_code or invite_code not in VALID_INVITE_CODES:
        return jsonify({"error": "A valid invite_code is required."}), 403

    if not seed_words:
        seed_words = generate_seed_RUwords() if lang == "ru" else generate_seed_ENGwords()

    use_ru = (lang == "ru") or is_russian(seed_words)

    options = {
        "punch_amount": punch_amount,
        "lyrics_love": lyrics_love,
        "storytelling": storytelling,
        "melancholy": melancholy,
        "one_vs_all": one_vs_all,
        "mood": mood
    }

    prompt = build_prompt(seed_words=seed_words, lang=("ru" if use_ru else "en"), options=options)

    # СТРАТЕГИЯ ГЕНЕРАЦИИ
    # 1. Сначала пробуем основную модель (Pro)
    # 2. Если таймаут или ошибка — пробуем Flash (она быстрее)
    # 3. Делаем всего 3 попытки, чтобы уложиться в лимиты браузера/сервера (60 сек)

    attempts_log = []

    # Список моделей для перебора: сначала мощная, потом быстрая, потом снова мощная
    models_sequence = [PRIMARY_MODEL, FALLBACK_MODEL, PRIMARY_MODEL]

    rap_text = None
    successful_model = None

    for attempt, model_name in enumerate(models_sequence, 1):
        try:
            logging.info(f"Attempt {attempt}: Using model {model_name}")
            rap_text = get_rap_from_gemini(prompt, model=model_name)
            successful_model = model_name
            break # Успех! Выходим из цикла
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Attempt {attempt} failed ({model_name}): {error_msg}")
            attempts_log.append(f"{model_name}: {error_msg}")
            # Небольшая пауза перед следующей попыткой, но не слишком длинная
            time.sleep(1)

    if rap_text:
        rap_text_html = markdown_to_html(rap_text)
        log_message(artist_name, seed_words, prompt, rap_text_html)
        return jsonify({
            "rap_text": rap_text_html,
            "seed_words": seed_words,
            "artistName": artist_name,
            "model_used": successful_model,
            "attempts": len(attempts_log) + 1,
            "options": options
        })
    else:
        # Если все попытки провалились
        return jsonify({
            "error": "Generation failed. Server is busy or API is unreachable.",
            "details": attempts_log
        }), 504

@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(force=True, silent=True) or {}
    rap_text = data.get("rap_text", "")
    lang = data.get("lang", "ru")

    if not rap_text:
        return jsonify({"error": "No rap_text provided"}), 400

    try:
        tts_lang = "ru" if lang.startswith("ru") else "en"
        # Очищаем HTML теги для озвучки, если они есть
        clean_text = re.sub(r'<[^>]+>', '', rap_text)

        tts_obj = gTTS(text=clean_text, lang=tts_lang)
        buf = io.BytesIO()
        tts_obj.write_to_fp(buf)
        buf.seek(0)

        # Ускорение аудио
        audio = AudioSegment.from_file(buf, format="mp3")
        faster_audio = audio.speedup(playback_speed=1.35)

        out_buf = io.BytesIO()
        faster_audio.export(out_buf, format="mp3")
        out_buf.seek(0)

        return send_file(
            out_buf,
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=f"rap_{int(time.time())}.mp3"
        )
    except Exception as e:
        logging.exception("TTS generation failed")
        return jsonify({"error": f"TTS generation failed: {e}"}), 500

if __name__ == "__main__":
    # threaded=True важно для одновременной обработки запросов
    app.run(host="0.0.0.0", port=5666, debug=False, threaded=True)