import telebot
from telebot import types, apihelper
import sqlite3
import json
import requests
import random
import time


def get_db_connection():
    return sqlite3.connect('users.db', check_same_thread=False)

def get_cursor():
    conn = get_db_connection()
    return conn, conn.cursor()

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    age INTEGER CHECK(age <= 21),
    gender TEXT,
    interested_in TEXT,
    city TEXT,
    latitude REAL,
    longitude REAL,
    phone TEXT,
    bio TEXT,
    media_file_ids TEXT,
    is_active INTEGER DEFAULT 1
)
''')

conn.commit()
cursor.execute('''
CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER,
    to_user_id INTEGER,
    UNIQUE(from_user_id, to_user_id)
)
''')
conn.commit()
cursor.execute('''
CREATE TABLE IF NOT EXISTS blocked_users (
    user_id INTEGER PRIMARY KEY,
    blocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
)
''')
conn.commit()
cursor.close()
conn.close()
bot = telebot.TeleBot('7990634300:AAFJNQU6fw-pIhqRxgTPAGL6RaYla9xYLew')
user_viewing_progress = {}
@bot.message_handler(commands=['start'])
def start(message):
    conn = get_db_connection()
    cursor = conn.cursor()

    user_id = message.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data_row = cursor.fetchone()

    if user_data_row:
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        keyboard.add("Погнали!")
        bot.send_message(message.chat.id, "👻 Добро пожаловать обратно!", reply_markup=keyboard)
        bot.register_next_step_handler_by_chat_id(message.chat.id, handle_existing_user_start)
    else:
        welcome_text = "👻 Добро пожаловать в Krasnoff Love бот для знакомств!"
        keyboard = types.InlineKeyboardMarkup()
        start_button = types.InlineKeyboardButton(text="Давай начнем!", callback_data="start_dating")
        keyboard.add(start_button)
        bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)

    cursor.close()
    conn.close()

def handle_existing_user_start(message):
    if message.text == "Погнали!":
        user_id = message.from_user.id

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if row:
            user_data = {
                'age': row[3],
                'gender': row[4],
                'interested_in': row[5],
                'city': row[6]
            }
            start_viewing_profiles(message, user_data)
    else:
        msg = bot.send_message(message.chat.id, "Пожалуйста, нажмите кнопку.")
        bot.register_next_step_handler(msg, handle_existing_user_start)

@bot.callback_query_handler(func=lambda call: call.data == "start_dating")
def callback_start_dating(call):
    warning_text = ("Помните, что в интернете люди могут выдавать себя за других!\n\n"
                    "Бот не запрашивает личные данные и не идентифицирует пользователей "
                    "по каким-либо документам.")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, warning_text)
    
    msg = bot.send_message(call.message.chat.id, "📋 Сколько вам лет?")
    bot.register_next_step_handler(msg, process_age_step, {})

def process_age_step(message, user_data):
    if not message.text.isdigit():
        msg = bot.send_message(message.chat.id, "⚠️ Пожалуйста, введите ваш возраст **цифрами**.")
        bot.register_next_step_handler(msg, process_age_step, user_data)
        return

    age = int(message.text)
    if age > 21:
        warning_text = (
            "❌ Упс… Похоже, вам больше 21 года.\n"
            "К сожалению, участие в боте ограничено возрастом до 21 года.\n\n"
            "Вы можете попробовать зарегистрироваться снова позже командой /start. 💌"
        )
        bot.send_message(message.chat.id, warning_text)
        return

    user_data['age'] = age
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Мужской", "Женский")
    msg = bot.send_message(message.chat.id, "Выберите ваш пол:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_gender_step, user_data)


def process_gender_step(message, user_data):
    user_data['gender'] = message.text
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Девушки", "Парни", "Все равно")
    msg = bot.send_message(message.chat.id, "Кто тебе интересен?", reply_markup=markup)
    bot.register_next_step_handler(msg, process_interested_step, user_data)

def process_interested_step(message, user_data):
    user_data['interested_in'] = message.text
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton("Отправить мою геопозицию", request_location=True))
    msg = bot.send_message(message.chat.id, "Из какого вы города? Отправьте геопозицию или напишите свой город на русском языке!", reply_markup=markup)
    bot.register_next_step_handler(msg, process_location_step, user_data)


def process_location_step(message, user_data):
    if message.location:
        latitude = message.location.latitude
        longitude = message.location.longitude
        user_data['latitude'] = latitude
        user_data['longitude'] = longitude

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": latitude, "lon": longitude, "format": "json", "accept-language": "ru"},
                headers={"User-Agent": "KrasnoffLoveBot/1.0"}
            )
            data = response.json()
            city = (
                data.get("address", {}).get("city") or
                data.get("address", {}).get("town") or
                data.get("address", {}).get("village") or
                data.get("address", {}).get("state") or
                "Неизвестный город"
            )
            user_data['city'] = city
        except Exception as e:
            print(f"Ошибка при получении города: {e}")
            user_data['city'] = "Неизвестный город"

    else:
        city_text = message.text.strip()
        if not city_text:
            msg = bot.send_message(
                message.chat.id,
                "❗ Город не распознан. Пожалуйста, отправьте геопозицию или напишите город текстом."
            )
            bot.register_next_step_handler(msg, process_location_step, user_data)
            return
        user_data['city'] = city_text.title()
        user_data['latitude'] = None
        user_data['longitude'] = None
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton("Отправить мой номер телефона", request_contact=True))
    msg = bot.send_message(
        message.chat.id,
        f"🏙 Ваш город установлен как: {user_data['city']}\n\nТеперь отправьте свой номер телефона для подтверждения анкеты:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_phone_step, user_data)


def process_phone_step(message, user_data):
    if message.contact is None:
        msg = bot.send_message(message.chat.id, "Номер телефона обязателен! Используйте кнопку.")
        bot.register_next_step_handler(msg, process_phone_step, user_data)
        return
    user_data['phone'] = message.contact.phone_number

    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Использовать имя Telegram")
    msg = bot.send_message(message.chat.id, "Как мне вас называть?", reply_markup=markup)
    bot.register_next_step_handler(msg, process_name_step, user_data)

def process_name_step(message, user_data):
    if message.text == "Использовать имя Telegram":
        user_data['first_name'] = message.from_user.first_name
    else:
        user_data['first_name'] = message.text
    
    msg = bot.send_message(message.chat.id, "Расскажите о себе и кого хотите найти:\n(Информация будет отображаться в анкете)")
    bot.register_next_step_handler(msg, process_bio_step, user_data)

def process_bio_step(message, user_data):
    user_data['bio'] = message.text
    user_data['media'] = []
    msg = bot.send_message(message.chat.id, "📸 Теперь пришлите фото или видео (до 15 секунд), которое будут видеть другие пользователи:")
    bot.register_next_step_handler(msg, process_media_step, user_data)

def process_media_step(message, user_data):
    if message.photo:
        user_data['media'].append({'type': 'photo', 'file_id': message.photo[-1].file_id})
    elif message.video:
        if message.video.duration > 15:
            msg = bot.send_message(message.chat.id, "Видео не должно быть длиннее 15 секунд. Отправьте другое видео или фото.")
            bot.register_next_step_handler(msg, process_media_step, user_data)
            return
        user_data['media'].append({'type': 'video', 'file_id': message.video.file_id})
    else:
        msg = bot.send_message(message.chat.id, "Пожалуйста, отправьте фото или видео!")
        bot.register_next_step_handler(msg, process_media_step, user_data)
        return

    if len(user_data['media']) >= 2:
        send_profile_review(message, user_data)
        return

    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Добавить ещё", "Пропустить")
    msg = bot.send_message(message.chat.id, f"Вы загрузили {len(user_data['media'])} медиа. Хотите добавить ещё?", reply_markup=markup)
    bot.register_next_step_handler(msg, process_add_more_step, user_data)

def process_add_more_step(message, user_data):
    if message.text == "Добавить ещё":
        msg = bot.send_message(message.chat.id, "Пришлите фото или видео:")
        bot.register_next_step_handler(msg, process_media_step, user_data)
    else:
        send_profile_review(message, user_data)

def send_profile_review(message, user_data):
    conn = get_db_connection()
    cursor = conn.cursor()

    media_file_ids = json.dumps(user_data['media'])
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, age, gender, interested_in, city,
                                      latitude, longitude, phone, bio, media_file_ids)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        message.from_user.id,
        message.from_user.username,
        user_data.get('first_name'),
        user_data.get('age'),
        user_data.get('gender'),
        user_data.get('interested_in'),
        user_data.get('city', ''),
        user_data.get('latitude'),
        user_data.get('longitude'),
        user_data.get('phone'),
        user_data.get('bio'),
        media_file_ids
    ))
    conn.commit()
    cursor.close()
    conn.close()

    media_group = []
    for idx, m in enumerate(user_data['media']):
        caption = f"{user_data.get('first_name')}, {user_data.get('age')} лет\n{user_data.get('bio')}" if idx == 0 else None
        if m['type'] == 'photo':
            media_group.append(types.InputMediaPhoto(media=m['file_id'], caption=caption))
        else:
            media_group.append(types.InputMediaVideo(media=m['file_id'], caption=caption))
    bot.send_message(message.chat.id, "Вот как выглядит ваша анкета:")
    bot.send_media_group(message.chat.id, media_group)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Да, всё верно ✅", "Изменить анкету ✏️")
    msg = bot.send_message(message.chat.id, "Проверьте всё ли правильно 👇", reply_markup=markup)
    bot.register_next_step_handler(msg, handle_profile_confirmation, user_data)


def handle_profile_confirmation(message, user_data):
    if message.text.startswith("Да"):
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("1", "2")

        text = (
            "Выбери действие:\n\n"
            "1️⃣ Смотреть анкеты\n"
            "2️⃣ Заполнить анкету заново\n"
        )

        msg = bot.send_message(message.chat.id, text, reply_markup=markup)
        bot.register_next_step_handler(msg, handle_final_options_selection, user_data)

    elif message.text.startswith("Изменить"):
        msg = bot.send_message(message.chat.id, "Начнем заново с возраста 🧠")
        bot.register_next_step_handler(msg, process_age_step, {})


def handle_final_options_selection(message, user_data):
    text = message.text.strip()

    if text == "1":
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Погнали!")
        msg = bot.send_message(
            message.chat.id,
            "💌 Отлично! Остался последний шаг, и ты будешь близок к знакомствам!\nТыкай на кнопку!",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, lambda m: start_viewing_profiles(m, user_data))

    elif text == "2":
        msg = bot.send_message(message.chat.id, "Начнем заново с возраста 🧭")
        bot.register_next_step_handler(msg, process_age_step, {})

    else:
        bot.send_message(message.chat.id, "Пожалуйста, выбери вариант от 1 до 2 ⬇️")
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("1", "2")
        msg = bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)
        bot.register_next_step_handler(msg, handle_final_options_selection, user_data)


def start_viewing_profiles(message, user_data):
    user_id = message.from_user.id
    if message.text.strip() not in ["Погнали!", "/start"]:
        bot.send_message(user_id, "Нажмите «Погнали!», чтобы продолжить.")
        return

    bot.send_message(user_id, "🚀")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET is_active = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

    age = user_data['age']
    gender = user_data['gender']
    interested_in = user_data['interested_in']

    cursor.execute("SELECT city FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    user_city = result[0] if result else None

    cursor.close()
    conn.close()

    progress = user_viewing_progress.get(user_id)
    if progress:
        send_next_profile(message)
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM users WHERE user_id != ? AND is_active = 1"
    params = [user_id]
    query += " AND age BETWEEN ? AND ?"
    params.extend([age - 2, age + 2])
    if user_city:
        query += " AND city = ?"
        params.append(user_city)
    if interested_in == "Девушки":
        query += " AND gender = 'Женский' AND interested_in IN ('Парни', 'Все равно')"
    elif interested_in == "Парни":
        query += " AND gender = 'Мужской' AND interested_in IN ('Девушки', 'Все равно')"
    elif interested_in == "Все равно":
        if gender == "Мужской":
            query += " AND ((gender = 'Женский' AND interested_in IN ('Парни', 'Все равно')) OR (gender = 'Мужской' AND interested_in = 'Все равно'))"
        else:
            query += " AND ((gender = 'Мужской' AND interested_in IN ('Девушки', 'Все равно')) OR (gender = 'Женский' AND interested_in = 'Все равно'))"

    cursor.execute(query, params)
    profiles = cursor.fetchall()

    cursor.close()
    conn.close()

    if not profiles:
        bot.send_message(user_id, "Нет подходящих анкет 😔 Попробуйте позже!")
        return

    profiles_list = list(profiles)
    random.shuffle(profiles_list)
    user_viewing_progress[user_id] = {'profiles': profiles_list, 'current_index': 0}
    send_next_profile(message)

import random
from functools import partial
from telebot import types
import json

from telebot import types

from telebot import types

def send_next_profile(message):
    user_id = message.from_user.id
    progress = user_viewing_progress.get(user_id)

    if not progress or not progress.get('profiles'):
        bot.send_message(message.chat.id, "Ты долистал до конца :(\nПопробуй позже снова!")
        user_viewing_progress.pop(user_id, None)
        return

    profile = progress['profiles'][0]
    media_file_ids = json.loads(profile[11])
    valid_media = [m for m in media_file_ids if m.get("file_id") and m["file_id"] != "TEST_FILE_ID"]

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("❤️", "💌")
    markup.add("👎", "😴")

    if valid_media:
        media = valid_media[0]
        caption = f"{profile[2]}, {profile[3]} лет\n{profile[10]}"
        if media['type'] == 'photo':
            bot.send_photo(message.chat.id, media['file_id'], caption=caption, reply_markup=markup)
        else:
            bot.send_video(message.chat.id, media['file_id'], caption=caption, reply_markup=markup)
    else:
        bot.send_message(
            message.chat.id,
            f"📋 Анкета:\nИмя: {profile[2]}\nВозраст: {profile[3]}\nБио: {profile[10]}",
            reply_markup=markup
        )

    bot.register_next_step_handler(message, handle_profile_action)

def handle_profile_action(message):
    user_id = message.from_user.id
    progress = user_viewing_progress.get(user_id)

    if not progress or not progress.get('profiles'):
        bot.send_message(message.chat.id, "Ты просмотрел все доступные анкеты.\nПопробуй позже!")
        user_viewing_progress.pop(user_id, None)
        return

    profile = progress['profiles'][0]
    target_user_id = profile[0]

    action = message.text.strip()
    valid_actions = ["❤️", "💌", "👎", "😴"]
    if action not in valid_actions:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(*valid_actions)
        bot.send_message(
            message.chat.id,
            "⚠️ Пожалуйста, выберите действие с помощью кнопок ниже.",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, handle_profile_action)
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if action == "❤️":
            cursor.execute(
                "SELECT 1 FROM likes WHERE from_user_id = ? AND to_user_id = ?",
                (user_id, target_user_id)
            )
            already_liked = cursor.fetchone()

            if already_liked:
                bot.send_message(message.chat.id, "Вы уже лайкали этого человека ❤️")
            else:
                cursor.execute(
                    "INSERT INTO likes (from_user_id, to_user_id) VALUES (?, ?)",
                    (user_id, target_user_id)
                )
                conn.commit()

                cursor.execute(
                    "SELECT 1 FROM likes WHERE from_user_id = ? AND to_user_id = ?",
                    (target_user_id, user_id)
                )
                mutual_like = cursor.fetchone()

                if mutual_like:
                    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                    liker = cursor.fetchone()
                    cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_user_id,))
                    responder = cursor.fetchone()

                    liker_username = liker[1] or liker[2]
                    responder_username = responder[1] or responder[2]

                    wishes = [
                        "✨ Пусть этот мэтч станет началом чего-то особенного!",
                        "💖 Возможно, это судьба, не упусти шанс!",
                        "🌹 Любовь — это магия, и вы только что её нашли!",
                        "💞 Две души нашли друг друга — теперь начинается самое интересное!"
                    ]
                    wish = random.choice(wishes)

                    liker_text = (
                        f"💞 Найден мэтч! Ваша пара — @{responder_username}!\n\n{wish}\n👉 Напиши им: https://t.me/{responder_username}"
                        if responder_username else f"💞 Найден мэтч! Ваша пара — {responder[2]}!\n\n{wish}"
                    )
                    responder_text = (
                        f"💞 Найден мэтч! Ваша пара — @{liker_username}!\n\n{wish}\n👉 Напиши им: https://t.me/{liker_username}"
                        if liker_username else f"💞 Найден мэтч! Ваша пара — {liker[2]}!\n\n{wish}"
                    )

                    bot.send_message(user_id, liker_text)
                    bot.send_message(target_user_id, responder_text)

                    cursor.execute(
                        "DELETE FROM likes WHERE (from_user_id = ? AND to_user_id = ?) OR (from_user_id = ? AND to_user_id = ?)",
                        (user_id, target_user_id, target_user_id, user_id)
                    )
                    conn.commit()
                else:
                    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
                    markup.add("Давай!")
                    msg = bot.send_message(
                        target_user_id,
                        "💘 Твоя анкета кого-то зацепила! Хочешь узнать кого?)",
                        reply_markup=markup
                    )
                    bot.register_next_step_handler(msg, start_showing_likers)

        elif action == "💌":
            msg = bot.send_message(message.chat.id, "Напишите короткое послание этому человеку:")
            bot.register_next_step_handler(
                msg,
                partial(handle_send_message_to_profile, target_user_id=target_user_id)
            )
            return


        elif action == "👎":
            pass

        elif action == "😴":
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("1", "2", "3")
            text = (
                "😴 Ты приостановил просмотр.\n"
                "Что хочешь сделать дальше?\n\n"
                "1️⃣ Смотреть анкеты\n"
                "2️⃣ Моя анкета\n"
                "3️⃣ Я больше никого не хочу искать"
            )
            msg = bot.send_message(message.chat.id, text, reply_markup=markup)
            bot.register_next_step_handler(msg, partial(handle_pause_selection, progress=progress, user_id=user_id))
            return

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    progress['profiles'].pop(0)

    if progress['profiles']:
        send_next_profile(message)
    else:
        bot.send_message(
            message.chat.id,
            "Ты просмотрел все доступные анкеты.\nПопробуй позже!\nВведи /start чтобы начать снова."
        )
        user_viewing_progress.pop(user_id, None)

def show_next_liker_profile(message):
    user_id = message.from_user.id
    progress = user_viewing_progress.setdefault(user_id, {})

    if 'likers_queue' not in progress or not progress['likers_queue']:
        bot.send_message(user_id, "Нет новых анкет для просмотра.")
        return

    action = message.text.strip() if message.text else None

    conn = get_db_connection()
    cursor = conn.cursor()

    if action in ["❤️", "👎"]:
        prev_index = progress.get('current_liker_index', 0) - 1
        if 0 <= prev_index < len(progress['likers_queue']):
            prev_liker_id = progress['likers_queue'][prev_index]

            if action == "❤️":
                cursor.execute(
                    "SELECT 1 FROM likes WHERE from_user_id = ? AND to_user_id = ?",
                    (prev_liker_id, user_id)
                )
                mutual_like = cursor.fetchone()

                if mutual_like:
                    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                    responder = cursor.fetchone()
                    cursor.execute("SELECT * FROM users WHERE user_id = ?", (prev_liker_id,))
                    liker = cursor.fetchone()

                    liker_username = liker[1] or liker[2]
                    responder_username = responder[1] or responder[2]

                    wishes = [
                        "✨ Пусть этот мэтч станет началом чего-то особенного!",
                        "💖 Возможно, это судьба, не упусти шанс!",
                        "🌹 Любовь — это магия, и вы только что её нашли!",
                        "💞 Две души нашли друг друга — теперь начинается самое интересное!"
                    ]
                    wish = random.choice(wishes)

                    liker_text = (
                        f"💞 Найден мэтч! Ваша пара — @{responder_username}!\n\n{wish}\n👉 Напиши им: https://t.me/{responder_username}"
                        if responder_username else f"💞 Найден мэтч! Ваша пара — {responder[2]}!\n\n{wish}"
                    )
                    responder_text = (
                        f"💞 Найден мэтч! Ваша пара — @{liker_username}!\n\n{wish}\n👉 Напиши им: https://t.me/{liker_username}"
                        if liker_username else f"💞 Найден мэтч! Ваша пара — {liker[2]}!\n\n{wish}"
                    )

                    bot.send_message(user_id, responder_text)
                    bot.send_message(prev_liker_id, liker_text)

    index = progress.get('current_liker_index', 0)
    if index >= len(progress['likers_queue']):
        cursor.close()
        conn.close()
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Погнали!")
        msg = bot.send_message(user_id, "✅ Все анкеты просмотрены!\nИдём дальше?", reply_markup=markup)
        bot.register_next_step_handler(msg, go_back_to_main_menu)
        progress.pop('likers_queue', None)
        progress.pop('current_liker_index', None)
        return

    liker_id = progress['likers_queue'][index]
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (liker_id,))
    liker = cursor.fetchone()

    if not liker:
        progress['current_liker_index'] += 1
        cursor.close()
        conn.close()
        show_next_liker_profile(message)
        return

    media_list = json.loads(liker[11]) if liker[11] else []
    if media_list and isinstance(media_list, list):
        media_group = []
        for idx, m in enumerate(media_list):
            caption = f"{liker[2]}, {liker[3]} лет\n{liker[10]}" if idx == 0 else None
            if m['type'] == 'photo':
                media_group.append(types.InputMediaPhoto(media=m['file_id'], caption=caption))
            else:
                media_group.append(types.InputMediaVideo(media=m['file_id'], caption=caption))
        bot.send_media_group(user_id, media_group)
    else:
        bot.send_message(user_id, f"📋 Имя: {liker[2]}\nВозраст: {liker[3]}\nО себе: {liker[10]}")

    cursor.close()
    conn.close()
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("❤️", "👎")
    msg = bot.send_message(user_id, "Вам нравится этот человек?", reply_markup=markup)
    bot.register_next_step_handler(msg, show_next_liker_profile)

    progress['current_liker_index'] += 1


def start_showing_likers(message):
    user_id = message.from_user.id
    progress = user_viewing_progress.setdefault(user_id, {})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT from_user_id FROM likes WHERE to_user_id = ?", (user_id,))
    likers = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not likers:
        bot.send_message(user_id, "😔 Пока никто вас не лайкнул.")
        return

    progress['likers_queue'] = likers
    progress['current_liker_index'] = 0

    show_next_liker_profile(message)

def go_back_to_main_menu(message):
    user_id = message.from_user.id

    if message.text.strip() != "Погнали!":
        bot.send_message(user_id, "Нажмите «Погнали!», чтобы продолжить.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT age, gender, interested_in FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    if not result:
        bot.send_message(user_id, "😕 Не удалось найти ваши данные. Сначала заполните анкету.")
        return

    user_data = {
        "age": result[0],
        "gender": result[1],
        "interested_in": result[2]
    }

    start_viewing_profiles(message, user_data)

temp_media_storage = {}
def handle_pause_selection(message, progress, user_id):
    choice = message.text.strip()

    if choice == "1" or choice.startswith("❤️"):
        bot.send_message(message.chat.id, "📖 Продолжаем просмотр анкет!")
        send_next_profile(message)

    elif choice == "2" or choice.startswith("2"):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            media_list = json.loads(user[11]) if user[11] else []
            if media_list:
                media_group = []
                for idx, m in enumerate(media_list):
                    caption = f"{user[2]}, {user[3]} лет\n{user[10]}" if idx == 0 else None
                    if m['type'] == 'photo':
                        media_group.append(types.InputMediaPhoto(media=m['file_id'], caption=caption))
                    else:
                        media_group.append(types.InputMediaVideo(media=m['file_id'], caption=caption))
                bot.send_media_group(message.chat.id, media_group)
            else:
                bot.send_message(
                    message.chat.id,
                    f"📋 Имя: {user[2]}\nВозраст: {user[3]}\nО себе: {user[10]}"
                )

            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add("1", "2")
            markup.add("3", "4")
            msg = bot.send_message(
                message.chat.id,
                "Выбери действие:\n"
                "1. Смотреть анкеты\n"
                "2. Заполнить анкету заново\n"
                "3. Изменить фото/видео\n"
                "4. Изменить текст анкеты",
                reply_markup=markup
            )
            bot.register_next_step_handler(msg, handle_user_menu_action_inline, user_id)
        else:
            bot.send_message(message.chat.id, "⚠️ Не удалось найти вашу анкету.")

    elif choice == "3":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()

        bot.send_message(
            message.chat.id,
            "😔 Хорошо, мы больше никого не будем показывать.\n"
            "Если передумаешь — просто напиши /start ❤️",
            reply_markup=types.ReplyKeyboardRemove()
        )

    else:
        bot.send_message(message.chat.id, "Пожалуйста, выбери 1, 2 или 3 ⬇️")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("1", "2", "3")
        msg = bot.send_message(message.chat.id, "Что хочешь сделать дальше?", reply_markup=markup)
        bot.register_next_step_handler(msg, handle_pause_selection, progress, user_id)


def handle_user_menu_action_inline(message, user_id):
    choice = message.text.strip()

    if choice.startswith("1") or choice.startswith("❤️") or choice.startswith("Смотреть анкеты"):
        send_next_profile(message)

    elif choice.startswith("2"):
        msg = bot.send_message(message.chat.id, "Начнем заново с возраста 🧭")
        bot.register_next_step_handler(msg, process_age_step, {})

    elif choice.startswith("3"):
        bot.send_message(message.chat.id, "Отправьте новые фото/видео для вашей анкеты.")
        bot.register_next_step_handler(message, handle_add_media, user_id)

    elif choice.startswith("4"):
        bot.send_message(message.chat.id, "Введите новый текст для вашей анкеты.")
        bot.register_next_step_handler(message, update_bio, user_id)

    else:
        bot.send_message(message.chat.id, "⚠️ Неизвестный выбор. Попробуйте снова.")
        handle_pause_selection(message, None, user_id)


def handle_add_media(message, user_id):
    media_file_id = None
    media_type = None

    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        media_file_id = message.video.file_id
        media_type = 'video'
    else:
        bot.send_message(message.chat.id, "⚠️ Отправьте фото или видео!")
        bot.register_next_step_handler(message, handle_add_media, user_id)
        return

    user_media = temp_media_storage.get(user_id, [])
    user_media.append({"type": media_type, "file_id": media_file_id})
    temp_media_storage[user_id] = user_media

    if len(user_media) < 2:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Добавить ещё", "Сохранить")
        msg = bot.send_message(message.chat.id, "Вы можете добавить ещё медиа или сохранить.", reply_markup=markup)
        bot.register_next_step_handler(msg, handle_media_choice, user_id)
    else:
        save_media_to_db(user_id)
        bot.send_message(message.chat.id, "✅ Ваша анкета успешно сохранена!", reply_markup=types.ReplyKeyboardRemove())
        temp_media_storage.pop(user_id, None)
        send_next_profile(message)

def handle_media_choice(message, user_id):
    choice = message.text.strip()
    if choice == "Добавить ещё":
        bot.send_message(message.chat.id, "Отправьте ещё одно фото или видео.", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, handle_add_media, user_id)
    elif choice == "Сохранить":
        save_media_to_db(user_id)
        bot.send_message(message.chat.id, "✅ Ваша анкета успешно сохранена!", reply_markup=types.ReplyKeyboardRemove())
        temp_media_storage.pop(user_id, None)
        send_next_profile(message)
    else:
        bot.send_message(message.chat.id, "Пожалуйста, выбери 'Добавить ещё' или 'Сохранить'.")
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Добавить ещё", "Сохранить")
        msg = bot.send_message(message.chat.id, "Что делать дальше?", reply_markup=markup)
        bot.register_next_step_handler(msg, handle_media_choice, user_id)


def save_media_to_db(user_id):
    """Сохраняет фото/видео анкеты в базу данных."""
    user_media = temp_media_storage.get(user_id, [])
    if not user_media:
        return

    media_json = json.dumps(user_media[:2])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET media_file_ids = ? WHERE user_id = ?", (media_json, user_id))
    conn.commit()
    cursor.close()
    conn.close()


def update_bio(message, user_id):
    """Обновляет текст анкеты."""
    new_bio = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET bio = ? WHERE user_id = ?", (new_bio, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    bot.send_message(message.chat.id, "✅ Текст анкеты обновлён!")
    send_next_profile(message)


def handle_profile_like_response(message, liker_id, progress, user_data_list):
    """Обработка ответа на лайк или дизлайк и показ следующей анкеты."""
    responder_id = message.from_user.id
    action = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    if action == "❤️":
        cursor.execute(
            "INSERT OR IGNORE INTO likes (from_user_id, to_user_id) VALUES (?, ?)",
            (responder_id, liker_id)
        )
        conn.commit()

        cursor.execute(
            "SELECT 1 FROM likes WHERE from_user_id = ? AND to_user_id = ?",
            (liker_id, responder_id)
        )
        mutual = cursor.fetchone()

        if mutual:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (liker_id,))
            liker = cursor.fetchone()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (responder_id,))
            responder = cursor.fetchone()

            liker_username = liker[1] or liker[2]
            responder_username = responder[1] or responder[2]

            import random
            wishes = [
                "✨ Пусть этот мэтч станет началом чего-то особенного!",
                "💖 Возможно, это судьба, не упусти шанс!",
                "🌹 Любовь — это магия, и вы только что её нашли!",
                "💞 Две души нашли друг друга — теперь начинается самое интересное!"
            ]
            wish = random.choice(wishes)

            liker_text = (
                f"💞 Найден мэтч! Твоя пара — @{responder_username}!\n\n{wish}\n\n👉 Пиши скорее: https://t.me/{responder_username}"
                if responder_username else f"💞 Найден мэтч! Твоя пара — {responder[2]}!\n\n{wish}"
            )
            responder_text = (
                f"💞 Найден мэтч! Твоя пара — @{liker_username}!\n\n{wish}\n\n👉 Пиши скорее: https://t.me/{liker_username}"
                if liker_username else f"💞 Найден мэтч! Твоя пара — {liker[2]}!\n\n{wish}"
            )

            bot.send_message(liker_id, liker_text)
            bot.send_message(responder_id, responder_text)

    else:
        bot.send_message(message.chat.id, "👎 Вы отклонили предложение.")

    cursor.close()
    conn.close()

    if responder_id not in progress:
        progress[responder_id] = 0

    if progress[responder_id] >= len(user_data_list):
        bot.send_message(message.chat.id, "📌 Анкет больше нет. Попробуй позже!")
        return

    next_profile = user_data_list[progress[responder_id]]
    progress[responder_id] += 1

    media_group = []
    for idx, m in enumerate(next_profile['media']):
        caption = f"{next_profile['first_name']}, {next_profile['age']} лет\n{next_profile['bio']}" if idx == 0 else None
        if m['type'] == 'photo':
            media_group.append(types.InputMediaPhoto(media=m['file_id'], caption=caption))
        else:
            media_group.append(types.InputMediaVideo(media=m['file_id'], caption=caption))

    bot.send_media_group(message.chat.id, media_group)

    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("❤️", "👎")
    msg = bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)
    bot.register_next_step_handler(msg, handle_profile_like_response, next_profile['user_id'], progress, user_data_list)

import json
from telebot import types

user_viewing_progress = {}

def handle_send_message_to_profile(message, target_user_id):
    user_id = message.from_user.id
    text = message.text

    conn, cursor = get_cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO likes (from_user_id, to_user_id) VALUES (?, ?)",
        (user_id, target_user_id)
    )
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    sender = cursor.fetchone()
    cursor.close()
    conn.close()

    if not sender:
        bot.send_message(message.chat.id, "⚠️ Не удалось получить данные вашей анкеты.")
        return

    sender_name = sender[2]
    sender_age = sender[3]
    sender_about = sender[10]
    media_list = json.loads(sender[11]) if sender[11] else []
    progress = user_viewing_progress.setdefault(target_user_id, {})
    queue = progress.setdefault('incoming_messages', [])

    queue.append({
        'type': 'message',
        'from_user_id': user_id,
        'name': sender_name,
        'age': sender_age,
        'about': sender_about,
        'media_list': media_list,
        'text': text
    })

    bot.send_message(message.chat.id, "✅ Ваше послание будет доставлено ❤️\nТеперь вы можете продолжить просмотр анкет.")
    
    if not progress.get('viewing'):
        show_sender_profile(target_user_id)
    send_next_profile(message)


def show_sender_profile(user_id):
    progress = user_viewing_progress.setdefault(user_id, {})

    if progress.get('viewing'):
        return
    progress['viewing'] = True

    queue = progress.get('incoming_messages', [])

    if not queue:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Погнали!")
        msg = bot.send_message(
            user_id,
            "📭 Все входящие сообщения просмотрены.",
            reply_markup=markup
        )

        user_viewing_progress.pop(user_id, None)

        def handle_go_next(m):
            choice = m.text.strip()
            if choice == "Погнали!":
                go_back_to_main_menu(m)

        bot.register_next_step_handler(msg, handle_go_next)
        return

    current_item = queue[0]

    if current_item['type'] == 'message':
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Да!")

        msg = bot.send_message(
            user_id,
            f"💌 Вам пришло сообщение:\n\n{current_item['text']}\n\nХотите посмотреть анкету отправителя?",
            reply_markup=markup
        )

        def handle_response(m):
            action = m.text.strip()
            if action == "Да!":
                queue[0] = {
                    'type': 'profile',
                    'from_user_id': current_item['from_user_id'],
                    'name': current_item.get('name', 'Не указано'),
                    'age': current_item.get('age', '?'),
                    'about': current_item.get('about', '—'),
                    'media_list': current_item.get('media_list', [])
                }
                progress['viewing'] = False
                show_sender_profile(user_id)
                return

        bot.register_next_step_handler(msg, handle_response)

    elif current_item['type'] == 'profile':
        try:
            media_list = current_item.get('media_list', [])
            name = current_item.get('name', 'Не указано')
            age = current_item.get('age', '?')
            about = current_item.get('about', '—')

            if media_list:
                media_group = []
                for idx, m in enumerate(media_list):
                    caption = f"{name}, {age} лет\n{about}" if idx == 0 else None
                    if m['type'] == 'photo':
                        media_group.append(types.InputMediaPhoto(media=m['file_id'], caption=caption))
                    else:
                        media_group.append(types.InputMediaVideo(media=m['file_id'], caption=caption))
                bot.send_media_group(user_id, media_group)
            else:
                bot.send_message(user_id, f"📋 Имя: {name}\nВозраст: {age}\nО себе: {about}")

            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add("❤️", "👎")
            msg = bot.send_message(user_id, "Вам нравится этот человек?", reply_markup=markup)

            def handle_choice(m):
                action = m.text.strip()
                target_id = current_item['from_user_id']

                conn, cursor = get_cursor()
                try:
                    if action == "❤️":
                        cursor.execute(
                            "INSERT OR IGNORE INTO likes (from_user_id, to_user_id) VALUES (?, ?)",
                            (user_id, target_id)
                        )
                        conn.commit()

                        cursor.execute(
                            "SELECT 1 FROM likes WHERE from_user_id = ? AND to_user_id = ?",
                            (target_id, user_id)
                        )
                        mutual_like = cursor.fetchone()

                        if mutual_like:
                            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                            liker = cursor.fetchone()
                            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
                            responder = cursor.fetchone()

                            liker_name = liker[1] or liker[2]
                            responder_name = responder[1] or responder[2]

                            wishes = [
                                "✨ Пусть этот мэтч станет началом чего-то особенного!",
                                "💖 Возможно, это судьба, не упусти шанс!",
                                "🌹 Любовь — это магия, и вы только что её нашли!",
                                "💞 Две души нашли друг друга — теперь начинается самое интересное!"
                            ]
                            wish = random.choice(wishes)

                            liker_text = (
                                f"💞 Найден мэтч! Ваша пара — @{responder_name}!\n\n{wish}\n👉 Напиши им: https://t.me/{responder_name}"
                                if responder_name else f"💞 Найден мэтч! Ваша пара — {responder[2]}!\n\n{wish}"
                            )
                            responder_text = (
                                f"💞 Найден мэтч! Ваша пара — @{liker_name}!\n\n{wish}\n👉 Напиши им: https://t.me/{liker_name}"
                                if liker_name else f"💞 Найден мэтч! Ваша пара — {liker[2]}!\n\n{wish}"
                            )

                            bot.send_message(user_id, liker_text)
                            bot.send_message(target_id, responder_text)

                            cursor.execute(
                                "DELETE FROM likes WHERE (from_user_id = ? AND to_user_id = ?) OR (from_user_id = ? AND to_user_id = ?)",
                                (user_id, target_id, target_id, user_id)
                            )
                            conn.commit()
                        else:
                            bot.send_message(user_id, "❤️ Лайк отправлен!")
                    else:
                        bot.send_message(user_id, "👎 Вы отклонили предложение.")

                finally:
                    cursor.close()
                    conn.close()

                queue.pop(0)
                progress['viewing'] = False
                show_sender_profile(user_id)

            bot.register_next_step_handler(msg, handle_choice)

        except Exception as e:
            print(f"⚠️ Не удалось показать анкету: {e}")
            queue.pop(0)
            progress['viewing'] = False
            show_sender_profile(user_id)

def safe_send_message(user_id, text, **kwargs):
    try:
        bot.send_message(user_id, text, **kwargs)
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "403" in str(e):
            print(f"⚠️ Невозможно отправить сообщение пользователю {user_id}: бот заблокирован или чат не начат")
        else:
            print(f"⚠️ Ошибка при отправке сообщения пользователю {user_id}: {e}")
        return False


def broadcast_message(text):
    try:
        conn = get_db_connection()
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users WHERE is_active = 1")
            users = cur.fetchall()

        for (user_id,) in users:
            try:
                bot.send_message(user_id, text)
                time.sleep(0.1)
            except Exception as e:
                error_msg = str(e).lower()
                if "bot was blocked by the user" in error_msg or "user is deactivated" in error_msg or "chat not found" in error_msg:
                    print(f"⚠️ Пользователь {user_id} заблокировал бота или деактивирован. Помечаем как неактивного.")
                    try:
                        with conn:
                            cur.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
                    except Exception as db_e:
                        print(f"❌ Ошибка при обновлении статуса пользователя {user_id}: {db_e}")
                else:
                    print(f"⚠️ Не удалось отправить сообщение пользователю {user_id}: {e}")

        print("✅ Рассылка завершена!")

    except Exception as e:
        print(f"⚠️ Ошибка при получении списка пользователей для рассылки: {e}")

    finally:
        if 'conn' in locals():
            conn.close()


ADMINS = [1282651738, 398948784]
ADMIN_PASSWORD = 'supersecret'
admin_sessions = {}

@bot.message_handler(commands=['admin'])
def admin_login(message):
    chat_id = message.chat.id
    if chat_id not in ADMINS:
        bot.send_message(chat_id, "❌ У вас нет доступа к админ-панели!")
        return

    msg = bot.send_message(chat_id, "Введите пароль для доступа в админ-панель:")
    bot.register_next_step_handler(msg, check_admin_password)

def check_admin_password(message):
    chat_id = message.chat.id
    if message.text == ADMIN_PASSWORD:
        admin_sessions[chat_id] = True
        bot.send_message(chat_id, "✅ Доступ разрешён!")
        start_admin_panel(message)
    else:
        bot.send_message(chat_id, "❌ Неверный пароль!")

def start_admin_panel(message):
    chat_id = message.chat.id
    if not admin_sessions.get(chat_id):
        bot.send_message(chat_id, "Доступ запрещён!")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📋 Список пользователей", "📊 Статистика", "🚀 Сделать рассылку")
    markup.add("🔒 Заблокировать пользователя", "🔓 Разблокировать пользователя")
    markup.add("⬅️ Выйти")
    bot.send_message(chat_id, "Админ-панель:", reply_markup=markup)

@bot.message_handler(func=lambda m: admin_sessions.get(m.chat.id))
def handle_admin_action(message):
    chat_id = message.chat.id
    text = message.text

    try:
        if text == "📋 Список пользователей":
            conn, cur = get_cursor()
            cur.execute("SELECT user_id, username, first_name, is_active FROM users")
            users = cur.fetchall()
            cur.close()
            conn.close()

            text_list = "\n".join([f"{u[0]} | @{u[1]} | {u[2]} | {'Активен' if u[3] else 'Неактивен'}" for u in users])
            bot.send_message(chat_id, f"Список пользователей:\n{text_list or 'Пусто'}")

        elif text == "📊 Статистика":
            conn, cur = get_cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
            active_users = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 0")
            inactive_users = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM users WHERE media_file_ids IS NOT NULL AND media_file_ids != ''")
            media_profiles = cur.fetchone()[0]

            cur.execute("SELECT gender, COUNT(*) FROM users GROUP BY gender")
            gender_stats = cur.fetchall()

            cur.execute("SELECT interested_in, COUNT(*) FROM users GROUP BY interested_in")
            interested_stats = cur.fetchall()

            cur.close()
            conn.close()

            gender_text = "\n".join([f"{g[0]}: {g[1]}" for g in gender_stats])
            interested_text = "\n".join([f"{i[0]}: {i[1]}" for i in interested_stats])

            stats_text = (
                f"📊 Статистика пользователей:\n\n"
                f"Всего пользователей: {total_users}\n"
                f"Активные: {active_users}\n"
                f"Неактивные: {inactive_users}\n"
                f"По полу:\n{gender_text}\n\n"
                f"По интересам:\n{interested_text}"
            )

            bot.send_message(chat_id, stats_text)

        elif text == "🚀 Сделать рассылку":
            msg = bot.send_message(chat_id, "Введите текст рассылки:")
            bot.register_next_step_handler(msg, send_broadcast)

        elif text == "🔒 Заблокировать пользователя":
            msg = bot.send_message(chat_id, "Введите user_id пользователя для блокировки:")
            bot.register_next_step_handler(msg, block_user)

        elif text == "🔓 Разблокировать пользователя":
            msg = bot.send_message(chat_id, "Введите user_id пользователя для разблокировки:")
            bot.register_next_step_handler(msg, unblock_user)

        elif text == "⬅️ Выйти":
            admin_sessions[chat_id] = False
            bot.send_message(chat_id, "Вы вышли из админ-панели.", reply_markup=types.ReplyKeyboardRemove())

        else:
            bot.send_message(chat_id, "Неизвестная команда, выберите действие заново.")
            start_admin_panel(message)

    except Exception as e:
        print(f"⚠️ Ошибка админ-панели: {e}")
        start_admin_panel(message)

def send_broadcast(message):
    text = message.text
    try:
        conn, cur = get_cursor()
        cur.execute("SELECT user_id FROM users")
        all_users = cur.fetchall()
        cur.close()
        conn.close()

        for u in all_users:
            try:
                bot.send_message(u[0], text)
            except:
                continue
        bot.send_message(message.chat.id, "Рассылка завершена!")
    except Exception as e:
        print(f"⚠️ Ошибка рассылки: {e}")
    start_admin_panel(message)

def block_user(message):
    try:
        user_id = int(message.text)
        conn, cur = get_cursor()
        cur.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
        cur.execute("INSERT OR IGNORE INTO blocked_users(user_id) VALUES (?)", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        bot.send_message(message.chat.id, f"Пользователь {user_id} заблокирован.")
    except Exception as e:
        print(f"⚠️ Ошибка блокировки пользователя: {e}")
    start_admin_panel(message)

def unblock_user(message):
    try:
        user_id = int(message.text)
        conn, cur = get_cursor()
        cur.execute("UPDATE users SET is_active = 1 WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        bot.send_message(message.chat.id, f"Пользователь {user_id} разблокирован.")
    except Exception as e:
        print(f"⚠️ Ошибка разблокировки пользователя: {e}")
    start_admin_panel(message)


if __name__ == "__main__":
    broadcast_message("🔥 Наш бот снова в работе! Напишите /start, чтобы начать знакомство!")
    print("🤖 Бот запущен и готов к работе...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка при работе бота: {e}")
            time.sleep(5)
