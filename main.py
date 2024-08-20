import sqlite3
import os
import time
from datetime import datetime
import telebot
from telebot import types
import threading

class ResidentsDB:
    def __init__(self, db_path):
        self.db_path = db_path

    def create_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS residents (
                            resident_id INTEGER PRIMARY KEY,
                            name TEXT NOT NULL,
                            surname TEXT NOT NULL,
                            apt TEXT NOT NULL,
                            phone TEXT NOT NULL UNIQUE,
                            telegram_id INTEGER UNIQUE
                        )''')
        conn.commit()
        conn.close()

    def add_resident(self, name, surname, apt, phone, telegram_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''INSERT INTO residents (name, surname, apt, phone, telegram_id)
                              VALUES (?, ?, ?, ?, ?)''', (name, surname, apt, phone, telegram_id))
            conn.commit()
            resident_id = cursor.lastrowid
            # Добавляем нового резидента в таблицу payment_data со значениями по умолчанию
            cursor.execute('''INSERT INTO payment_data (resident_id, current_balance, arrears)
                              VALUES (?, ?, ?)''', (resident_id, 0, 100))
            conn.commit()
        except sqlite3.IntegrityError:
            resident_id = False
        finally:
            conn.close()
        return resident_id

    def get_residents(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM residents")
        residents = cursor.fetchall()
        conn.close()
        return residents

    def get_resident_by_telegram_id(self, telegram_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM residents WHERE telegram_id = ?", (telegram_id,))
        resident = cursor.fetchone()
        conn.close()
        return resident


class PaymentManagerDB:
    def __init__(self, db_path):
        self.db_path = db_path

    def create_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS payment_data (
                            resident_id INTEGER PRIMARY KEY,
                            current_balance REAL NOT NULL,
                            arrears REAL NOT NULL,
                            FOREIGN KEY (resident_id) REFERENCES residents(resident_id)
                        )''')
        conn.commit()
        conn.close()

    def create_payment_folders(self):
        payments_path = os.path.join('payments')
        if not os.path.exists(payments_path):
            os.makedirs(payments_path)

        current_date = datetime.now()
        year = str(current_date.year)
        month = current_date.strftime('%B')

        year_path = os.path.join(payments_path, year)
        if not os.path.exists(year_path):
            os.makedirs(year_path)

        month_path = os.path.join(year_path, month)
        if not os.path.exists(month_path):
            os.makedirs(month_path)

        file_path = os.path.join(month_path, 'payment_data.db')
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS payment_data (
                            resident_id INTEGER PRIMARY KEY,
                            current_balance REAL NOT NULL,
                            arrears REAL NOT NULL,
                            FOREIGN KEY (resident_id) REFERENCES residents(resident_id)
                        )''')
        conn.commit()
        conn.close()

    def get_account_status(self, resident_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT current_balance, arrears FROM payment_data WHERE resident_id = ?", (resident_id,))
        data = cursor.fetchone()
        conn.close()
        if data:
            current_balance, arrears = data
            return current_balance, arrears
        else:
            return None, None

    def get_connection(self):
        return sqlite3.connect(self.db_path)


TOKEN = "6514605804:AAHYgihremJI64nl_D1W9yVz3o5wtt7lqpk"
bot = telebot.TeleBot(TOKEN)

DB_FILE = "database.db"

residents_manager = ResidentsDB(DB_FILE)
payment_manager = PaymentManagerDB(DB_FILE)

registered_users = {}

def check_debts_and_send_messages():
    print("Проверяем задолженности и отправляем сообщения...")
    current_year = datetime.now().strftime('%Y')
    current_month = datetime.now().strftime('%B')

    residents = residents_manager.get_residents()

    for resident in residents:
        resident_id = resident[0]
        _, arrears = payment_manager.get_account_status(resident_id)

        if arrears is not None and arrears > 0:
            telegram_id = resident[-1]  # Assuming the last column is telegram_id
            try:
                bot.send_message(telegram_id, f"У вас имеется задолженность в размере: {arrears} грн.")
                print(f"Отправлено сообщение пользователю с Telegram ID: {telegram_id}")
            except Exception as e:
                print(f"Ошибка при отправке сообщения пользователю с Telegram ID {telegram_id}: {str(e)}")

    print("Проверка и отправка завершены.")


def bot_polling():
    bot.polling()


def main_loop():
    interval_seconds = 10
    while True:
        check_debts_and_send_messages()
        print(f"Рассылка выполнена. Ждем {interval_seconds} секунд до следующей проверки...")
        time.sleep(interval_seconds)


@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.id in registered_users:
        bot.reply_to(message, "Введите свой номер телефона для входа")
        bot.register_next_step_handler(message, login)
    else:
        show_registration_menu(message)


@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if message.chat.id in registered_users:
        handle_registered_user_messages(message)
    else:
        handle_registration_choice(message)


def show_registration_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    registration_button = types.KeyboardButton('Регистрация')
    login_button = types.KeyboardButton('Вход')
    markup.add(registration_button, login_button)
    bot.send_message(message.chat.id, "Добро пожаловать в телеграмм бот нашего ОСББ! Выберите действие:",
                     reply_markup=markup)


@bot.message_handler(func=lambda message: message.text in ['Регистрация', 'Вход'])
def handle_registration_choice(message):
    if message.text == 'Регистрация':
        bot.reply_to(message, "Введите свои данные для регистрации в формате: Имя Фамилия Квартира Номер телефона")
        bot.register_next_step_handler(message, register)
    elif message.text == 'Вход':
        bot.reply_to(message, "Введите свой номер телефона для входа")
        bot.register_next_step_handler(message, login)


def register(message):
    try:
        name, surname, apt, phone = message.text.split()
        telegram_id = message.chat.id
        if not residents_manager.get_resident_by_telegram_id(telegram_id):
            resident_id = residents_manager.add_resident(name, surname, apt, phone, telegram_id)
            registered_users[telegram_id] = True
            bot.reply_to(message, "Вы успешно зарегистрированы!")
            show_main_menu(message)
        else:
            bot.reply_to(message, "Пользователь с таким Telegram ID уже зарегистрирован.")
            show_registration_menu(message)

    except ValueError:
        bot.reply_to(message, "Неправильный формат ввода. Пожалуйста, введите свои данные в нужном формате.")


def login(message):
    try:
        phone_number = message.text
        resident = residents_manager.get_resident_by_telegram_id(message.chat.id)
        if resident:
            resident_id = resident[0]
            registered_users[message.chat.id] = True
            bot.reply_to(message, "Вы успешно вошли в систему!")
            show_main_menu(message)
        else:
            bot.reply_to(message, "Пользователь с таким Telegram ID не найден.")
            show_registration_menu(message)

    except ValueError:
        bot.reply_to(message, "Неправильный формат ввода. Пожалуйста, введите свой номер телефона.")


def show_main_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=1)
    balance_button = types.KeyboardButton('Проверить баланс')
    debts_button = types.KeyboardButton('Проверить задолженность')
    markup.add(balance_button, debts_button)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)


def handle_registered_user_messages(message):
    if message.text == 'Проверить баланс':
        check_balance(message)
    elif message.text == 'Проверить задолженность':
        check_debts(message)
    else:
        bot.reply_to(message, "Извините, я не понимаю вашего запроса. Пожалуйста, выберите действие из меню.")


def check_balance(message):
    resident = residents_manager.get_resident_by_telegram_id(message.chat.id)
    if resident:
        resident_id = resident[0]
        current_balance, _ = payment_manager.get_account_status(resident_id)
        if current_balance is not None:
            bot.reply_to(message, f"Ваш текущий баланс: {current_balance} грн")
        else:
            bot.reply_to(message, "Извините, не удалось получить информацию о балансе.")
    else:
        bot.reply_to(message, "Пожалуйста, сначала зарегистрируйтесь или войдите в систему.")


def check_debts(message):
    resident = residents_manager.get_resident_by_telegram_id(message.chat.id)
    if resident:
        resident_id = resident[0]
        _, arrears = payment_manager.get_account_status(resident_id)
        if arrears is not None and arrears > 0:
            bot.reply_to(message, f"У вас имеется задолженность в размере: {arrears} грн.")
        else:
            bot.reply_to(message, "У вас нет текущей задолженности.")
    else:
        bot.reply_to(message, "Пожалуйста, сначала зарегистрируйтесь или войдите в систему.")


if __name__ == "__main__":
    residents_manager.create_table()
    payment_manager.create_table()
    payment_manager.create_payment_folders()

    # Создаем два потока: один для работы бота, другой для цикла проверки задолженностей
    bot_thread = threading.Thread(target=bot_polling)
    main_loop_thread = threading.Thread(target=main_loop)

    bot_thread.start()
    main_loop_thread.start()

    bot_thread.join()
    main_loop_thread.join()
