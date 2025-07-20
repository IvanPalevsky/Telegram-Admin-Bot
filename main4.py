import os
import sys
import socket
import psutil
import telebot
from telebot import types
import json
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import time

# Инициализация бота
bot = telebot.TeleBot('')

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_file = 'bot.log'
log_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=5, encoding='utf-8')
log_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(console_handler)

# Константы
SUPER_ADMIN_ID = '1454561912'
EMOJI = {
    'success': '✅', 'error': '❌', 'info': 'ℹ️', 'settings': '⚙️', 'stats': '📊', 
    'users': '👥', 'chats': '💬', 'channels': '📢', 'subscribe': '🔔', 'unsubscribe': '🔕', 
    'block': '🚫', 'unblock': '🔓', 'delete': '🗑️', 'edit': '✏️', 'admin': '👑', 
    'help': '❓', 'welcome': '👋', 'wave': '👋', 'warning': '⚠️', 'back': '🔙',
    'search': '🔍', 'rating': '⭐', 'mute': '🔇', 'unmute': '🔈', 'rocket': '🚀', 
    'fire': '🔥', 'gem': '💎', 'magic': '✨', 'cool': '😎', 'party': '🎉', 'level_up': '🆙',
    'medal_bronze': '🥉', 'medal_silver': '🥈', 'medal_gold': '🥇', 'trophy': '🏆',
    'star': '⭐', 'sparkles': '✨', 'thinking': '🤔', 'robot': '🤖',
}

# Глобальные переменные для хранения данных
users, chats, channels = {}, {}, {}

def save_data():
    try:
        data = {'users': users, 'chats': chats, 'channels': channels}
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Данные успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {str(e)}")
        # Можно добавить резервное сохранение или уведомление администратора
        bot.send_message(SUPER_ADMIN_ID, f"{EMOJI['error']} Ошибка при сохранении данных: {str(e)}")

def load_data():
    global users, chats, channels
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            users, chats, channels = data['users'], data['chats'], data['channels']
        logger.info("Данные успешно загружены")
    except FileNotFoundError:
        logger.warning("Файл данных не найден. Создан новый.")
        save_data()
    except json.JSONDecodeError:
        logger.error("Ошибка при чтении файла данных. Создан новый.")
        save_data()

load_data()

def is_user_blocked(user_id):
    return users.get(str(user_id), {}).get('blocked', False)

def super_admin_required(func):
    def wrapper(message):
        if isinstance(message, types.CallbackQuery):
            if str(message.from_user.id) != SUPER_ADMIN_ID:
                bot.answer_callback_query(message.id, f"{EMOJI['error']} У вас нет прав для выполнения этой команды.")
                return
        elif str(message.from_user.id) != SUPER_ADMIN_ID:
            bot.reply_to(message, f"{EMOJI['error']} У вас нет прав для выполнения этой команды.")
            return
        return func(message)
    return wrapper

def calculate_rating(user):
    return user.get('messages_count', 0) + user.get('reactions_received', 0) * 2

def get_rank_emoji(rating):
    if rating < 100:
        return EMOJI['medal_bronze']
    elif rating < 500:
        return EMOJI['medal_silver']
    elif rating < 1000:
        return EMOJI['medal_gold']
    else:
        return EMOJI['trophy']

def update_user_rating(user_id, change):
    user = users.get(str(user_id))
    if user:
        old_rating = calculate_rating(user)
        user['messages_count'] = user.get('messages_count', 0) + change
        new_rating = calculate_rating(user)
        save_data()
        return old_rating, new_rating
    return None

def get_top_users(n=10):
    sorted_users = sorted(users.values(), key=lambda x: calculate_rating(x), reverse=True)
    return sorted_users[:n]

def safe_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except telebot.apihelper.ApiException as e:
        if e.result.status_code == 403:
            logger.warning(f"Бот заблокирован пользователем {chat_id}")
        elif e.result.status_code == 400:
            logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")
        else:
            logger.error(f"Неизвестная ошибка при отправке сообщения в чат {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке сообщения в чат {chat_id}: {str(e)}")
        return None
    
def scan_chat_members(chat_id):
    """Сканирует всех участников чата и добавляет их в базу"""
    try:
        # Получаем информацию о чате
        chat_info = bot.get_chat(chat_id)
        
        # Получаем список администраторов
        admins = bot.get_chat_administrators(chat_id)
        admin_ids = [str(admin.user.id) for admin in admins]
        
        # Инициализируем или обновляем информацию о чате
        if chat_id not in chats:
            chats[chat_id] = {
                'id': chat_id,
                'title': chat_info.title,
                'type': chat_info.type,
                'members': [],
                'messages_count': 0,
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        # Получаем актуальный список участников через администратора чата
        members = []
        for admin in admins:
            if admin.can_invite_users:  # Ищем админа с правами просмотра участников
                try:
                    for member in bot.get_chat_members(chat_id):
                        member_id = str(member.user.id)
                        if member_id not in members:
                            members.append(member_id)
                            
                            # Добавляем пользователя в базу данных
                            if member_id not in users:
                                users[member_id] = {
                                    'id': member_id,
                                    'first_name': member.user.first_name,
                                    'last_name': member.user.last_name,
                                    'username': member.user.username,
                                    'joined_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'messages_count': 0,
                                    'reactions_received': 0,
                                    'chats': [chat_id],
                                    'channels': [],
                                    'language': 'ru'
                                }
                            elif chat_id not in users[member_id]['chats']:
                                users[member_id]['chats'].append(chat_id)
                except Exception as e:
                    logger.error(f"Ошибка при получении участников через админа: {e}")
                break
        
        # Обновляем список участников в чате
        chats[chat_id]['members'] = members
        save_data()
        
        return len(members)
    except Exception as e:
        logger.error(f"Ошибка при сканировании участников чата {chat_id}: {e}")
        return 0

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = str(message.from_user.id)
    if is_user_blocked(user_id):
        return

    if user_id not in users:
        users[user_id] = {
            'id': user_id,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'username': message.from_user.username,
            'joined_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'messages_count': 0,
            'reactions_received': 0,
            'chats': [],
            'channels': [],
            'language': 'ru'
        }
    else:
        users[user_id].update({
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'username': message.from_user.username,
        })
    save_data()
    
    welcome_text = get_localized_text('welcome_message', user_id).format(name=message.from_user.first_name)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_localized_text('help_button', user_id), callback_data="help"))
    markup.add(types.InlineKeyboardButton(get_localized_text('menu_button', user_id), callback_data="menu"))
    
    bot.reply_to(message, welcome_text, reply_markup=markup)
    logger.info(f"Пользователь {user_id} начал работу с ботом")

def get_localized_text(key, user_id):
    user_language = users.get(str(user_id), {}).get('language', 'ru')
    localized_texts = {
        'ru': {
            'enter_new_name': f"{EMOJI['edit']} Введите новое имя:",
            'welcome_message': f"{EMOJI['welcome']} Привет, {{name}}!\n\nЯ бот для управления чатами и каналами. {EMOJI['info']}\n\nЧтобы начать работу, используйте команду /menu для доступа к основному меню.",
            'help_button': f"{EMOJI['help']} Помощь",
            'menu_button': f"{EMOJI['settings']} Меню",
            'help_message': f"{EMOJI['help']} Список доступных команд:\n\n/start - Начать работу с ботом\n/help - Показать список команд\n/menu - Открыть главное меню\n/settings - Настройки пользователя\n/rating - Показать рейтинг пользователей\n/feedback - Отправить отзыв или сообщение",
            'back_to_menu': f"{EMOJI['back']} Назад в меню",
            'main_menu': f"{EMOJI['settings']} Главное меню",
            'my_chats': f"{EMOJI['chats']} Мои чаты",
            'my_channels': f"{EMOJI['channels']} Мои каналы",
            'settings': f"{EMOJI['settings']} Настройки",
            'statistics': f"{EMOJI['stats']} Статистика",
            'rating': f"{EMOJI['rating']} Рейтинг",
            'no_chats': f"{EMOJI['info']} У вас пока нет чатов",
            'no_channels': f"{EMOJI['info']} У вас пока нет каналов",
            'user_not_found': f"{EMOJI['error']} Пользователь не найден.",
            'change_name': "Изменить имя",
            'change_language': "Изменить язык",
            'notifications': "Уведомления",
            'user_settings': f"{EMOJI['settings']} Настройки пользователя:",
            'select_language': f"{EMOJI['edit']} Выберите язык:",
            'russian': "Русский",
            'english': "English",
            'language_changed': f"{EMOJI['success']} Язык успешно изменен",
            'notification_settings': f"{EMOJI['settings']} Настройки уведомлений",
            'notifications_on': "Включены",
            'notifications_off': "Выключены",
            'user_stats': f"{EMOJI['stats']} Ваша статистика:",
            'rating_info': f"{EMOJI['trophy']} Топ-10 пользователей по рейтингу:",
            'feedback_request': f"{EMOJI['edit']} Пожалуйста, напишите ваш отзыв или сообщение:",
            'feedback_sent': f"{EMOJI['success']} Спасибо за ваш отзыв! Он был отправлен администратору.",
            'feedback_error': f"{EMOJI['error']} Произошла ошибка при отправке отзыва. Попробуйте позже.",
            'bot_instructions': f"{EMOJI['info']} Инструкция по использованию бота:\n\n1. Добавьте бота в ваш чат или канал.\n2. Назначьте бота администратором.\n3. Используйте команду /menu для доступа к функциям управления."
        },
        'en': {
            'enter_new_name': f"{EMOJI['edit']} Введите новое имя:",
            'welcome_message': f"{EMOJI['welcome']} Hello, {{name}}!\n\nI'm a bot for managing chats and channels. {EMOJI['info']}\n\nTo get started, use the /menu command to access the main menu.",
            'help_button': f"{EMOJI['help']} Help",
            'menu_button': f"{EMOJI['settings']} Menu",
            'help_message': f"{EMOJI['help']} List of available commands:\n\n/start - Start working with the bot\n/help - Show list of commands\n/menu - Open main menu\n/settings - User settings\n/rating - Show user ratings\n/feedback - Send feedback or message",
            'back_to_menu': f"{EMOJI['back']} Back to menu",
            'main_menu': f"{EMOJI['settings']} Main Menu",
            'my_chats': f"{EMOJI['chats']} My Chats",
            'my_channels': f"{EMOJI['channels']} My Channels",
            'settings': f"{EMOJI['settings']} Settings",
            'statistics': f"{EMOJI['stats']} Statistics",
            'rating': f"{EMOJI['rating']} Rating",
            'no_chats': f"{EMOJI['info']} You don't have any chats yet",
            'no_channels': f"{EMOJI['info']} You don't have any channels yet",
            'user_not_found': f"{EMOJI['error']} User not found.",
            'change_name': "Change name",
            'change_language': "Change language",
            'notifications': "Notifications",
            'user_settings': f"{EMOJI['settings']} User settings:",
            'select_language': f"{EMOJI['edit']} Select language:",
            'russian': "Russian",
            'english': "English",
            'language_changed': f"{EMOJI['success']} Language changed successfully",
            'notification_settings': f"{EMOJI['settings']} Notification settings",
            'notifications_on': "Enabled",
            'notifications_off': "Disabled",
            'user_stats': f"{EMOJI['stats']} Your statistics:",
            'rating_info': f"{EMOJI['trophy']} Top 10 users by rating:",
            'feedback_request': f"{EMOJI['edit']} Please write your feedback or message:",
            'feedback_sent': f"{EMOJI['success']} Thank you for your feedback! It has been sent to the administrator.",
            'feedback_error': f"{EMOJI['error']} An error occurred while sending feedback. Please try again later.",
            'bot_instructions': f"{EMOJI['info']} Instructions for using the bot:\n\n1. Add the bot to your chat or channel.\n2. Assign the bot as an administrator.\n3. Use the /menu command to access management functions."
        }
    }
    return localized_texts.get(user_language, localized_texts['ru']).get(key, key)

@bot.message_handler(commands=['help'])
def handle_help(message):
    if is_user_blocked(str(message.from_user.id)):
        return

    help_text = get_localized_text('help_message', message.from_user.id)
    
    if str(message.from_user.id) == SUPER_ADMIN_ID:
        help_text += "\n/super_admin - Панель управления суперадминистратора"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_localized_text('back_to_menu', message.from_user.id), callback_data="menu"))
    
    bot.reply_to(message, help_text, reply_markup=markup)
    logger.info(f"Пользователь {message.from_user.id} запросил справку")

@bot.message_handler(commands=['menu'])
def handle_menu(message):
    show_main_menu(message.chat.id)

def show_main_menu(chat_id):
    user_id = str(chat_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(get_localized_text('my_chats', user_id), callback_data="my_chats"),
        types.InlineKeyboardButton(get_localized_text('my_channels', user_id), callback_data="my_channels"),
        types.InlineKeyboardButton(get_localized_text('settings', user_id), callback_data="settings"),
        types.InlineKeyboardButton(get_localized_text('statistics', user_id), callback_data="user_stats"),
        types.InlineKeyboardButton(get_localized_text('rating', user_id), callback_data="show_rating"),
        types.InlineKeyboardButton(get_localized_text('help_button', user_id), callback_data="help")
    )
    markup.add(types.InlineKeyboardButton(get_localized_text('bot_instructions', user_id), callback_data="bot_instructions"))
    
    bot.send_message(chat_id, get_localized_text('main_menu', user_id), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "menu")
def callback_menu(call):
    show_main_menu(call.message.chat.id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def callback_help(call):
    handle_help(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "bot_instructions")
def callback_bot_instructions(call):
    user_id = str(call.from_user.id)
    instructions = get_localized_text('bot_instructions', user_id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_localized_text('back_to_menu', user_id), callback_data="menu"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=instructions, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "my_chats")
def handle_my_chats(call):
    user_id = str(call.from_user.id)
    user_chats = users.get(user_id, {}).get('chats', [])
    
    if not user_chats:
        bot.answer_callback_query(call.id, get_localized_text('no_chats', user_id))
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for chat_id in user_chats:
        chat = chats.get(chat_id)
        if chat:
            markup.add(types.InlineKeyboardButton(chat['title'], callback_data=f"manage_chat:{chat_id}"))
    
    markup.add(types.InlineKeyboardButton(get_localized_text('back_to_menu', user_id), callback_data="menu"))
    
    bot.edit_message_text(get_localized_text('my_chats', user_id), call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "notifications_settings")
def handle_notifications_settings(call):
    user_id = str(call.from_user.id)
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, get_localized_text('user_not_found', user_id))
        return
    
    current_status = user.get('notifications', True)
    new_status = not current_status
    user['notifications'] = new_status
    save_data()
    
    status_text = get_localized_text('notifications_on', user_id) if new_status else get_localized_text('notifications_off', user_id)
    bot.answer_callback_query(call.id, f"{EMOJI['success']} {get_localized_text('notifications', user_id)}: {status_text}")
    
    handle_settings(call)

@bot.callback_query_handler(func=lambda call: call.data == "my_channels")
def handle_my_channels(call):
    user_id = str(call.from_user.id)
    user_channels = users.get(user_id, {}).get('channels', [])
    
    if not user_channels:
        bot.answer_callback_query(call.id, get_localized_text('no_channels', user_id))
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for channel_id in user_channels:
        channel = channels.get(channel_id)
        if channel:
            markup.add(types.InlineKeyboardButton(channel['title'], callback_data=f"manage_channel:{channel_id}"))
    
    markup.add(types.InlineKeyboardButton(get_localized_text('back_to_menu', user_id), callback_data="menu"))
    
    bot.edit_message_text(get_localized_text('my_channels', user_id), call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "settings")
def handle_settings(call):
    user_id = str(call.from_user.id)
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, get_localized_text('user_not_found', user_id))
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(get_localized_text('change_name', user_id), callback_data="change_name"),
        types.InlineKeyboardButton(get_localized_text('change_language', user_id), callback_data="change_language"),
        types.InlineKeyboardButton(get_localized_text('notifications', user_id), callback_data="notifications_settings"),
        types.InlineKeyboardButton(get_localized_text('back_to_menu', user_id), callback_data="menu")
    )
    
    settings_text = get_localized_text('user_settings', user_id) + "\n\n"
    settings_text += f"{get_localized_text('change_name', user_id)}: {user['first_name']} {user['last_name'] or ''}\n"
    settings_text += f"{get_localized_text('change_language', user_id)}: {get_localized_text(user.get('language', 'ru'), user_id)}\n"
    settings_text += f"{get_localized_text('notifications', user_id)}: {get_localized_text('notifications_on' if user.get('notifications', True) else 'notifications_off', user_id)}\n"
    
    bot.edit_message_text(settings_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("change_username:"))
@super_admin_required
def handle_change_username(call):
    entity_type, entity_id = call.data.split(":")[1:]
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите новый username для {'канала' if entity_type == 'channel' else 'чата'}:")
    bot.register_next_step_handler(msg, change_username_step, entity_type, entity_id)

def change_username_step(message, entity_type, entity_id):
    new_username = message.text.strip()
    if not new_username.startswith('@'):
        new_username = '@' + new_username
    
    if entity_type == 'channel':
        if entity_id in channels:
            channels[entity_id]['username'] = new_username
            bot.reply_to(message, f"{EMOJI['success']} Username канала успешно изменен на {new_username}")
        else:
            bot.reply_to(message, f"{EMOJI['error']} Канал не найден")
    elif entity_type == 'chat':
        if entity_id in chats:
            chats[entity_id]['username'] = new_username
            bot.reply_to(message, f"{EMOJI['success']} Username чата успешно изменен на {new_username}")
        else:
            bot.reply_to(message, f"{EMOJI['error']} Чат не найден")
    
    save_data()

    try:
        fake_call = types.CallbackQuery(
            id='0', from_user=message.from_user, chat_instance='0',
            message=message, data=f"{'channel' if entity_type == 'channel' else 'chat'}_info:{entity_id}", json_string='{}'
        )
        if entity_type == 'channel':
            handle_channel_info(fake_call)
        else:
            handle_chat_info(fake_call)
    except telebot.apihelper.ApiTelegramException as e:
        if "message can't be edited" in str(e):
            bot.send_message(message.chat.id, f"{EMOJI['success']} Username успешно изменен. Пожалуйста, вернитесь в меню управления для просмотра обновленной информации.")
        else:
            logger.error(f"Ошибка при обновлении информации: {str(e)}")
            bot.send_message(message.chat.id, f"{EMOJI['error']} Произошла ошибка при обновлении информации. Пожалуйста, попробуйте позже.")
    
    # Возвращаемся к информации о чате или канале
    fake_call = types.CallbackQuery(
        id='0', from_user=message.from_user, chat_instance='0',
        message=message, data=f"{'channel' if entity_type == 'channel' else 'chat'}_info:{entity_id}", json_string='{}'
    )
    if entity_type == 'channel':
        handle_channel_info(fake_call)
    else:
        handle_chat_info(fake_call)

@bot.callback_query_handler(func=lambda call: call.data == "change_name")
def handle_change_name(call):
    user_id = str(call.from_user.id)
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, get_localized_text('enter_new_name', user_id))
    bot.register_next_step_handler(msg, change_name_step)
    logger.info(f"Пользователь {call.from_user.id} начал процесс изменения имени")

def change_name_step(message):
    user_id = str(message.from_user.id)
    new_name = message.text.strip()
    
    if len(new_name) < 2:
        bot.reply_to(message, get_localized_text('name_too_short', user_id))
        return
    
    users[user_id]['first_name'] = new_name
    save_data()
    
    bot.reply_to(message, get_localized_text('name_changed', user_id).format(name=new_name))
    logger.info(f"Пользователь {user_id} изменил свое имя на {new_name}")
    
    show_main_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "change_language")
def handle_change_language(call):
    user_id = str(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(get_localized_text('russian', user_id), callback_data="set_language:ru"),
        types.InlineKeyboardButton(get_localized_text('english', user_id), callback_data="set_language:en"),
        types.InlineKeyboardButton(get_localized_text('back_to_menu', user_id), callback_data="settings")
    )
    
    bot.edit_message_text(
        get_localized_text('select_language', user_id),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    logger.info(f"Пользователь {call.from_user.id} открыл меню выбора языка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_language:"))
def handle_set_language(call):
    user_id = str(call.from_user.id)
    language = call.data.split(":")[1]
    
    users[user_id]['language'] = language
    save_data()
    
    bot.answer_callback_query(call.id, get_localized_text('language_changed', user_id))
    logger.info(f"Пользователь {user_id} изменил язык на {language}")
    
    handle_settings(call)

@bot.message_handler(commands=['super_admin'])
@super_admin_required
def handle_super_admin(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['stats']} Общая статистика", callback_data="overall_stats"),
        types.InlineKeyboardButton(f"{EMOJI['users']} Пользователи", callback_data="manage_users"),
        types.InlineKeyboardButton(f"{EMOJI['chats']} Чаты", callback_data="manage_chats"),
        types.InlineKeyboardButton(f"{EMOJI['channels']} Каналы", callback_data="manage_channels"),
        types.InlineKeyboardButton(f"{EMOJI['rocket']} Рассылка", callback_data="send_broadcast"),
        types.InlineKeyboardButton(f"{EMOJI['settings']} Настройки бота", callback_data="bot_settings")
    )
    
    text = f"{EMOJI['admin']} Панель суперадминистратора\n\n"
    text += f"{EMOJI['rocket']} Выберите раздел для управления:\n\n"
    text += f"{EMOJI['info']} Текущий статус:\n"
    text += f"- Пользователей: {len(users)}\n"
    text += f"- Чатов: {len(chats)}\n"
    text += f"- Каналов: {len(channels)}\n"
    
    bot.send_message(message.chat.id, text, reply_markup=markup)
    logger.info(f"Суперадминистратор {message.from_user.id} открыл панель управления")

@bot.callback_query_handler(func=lambda call: call.data == "overall_stats")
@super_admin_required
def handle_overall_stats(call):
    total_users = len(users)
    total_chats = len(chats)
    total_channels = len(channels)
    active_users = sum(1 for user in users.values() if user.get('messages_count', 0) > 0)
    
    top_users = sorted(users.values(), key=lambda x: calculate_rating(x), reverse=True)[:5]
    
    text = f"{EMOJI['stats']} Общая статистика:\n\n"
    text += f"Всего пользователей: {total_users}\n"
    text += f"Активных пользователей: {active_users}\n"
    text += f"Всего чатов: {total_chats}\n"
    text += f"Всего каналов: {total_channels}\n\n"
    text += f"Топ-5 пользователей по рейтингу:\n"
    for i, user in enumerate(top_users, 1):
        rating = calculate_rating(user)
        text += f"{i}. {user['first_name']} {user['last_name'] or ''} - {rating} очков\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="super_admin"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел общую статистику")

@bot.callback_query_handler(func=lambda call: call.data == "manage_users")
@super_admin_required
def handle_manage_users(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['users']} Список пользователей", callback_data="list_users"),
        types.InlineKeyboardButton(f"{EMOJI['search']} Найти пользователя", callback_data="search_user"),
        types.InlineKeyboardButton(f"{EMOJI['block']} Заблокированные", callback_data="blocked_users"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить рейтинг", callback_data="edit_user_rating"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="super_admin")
    )
    
    text = f"{EMOJI['users']} Управление пользователями\n\n"
    text += f"Всего пользователей: {len(users)}\n"
    text += f"Заблокировано: {sum(1 for user in users.values() if user.get('blocked', False))}\n\n"
    text += f"{EMOJI['thinking']} Выберите действие:"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} открыл меню управления пользователями")

@bot.message_handler(commands=['super_admin'])
@super_admin_required
def handle_super_admin(message):
    show_super_admin_menu(message.chat.id)

def show_super_admin_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['stats']} Общая статистика", callback_data="overall_stats"),
        types.InlineKeyboardButton(f"{EMOJI['users']} Пользователи", callback_data="manage_users"),
        types.InlineKeyboardButton(f"{EMOJI['chats']} Чаты", callback_data="manage_chats"),
        types.InlineKeyboardButton(f"{EMOJI['channels']} Каналы", callback_data="manage_channels"),
        types.InlineKeyboardButton(f"{EMOJI['rocket']} Рассылка", callback_data="send_broadcast"),
        types.InlineKeyboardButton(f"{EMOJI['settings']} Настройки бота", callback_data="bot_settings")
    )
    
    text = f"{EMOJI['admin']} Панель суперадминистратора\n\n"
    text += f"{EMOJI['rocket']} Выберите раздел для управления:\n\n"
    text += f"{EMOJI['info']} Текущий статус:\n"
    text += f"- Пользователей: {len(users)}\n"
    text += f"- Чатов: {len(chats)}\n"
    text += f"- Каналов: {len(channels)}\n"
    
    bot.send_message(chat_id, text, reply_markup=markup)
    logger.info(f"Суперадминистратор открыл панель управления")

@bot.callback_query_handler(func=lambda call: call.data == "super_admin")
@super_admin_required
def callback_super_admin(call):
    show_super_admin_menu(call.message.chat.id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "list_users")
@super_admin_required
def handle_list_users(call):
    page = 0
    users_per_page = 10
    total_users = len(users)
    total_pages = (total_users - 1) // users_per_page + 1

    def get_user_list_markup(page):
        markup = types.InlineKeyboardMarkup(row_width=1)
        start = page * users_per_page
        end = min(start + users_per_page, total_users)
        for user in list(users.values())[start:end]:
            user_info = f"{user['first_name']} {user['last_name'] or ''} (@{user['username'] or 'нет username'})"
            markup.add(types.InlineKeyboardButton(user_info, callback_data=f"user:{user['id']}"))
        
        nav_markup = types.InlineKeyboardMarkup(row_width=3)
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"user_list_page:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"user_list_page:{page+1}"))
        nav_markup.add(*nav_buttons)
        
        markup.add(*nav_markup.keyboard[0])
        markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_users"))
        return markup

    text = f"{EMOJI['users']} Список пользователей (страница {page+1}/{total_pages}):\n\n"
    text += f"{EMOJI['info']} Всего пользователей: {total_users}\n"
    text += f"{EMOJI['info']} Нажмите на пользователя для подробной информации"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=get_user_list_markup(page))
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел список пользователей")

@bot.callback_query_handler(func=lambda call: call.data.startswith("user_list_page:"))
@super_admin_required
def handle_user_list_page(call):
    try:
        page = int(call.data.split(':')[1])
        users_per_page = 10
        total_users = len(users)
        total_pages = (total_users - 1) // users_per_page + 1

        def get_user_list_markup(page):
            markup = types.InlineKeyboardMarkup(row_width=1)
            start = page * users_per_page
            end = min(start + users_per_page, total_users)
            
            # Получаем список пользователей для текущей страницы
            current_users = list(users.values())[start:end]
            
            for user in current_users:
                user_info = f"{user['first_name']} {user['last_name'] or ''} (@{user['username'] or 'нет username'})"
                markup.add(types.InlineKeyboardButton(user_info, callback_data=f"user:{user['id']}"))
            
            # Добавляем кнопки навигации
            nav_buttons = []
            if page > 0:
                nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"user_list_page:{page-1}"))
            nav_buttons.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
            if page < total_pages - 1:
                nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"user_list_page:{page+1}"))
            
            markup.add(*nav_buttons)
            markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_users"))
            return markup

        text = f"{EMOJI['users']} Список пользователей (страница {page+1}/{total_pages}):\n\n"
        text += f"{EMOJI['info']} Всего пользователей: {total_users}\n"
        text += f"{EMOJI['info']} Нажмите на пользователя для подробной информации"

        try:
            # Пробуем отредактировать сообщение
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=get_user_list_markup(page)
            )
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e):
                # Если сообщение не изменилось, просто игнорируем ошибку
                pass
            else:
                raise

        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Ошибка при переключении страницы: {e}")
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка при переключении страницы"
        )

@bot.callback_query_handler(func=lambda call: call.data == "search_user")
@super_admin_required
def handle_search_user(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['search']} Введите username, ID или часть имени пользователя для поиска:")
    bot.register_next_step_handler(msg, search_user_step)
    logger.info(f"Суперадминистратор {call.from_user.id} начал поиск пользователя")

def search_user_step(message):
    search_query = message.text.lower()
    found_users = []
    for user_id, user in users.items():
        if (search_query in (user['username'] or '').lower() or 
            search_query in (user['first_name'] or '').lower() or 
            search_query in (user['last_name'] or '').lower() or
            search_query == user['id']):
            found_users.append(user)
    
    if not found_users:
        bot.reply_to(message, f"{EMOJI['error']} Пользователи не найдены.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for user in found_users[:10]:  # Ограничиваем результаты поиска до 10
        user_info = f"{user['first_name']} {user['last_name'] or ''} (@{user['username'] or 'нет username'})"
        markup.add(types.InlineKeyboardButton(user_info, callback_data=f"user:{user['id']}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_users"))

    bot.send_message(message.chat.id, f"{EMOJI['success']} Найденные пользователи:", reply_markup=markup)
    logger.info(f"Суперадминистратор {message.from_user.id} выполнил поиск пользователей")

@bot.callback_query_handler(func=lambda call: call.data.startswith("user:"))
@super_admin_required
def handle_user_info(call):
    user_id = call.data.split(":")[1]
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Пользователь не найден.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if user.get('blocked', False):
        markup.add(types.InlineKeyboardButton(f"{EMOJI['unblock']} Разблокировать", callback_data=f"unblock_user:{user_id}"))
    else:
        markup.add(types.InlineKeyboardButton(f"{EMOJI['block']} Заблокировать", callback_data=f"block_user:{user_id}"))
    
    markup.add(types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить рейтинг", callback_data=f"edit_rating:{user_id}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['edit']} Написать", callback_data=f"message_user:{user_id}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="list_users"))
    
    user_info = f"{EMOJI['users']} Информация о пользователе:\n\n"
    user_info += f"ID: {user['id']}\n"
    user_info += f"Имя: {user['first_name']} {user['last_name'] or ''}\n"
    user_info += f"Username: @{user['username'] or 'Отсутствует'}\n"
    user_info += f"Рейтинг: {calculate_rating(user)}\n"
    user_info += f"Заблокирован: {'Да' if user.get('blocked', False) else 'Нет'}\n"
    user_info += f"Дата регистрации: {user['joined_at']}\n\n"
    user_info += f"Чаты пользователя:\n"
    for chat_id in user.get('chats', []):
        chat = chats.get(chat_id, {})
        user_info += f"- {chat.get('title', 'Неизвестный чат')}\n"
    user_info += f"\nКаналы пользователя:\n"
    for channel_id in user.get('channels', []):
        channel = channels.get(channel_id, {})
        user_info += f"- {channel.get('title', 'Неизвестный канал')}\n"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=user_info, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел информацию о пользователе {user_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("block_user:") or call.data.startswith("unblock_user:"))
@super_admin_required
def handle_toggle_block_user(call):
    action, user_id = call.data.split(":")
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Пользователь не найден.")
        return
    
    if action == "block_user":
        user['blocked'] = True
        status = "заблокирован"
    else:
        user['blocked'] = False
        status = "разблокирован"
    
    save_data()
    bot.answer_callback_query(call.id, f"{EMOJI['success']} Пользователь успешно {status}.")
    
    handle_user_info(types.CallbackQuery(
        from_user=call.from_user,
        message=call.message,
        data=f"user:{user_id}"
    ))
    logger.info(f"Суперадминистратор {call.from_user.id} {status} пользователя {user_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_rating:"))
@super_admin_required
def handle_edit_rating(call):
    user_id = call.data.split(":")[1]
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Пользователь не найден.")
        return
    
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите новое значение рейтинга для пользователя:")
    bot.register_next_step_handler(msg, process_edit_rating, user_id)
    logger.info(f"Суперадминистратор {call.from_user.id} начал процесс изменения рейтинга пользователя {user_id}")

def process_edit_rating(message, user_id):
    try:
        new_rating = int(message.text)
        if new_rating < 0:
            raise ValueError
        
        user = users.get(user_id)
        if not user:
            bot.reply_to(message, f"{EMOJI['error']} Пользователь не найден.")
            return
        
        old_rating = calculate_rating(user)
        user['messages_count'] = new_rating  # Используем messages_count как основу для рейтинга
        user['reactions_received'] = 0  # Сбрасываем reactions_received
        save_data()
        
        bot.reply_to(message, f"{EMOJI['success']} Рейтинг пользователя успешно изменен с {old_rating} на {new_rating}")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил рейтинг пользователя {user_id} с {old_rating} на {new_rating}")
    except ValueError:
        bot.reply_to(message, f"{EMOJI['error']} Некорректное значение рейтинга. Пожалуйста, введите положительное целое число.")
    
    handle_user_info(types.CallbackQuery(
        from_user=message.from_user,
        message=message,
        data=f"user:{user_id}"
    ))

@bot.callback_query_handler(func=lambda call: call.data == "manage_chats")
@super_admin_required
def handle_manage_chats(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['chats']} Список чатов", callback_data="list_chats"),
        types.InlineKeyboardButton(f"{EMOJI['search']} Найти чат", callback_data="search_chat"),
        types.InlineKeyboardButton(f"{EMOJI['stats']} Статистика чатов", callback_data="chat_stats"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="super_admin")
    )
    
    text = f"{EMOJI['chats']} Управление чатами\n\n"
    text += f"Всего чатов: {len(chats)}\n"
    text += f"Активных чатов: {sum(1 for chat in chats.values() if chat.get('is_active', True))}\n\n"
    text += f"{EMOJI['thinking']} Выберите действие:"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} открыл меню управления чатами")

def safe_edit_message(chat_id, message_id, text, reply_markup=None):
    """Безопасное редактирование сообщения"""
    try:
        return bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    except telebot.apihelper.ApiException as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            raise

def safe_answer_callback(callback_query_id, text=None, show_alert=False):
    """Безопасный ответ на callback"""
    try:
        bot.answer_callback_query(callback_query_id, text=text, show_alert=show_alert)
    except telebot.apihelper.ApiException as e:
        if "query is too old" not in str(e):
            logger.error(f"Ошибка при ответе на callback: {e}")
            raise

@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_chat:"))
def handle_manage_chat(call):
    """Обработка нажатия на чат в списке пользователя"""
    try:
        chat_id = call.data.split(":")[1]
        user_id = str(call.from_user.id)
        
        if chat_id not in chats:
            safe_answer_callback(call.id, "Чат не найден")
            return
            
        chat = chats[chat_id]
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Добавляем кнопки управления
        buttons = [
            ("🔔 Уведомления", f"chat_notifications:{chat_id}"),
            ("ℹ️ Информация", f"chat_info_user:{chat_id}"),
            ("📊 Статистика", f"chat_stats_user:{chat_id}"),
            ("👋 Приветствие", f"welcome_settings:{chat_id}"),
            ("📝 Отправить сообщение", f"send_message:{chat_id}"),
            ("🔙 Назад", "my_chats")
        ]
        
        # Создаем кнопки в два столбца
        for i in range(0, len(buttons), 2):
            row_buttons = [types.InlineKeyboardButton(text, callback_data=cb) 
                         for text, cb in buttons[i:min(i+2, len(buttons))]]
            markup.add(*row_buttons)
        
        text = f"💬 Управление чатом {chat['title']}\n\n"
        text += f"Тип: {chat['type']}\n"
        text += f"Сообщений: {chat.get('messages_count', 0)}\n"
        text += f"Приветствие: {'Настроено ✅' if chat.get('welcome_message') else 'Стандартное ℹ️'}\n"
        text += f"Уведомления: {'Включены 🔔' if users[user_id].get('chat_notifications', {}).get(chat_id, True) else 'Выключены 🔕'}"
        
        safe_edit_message(call.message.chat.id, call.message.message_id, text, markup)
        safe_answer_callback(call.id)
        
    except Exception as e:
        logger.error(f"Ошибка при управлении чатом: {e}")
        try:
            safe_answer_callback(call.id, "Произошла ошибка")
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("welcome_settings:"))
def handle_welcome_settings(call):
    chat_id = call.data.split(":")[1]
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Шаблоны приветствий
    templates = [
        ("👋 Простое", f"set_welcome:{chat_id}:simple"),
        ("🌟 Креативное", f"set_welcome:{chat_id}:creative"),
        ("🤝 Деловое", f"set_welcome:{chat_id}:business"),
        ("✨ Своё", f"custom_welcome:{chat_id}")
    ]
    
    for title, callback in templates:
        markup.add(types.InlineKeyboardButton(title, callback_data=callback))
    
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data=f"manage_chat:{chat_id}"))
    
    text = "👋 Выберите тип приветственного сообщения:\n\n"
    text += "Simple: Привет, {username}! Добро пожаловать в чат!\n\n"
    text += "Creative: ✨ Ура! {username} присоединился к нашей компании! 🎉\n\n"
    text += "Business: Добрый день, {username}. Рады приветствовать вас.\n\n"
    text += "Custom: Создайте своё уникальное приветствие"
    
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    except telebot.apihelper.ApiException as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка при настройке приветствия: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_welcome:"))
def handle_set_welcome_template(call):
    chat_id = call.data.split(":")[1]
    template_type = call.data.split(":")[2]
    
    templates = {
        'simple': "👋 Привет, {username}! Добро пожаловать в чат!",
        'creative': "✨ Ура! {username} присоединился к нашей компании! 🎉\nНадеемся, тебе у нас понравится! 🌟",
        'business': "Добрый день, {username}.\nРады приветствовать вас в нашем сообществе.\nОзнакомьтесь, пожалуйста, с правилами чата."
    }
    
    if chat_id in chats:
        chats[chat_id]['welcome_message'] = templates[template_type]
        save_data()
        
        bot.answer_callback_query(
            call.id,
            "✅ Приветственное сообщение установлено!"
        )
        
        # Возвращаемся к управлению чатом
        handle_manage_chat(types.CallbackQuery(
            id='0',
            from_user=call.from_user,
            message=call.message,
            data=f"manage_chat:{chat_id}",
            chat_instance='0',
            json_string='{}'
        ))

@bot.callback_query_handler(func=lambda call: call.data.startswith("custom_welcome:"))
def handle_custom_welcome(call):
    chat_id = call.data.split(":")[1]
    msg = bot.send_message(
        call.message.chat.id,
        "✏️ Введите своё приветственное сообщение.\n\n"
        "Используйте {username} для подстановки имени пользователя.\n"
        "Поддерживаются эмодзи и форматирование."
    )
    bot.register_next_step_handler(msg, save_custom_welcome, chat_id)

def save_custom_welcome(message, chat_id):
    if chat_id in chats:
        chats[chat_id]['welcome_message'] = message.text
        save_data()
        
        bot.reply_to(
            message,
            "✅ Новое приветственное сообщение установлено!"
        )
        
        # Показываем пример
        example = message.text.replace("{username}", "Пользователь")
        bot.send_message(
            message.chat.id,
            "Пример приветствия:\n\n" + example
        )
        
        # Возвращаемся к управлению чатом
        show_chat_menu(message.chat.id, chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("send_message:"))
def handle_send_message(call):
    """Отправка сообщения в чат"""
    try:
        chat_id = call.data.split(":")[1]
        safe_answer_callback(call.id)  # Сразу отвечаем на callback
        
        msg = bot.send_message(
            call.message.chat.id,
            "📝 Введите сообщение для отправки в чат:"
        )
        bot.register_next_step_handler(msg, process_send_message, chat_id)
    except Exception as e:
        logger.error(f"Ошибка при подготовке к отправке сообщения: {e}")
        safe_answer_callback(call.id, "Не удалось начать отправку")

def process_send_message(message, chat_id):
    """Обработка введенного сообщения для отправки"""
    try:
        sent = bot.send_message(chat_id, message.text)
        if sent:
            bot.reply_to(message, "✅ Сообщение отправлено!")
        
        # Показываем меню чата
        show_chat_menu(message, chat_id)
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в чат: {e}")
        bot.reply_to(message, f"❌ Не удалось отправить сообщение: {str(e)}")

def show_chat_menu(message, chat_id):
    """Безопасный показ меню чата"""
    try:
        # Создаем новое сообщение вместо редактирования старого
        text = f"💬 Управление чатом {chats[chat_id]['title']}"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🔙 Вернуться к управлению", 
                                            callback_data=f"manage_chat:{chat_id}"))
        
        bot.send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка при показе меню чата: {e}")
        bot.send_message(message.chat.id, "❌ Не удалось показать меню чата")

def send_message_to_chat(message, chat_id):
    try:
        # Отправляем сообщение в чат
        sent = bot.send_message(chat_id, message.text)
        if sent:
            bot.reply_to(
                message,
                "✅ Сообщение успешно отправлено в чат!"
            )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Ошибка при отправке сообщения: {str(e)}"
        )
    
    # Возвращаемся к управлению чатом
    show_chat_menu(message.chat.id, chat_id)

def show_chat_menu(chat_id, target_chat_id):
    """Вспомогательная функция для показа меню чата"""
    try:
        handle_manage_chat(types.CallbackQuery(
            id='0',
            from_user=types.User(id=chat_id, is_bot=False, first_name="User"),
            message=types.Message(
                message_id=0,
                from_user=types.User(id=chat_id, is_bot=False, first_name="User"),
                date=0,
                chat=types.Chat(id=chat_id, type="private"),
                content_type="text",
                options={},
                json_string="{}"
            ),
            data=f"manage_chat:{target_chat_id}",
            chat_instance="0",
            json_string="{}"
        ))
    except Exception as e:
        logger.error(f"Ошибка при показе меню чата: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_info_user:"))
def handle_chat_info_user(call):
    """Информация о чате для пользователя"""
    try:
        chat_id = call.data.split(":")[1]
        chat = chats.get(chat_id)
        
        if not chat:
            bot.answer_callback_query(call.id, "Чат не найден")
            return
            
        text = f"{EMOJI['info']} Информация о чате:\n\n"
        text += f"Название: {chat['title']}\n"
        text += f"Тип: {chat['type']}\n"
        text += f"Сообщений: {chat.get('messages_count', 0)}\n"
        text += f"Дата добавления: {chat['created_at']}\n"
        text += f"Статус: {'Активен' if chat.get('is_active', True) else 'Неактивен'}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"manage_chat:{chat_id}"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Ошибка при показе информации о чате: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_stats_user:"))
def handle_chat_stats_user(call):
    """Статистика чата для пользователя"""
    try:
        chat_id = call.data.split(":")[1]
        chat = chats.get(chat_id)
        
        if not chat:
            bot.answer_callback_query(call.id, "Чат не найден")
            return
            
        text = f"{EMOJI['stats']} Статистика чата:\n\n"
        text += f"Всего сообщений: {chat.get('messages_count', 0)}\n"
        text += f"Участников: {len(chat.get('members', []))}\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"manage_chat:{chat_id}"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Ошибка при показе статистики чата: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_notifications:"))
def handle_chat_notifications(call):
    """Управление уведомлениями чата"""
    try:
        chat_id = call.data.split(":")[1]
        user_id = str(call.from_user.id)
        
        if user_id not in users or 'chat_notifications' not in users[user_id]:
            users[user_id]['chat_notifications'] = {}
        
        current_status = users[user_id]['chat_notifications'].get(chat_id, True)
        users[user_id]['chat_notifications'][chat_id] = not current_status
        save_data()
        
        new_status = users[user_id]['chat_notifications'][chat_id]
        bot.answer_callback_query(
            call.id,
            f"Уведомления {'включены' if new_status else 'выключены'}"
        )
        
        # Возвращаемся к управлению чатом
        handle_manage_chat(types.CallbackQuery(
            id='0',
            from_user=call.from_user,
            message=call.message,
            data=f"manage_chat:{chat_id}",
            chat_instance='0',
            json_string='{}'
        ))
        
    except Exception as e:
        logger.error(f"Ошибка при управлении уведомлениями: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == "list_chats")
@super_admin_required
def handle_list_chats(call):
    page = 0
    chats_per_page = 10
    total_chats = len(chats)
    total_pages = (total_chats - 1) // chats_per_page + 1

    def get_chat_list_markup(page):
        markup = types.InlineKeyboardMarkup(row_width=1)
        start = page * chats_per_page
        end = min(start + chats_per_page, total_chats)
        for chat in list(chats.values())[start:end]:
            chat_info = f"{chat['title']} ({chat['id']})"
            markup.add(types.InlineKeyboardButton(chat_info, callback_data=f"chat_info:{chat['id']}"))
        
        nav_markup = types.InlineKeyboardMarkup(row_width=3)
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"chat_list_page:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"chat_list_page:{page+1}"))
        nav_markup.add(*nav_buttons)
        
        markup.add(*nav_markup.keyboard[0])
        markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_chats"))
        return markup

    text = f"{EMOJI['chats']} Список чатов (страница {page+1}/{total_pages}):\n\n"
    text += f"{EMOJI['info']} Всего чатов: {total_chats}\n"
    text += f"{EMOJI['info']} Нажмите на чат для подробной информации"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=get_chat_list_markup(page))
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел список чатов")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_info:"))
@super_admin_required
def handle_chat_info(call):
    chat_id = call.data.split(":")[1]
    chat = chats.get(chat_id)
    
    if not chat:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Чат не найден.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить название", callback_data=f"rename_chat:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить описание", callback_data=f"set_chat_description:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить username", callback_data=f"change_username:chat:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['delete']} Удалить чат", callback_data=f"delete_chat:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['users']} Участники", callback_data=f"chat_members:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['stats']} Статистика", callback_data=f"chat_stats:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="list_chats")
    )
    
    chat_info = f"{EMOJI['chats']} Информация о чате:\n\n"
    chat_info += f"ID: {chat['id']}\n"
    chat_info += f"Название: {chat['title']}\n"
    chat_info += f"Описание: {chat.get('description', 'Не задано')}\n"
    chat_info += f"Владелец: {chat.get('owner_id', 'Не задан')}\n"
    chat_info += f"Количество участников: {len(chat.get('members', []))}\n"
    chat_info += f"Дата создания: {chat.get('created_at', 'Неизвестно')}\n"
    chat_info += f"Активность: {'Активен' if chat.get('is_active', True) else 'Неактивен'}\n\n"
    chat_info += f"{EMOJI['thinking']} Выберите действие:"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=chat_info, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел информацию о чате {chat_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("rename_chat:"))
@super_admin_required
def handle_rename_chat(call):
    chat_id = call.data.split(":")[1]
    
    try:
        # Получаем актуальную информацию о чате
        chat_info = bot.get_chat(chat_id)
        
        # Если чат был обновлен до супергруппы, обновляем ID
        if chat_info.type == 'supergroup' and chat_info.id != int(chat_id):
            old_chat_id = chat_id
            chat_id = str(chat_info.id)
            # Обновляем ID в базе данных
            if old_chat_id in chats:
                chats[chat_id] = chats.pop(old_chat_id)
                chats[chat_id]['id'] = chat_id
                save_data()
        
        # Проверяем права бота
        bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
        
        # Логируем информацию о правах для отладки
        logger.info(f"Права бота в чате {chat_id}:")
        logger.info(f"Status: {bot_member.status}")
        logger.info(f"Can change info: {getattr(bot_member, 'can_change_info', None)}")
        
        if not bot_member.can_change_info:
            bot.answer_callback_query(
                call.id,
                f"{EMOJI['error']} У бота нет прав на изменение информации о чате. "
                f"Статус: {bot_member.status}"
            )
            return
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.from_user.id,
            f"{EMOJI['edit']} Введите новое название для чата:"
        )
        bot.register_next_step_handler(msg, rename_chat_step, chat_id)
        
    except Exception as e:
        logger.error(f"Ошибка при запросе переименования чата {chat_id}: {str(e)}")
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка: {str(e)}"
        )

def rename_chat_step(message, chat_id):
    new_title = message.text.strip()
    if len(new_title) < 1 or len(new_title) > 255:
        bot.reply_to(
            message,
            f"{EMOJI['error']} Название чата должно содержать от 1 до 255 символов."
        )
        return
    
    try:
        # Пытаемся изменить название
        result = bot.set_chat_title(chat_id, new_title)
        
        if result:
            # Обновляем локальные данные
            if chat_id in chats:
                chats[chat_id]['title'] = new_title
                save_data()
            
            bot.reply_to(
                message,
                f"{EMOJI['success']} Название чата успешно изменено на «{new_title}»"
            )
        else:
            raise Exception("Не удалось изменить название")
            
    except Exception as e:
        error_text = str(e)
        if "not enough rights" in error_text:
            # Проверяем текущие права бота
            try:
                bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
                rights_info = (
                    f"\n\nТекущие права бота:\n"
                    f"Статус: {bot_member.status}\n"
                    f"Может изменять информацию: {getattr(bot_member, 'can_change_info', 'Нет')}"
                )
            except:
                rights_info = ""
                
            bot.reply_to(
                message,
                f"{EMOJI['error']} У бота недостаточно прав для изменения названия чата.{rights_info}"
            )
        else:
            bot.reply_to(
                message,
                f"{EMOJI['error']} Ошибка при изменении названия: {error_text}"
            )
        logger.error(f"Ошибка при изменении названия чата {chat_id}: {error_text}")

@bot.callback_query_handler(func=lambda call: call.data == "chat_stats")
@super_admin_required
def handle_chat_stats(call):
    total_chats = len(chats)
    active_chats = sum(1 for chat in chats.values() if chat.get('is_active', True))
    total_messages = sum(chat.get('messages_count', 0) for chat in chats.values())
    
    stats_text = f"{EMOJI['stats']} Статистика чатов:\n\n"
    stats_text += f"Всего чатов: {total_chats}\n"
    stats_text += f"Активных чатов: {active_chats}\n"
    stats_text += f"Всего сообщений: {total_messages}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_chats"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=stats_text, 
                          reply_markup=markup)
    
@bot.callback_query_handler(func=lambda call: call.data == "bot_settings")
@super_admin_required
def handle_bot_settings(call):
    try:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(f"{EMOJI['info']} Информация о боте", callback_data="bot_info"),
            types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить имя бота", callback_data="change_bot_name"),
            types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить описание", callback_data="change_bot_description"),
            types.InlineKeyboardButton(f"{EMOJI['settings']} Настройки приватности", callback_data="privacy_settings"),
            types.InlineKeyboardButton(f"{EMOJI['back']} Вернуться в меню", callback_data="super_admin")
        )
        
        text = f"{EMOJI['settings']} Настройки бота\n\n"
        text += f"{EMOJI['thinking']} Выберите действие:"
        
        bot.edit_message_text(chat_id=call.message.chat.id, 
                              message_id=call.message.message_id, 
                              text=text, 
                              reply_markup=markup)
        logger.info(f"Суперадминистратор {call.from_user.id} открыл настройки бота")
    except Exception as e:
        logger.error(f"Ошибка при обработке настроек бота: {str(e)}")
        bot.answer_callback_query(call.id, text="Произошла ошибка. Попробуйте еще раз.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_members:"))
@super_admin_required
def handle_chat_members(call):
    chat_id = call.data.split(":")[1]
    chat = chats.get(chat_id)
    
    if not chat:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Чат не найден.")
        return
    
    members = chat.get('members', [])
    members_text = f"{EMOJI['users']} Участники чата {chat['title']}:\n\n"
    
    for member_id in members[:10]:  # Показываем только первых 10 участников
        user = users.get(member_id, {})
        members_text += f"- {user.get('first_name', 'Unknown')} {user.get('last_name', '')} (@{user.get('username', 'N/A')})\n"
    
    if len(members) > 10:
        members_text += f"\nИ еще {len(members) - 10} участников..."
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Массовое удаление", callback_data=f"mass_remove:{chat_id}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"chat_info:{chat_id}"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=members_text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел список участников чата {chat_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_chat_description:"))
@super_admin_required
def handle_set_chat_description(call):
    chat_id = call.data.split(":")[1]
    
    try:
        # Проверяем права бота
        bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
        if not bot_member.can_change_info:
            bot.answer_callback_query(
                call.id,
                f"{EMOJI['error']} У бота нет прав на изменение информации о чате."
            )
            return
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите новое описание для чата:")
        bot.register_next_step_handler(msg, set_chat_description_step, chat_id)
        logger.info(f"Суперадминистратор {call.from_user.id} начал процесс изменения описания чата {chat_id}")
        
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка при проверке прав бота: {str(e)}"
        )
        logger.error(f"Ошибка при проверке прав бота: {str(e)}")

def set_chat_description_step(message, chat_id):
    new_description = message.text.strip()
    if len(new_description) > 255:
        bot.reply_to(message, f"{EMOJI['error']} Описание чата не должно превышать 255 символов.")
        return
    
    try:
        # Пытаемся изменить описание чата через API Telegram
        bot.set_chat_description(chat_id, new_description)
        
        # Обновляем локальные данные
        if chat_id in chats:
            chats[chat_id]['description'] = new_description
            save_data()
        
        bot.reply_to(message, f"{EMOJI['success']} Описание чата успешно изменено.")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил описание чата {chat_id}")
        
        # Обновляем информацию в меню
        try:
            fake_call = types.CallbackQuery(
                id='0',
                from_user=message.from_user,
                chat_instance='0',
                message=message,
                data=f"chat_info:{chat_id}",
                json_string='{}'
            )
            handle_chat_info(fake_call)
        except telebot.apihelper.ApiTelegramException as e:
            if "message can't be edited" in str(e):
                # Если не можем отредактировать сообщение, отправляем новое
                bot.send_message(
                    message.chat.id,
                    f"{EMOJI['success']} Описание успешно изменено. Используйте меню для просмотра обновленной информации."
                )
            else:
                raise
                
    except telebot.apihelper.ApiException as e:
        error_text = str(e)
        if "not enough rights" in error_text:
            bot.reply_to(message, f"{EMOJI['error']} У бота недостаточно прав для изменения описания чата.")
        else:
            bot.reply_to(message, f"{EMOJI['error']} Ошибка при изменении описания: {error_text}")
        logger.error(f"Ошибка при изменении описания чата {chat_id}: {error_text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("channel_detailed_stats:"))
@super_admin_required
def handle_channel_detailed_stats(call):
    channel_id = call.data.split(":")[1]
    
    try:
        # Получаем актуальную информацию о канале
        chat_info = bot.get_chat(channel_id)
        member_count = bot.get_chat_member_count(channel_id)
        
        # Собираем статистику сообщений (если есть доступ к истории)
        try:
            messages = 0
            for message in bot.get_chat_history(channel_id, limit=100):
                messages += 1
        except:
            messages = "Нет доступа к истории"
        
        # Собираем статистику администраторов
        admins = bot.get_chat_administrators(channel_id)
        admin_count = len(admins)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                f"{EMOJI['back']} К информации о канале", 
                callback_data=f"channel_info:{channel_id}"
            )
        )
        
        stats_text = f"{EMOJI['stats']} Подробная статистика канала {chat_info.title}:\n\n"
        stats_text += f"Подписчиков: {member_count}\n"
        stats_text += f"Администраторов: {admin_count}\n"
        stats_text += f"Последних сообщений: {messages}\n"
        stats_text += f"Публичная ссылка: {'Есть' if chat_info.username else 'Нет'}\n"
        stats_text += f"Приватный канал: {'Да' if chat_info.type == 'private' else 'Нет'}\n"
        
        if hasattr(chat_info, 'linked_chat_id') and chat_info.linked_chat_id:
            stats_text += f"Привязанная группа: Есть\n"
        
        # Добавляем информацию о правах бота
        bot_member = bot.get_chat_member(channel_id, bot.get_me().id)
        stats_text += f"\nПрава бота в канале:\n"
        stats_text += f"• Изменение информации: {'✅' if bot_member.can_change_info else '❌'}\n"
        stats_text += f"• Публикация сообщений: {'✅' if bot_member.can_post_messages else '❌'}\n"
        stats_text += f"• Редактирование сообщений: {'✅' if bot_member.can_edit_messages else '❌'}\n"
        stats_text += f"• Удаление сообщений: {'✅' if bot_member.can_delete_messages else '❌'}\n"
        stats_text += f"• Управление подписчиками: {'✅' if bot_member.can_invite_users else '❌'}\n"
        
        bot.edit_message_text(
            text=stats_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        
    except telebot.apihelper.ApiException as e:
        error_text = str(e)
        if "chat not found" in error_text:
            text = f"{EMOJI['error']} Канал не найден"
        elif "not enough rights" in error_text:
            text = f"{EMOJI['error']} Недостаточно прав для получения статистики"
        else:
            text = f"{EMOJI['error']} Ошибка при получении статистики: {error_text}"
        
        bot.answer_callback_query(call.id, text)
        logger.error(f"Ошибка при получении статистики канала {channel_id}: {error_text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("channel_subscribers:"))
@super_admin_required
def handle_channel_subscribers(call):
    channel_id = call.data.split(":")[1]
    
    try:
        # Проверяем права бота
        bot_member = bot.get_chat_member(channel_id, bot.get_me().id)
        if not bot_member.can_invite_users:
            bot.answer_callback_query(
                call.id,
                f"{EMOJI['error']} У бота нет прав на управление подписчиками."
            )
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                f"{EMOJI['users']} Добавить подписчиков", 
                callback_data=f"add_subscribers:{channel_id}"
            ),
            types.InlineKeyboardButton(
                f"{EMOJI['block']} Заблокировать пользователей", 
                callback_data=f"block_channel_users:{channel_id}"
            ),
            types.InlineKeyboardButton(
                f"{EMOJI['unblock']} Разблокированные пользователи", 
                callback_data=f"unblock_channel_users:{channel_id}"
            ),
            types.InlineKeyboardButton(
                f"{EMOJI['back']} К информации о канале", 
                callback_data=f"channel_info:{channel_id}"
            )
        )
        
        text = f"{EMOJI['users']} Управление подписчиками канала\n\n"
        text += f"Выберите действие:"
        
        bot.edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка при открытии меню управления подписчиками: {str(e)}"
        )
        logger.error(f"Ошибка при открытии меню управления подписчиками канала {channel_id}: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("add_subscribers:"))
@super_admin_required
def handle_add_subscribers(call):
    channel_id = call.data.split(":")[1]
    
    try:
        # Генерируем пригласительную ссылку
        invite_link = bot.create_chat_invite_link(
            channel_id,
            member_limit=100,  # Ограничение на количество использований
            expire_date=int(time.time()) + 3600  # Срок действия 1 час
        )
        
        text = f"{EMOJI['success']} Создана пригласительная ссылка:\n"
        text += f"{invite_link.invite_link}\n\n"
        text += f"Ограничение: 100 пользователей\n"
        text += f"Срок действия: 1 час"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                f"{EMOJI['back']} Назад", 
                callback_data=f"channel_subscribers:{channel_id}"
            )
        )
        
        bot.edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        
    except telebot.apihelper.ApiException as e:
        error_text = str(e)
        if "not enough rights" in error_text:
            text = f"{EMOJI['error']} У бота нет прав на создание пригласительной ссылки"
        else:
            text = f"{EMOJI['error']} Ошибка при создании ссылки: {error_text}"
        
        bot.answer_callback_query(call.id, text)
        logger.error(f"Ошибка при создании пригласительной ссылки для канала {channel_id}: {error_text}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("block_channel_users:"))
@super_admin_required
def handle_block_channel_users(call):
    channel_id = call.data.split(":")[1]
    
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.from_user.id,
        f"{EMOJI['block']} Отправьте список username пользователей для блокировки (через запятую):"
    )
    bot.register_next_step_handler(msg, process_block_channel_users, channel_id)

def process_block_channel_users(message, channel_id):
    usernames = [username.strip() for username in message.text.split(',')]
    blocked_count = 0
    errors_count = 0
    
    for username in usernames:
        try:
            # Получаем информацию о пользователе
            user_info = bot.get_chat(username)
            # Блокируем пользователя
            bot.ban_chat_member(channel_id, user_info.id)
            blocked_count += 1
        except Exception as e:
            errors_count += 1
            logger.error(f"Ошибка при блокировке пользователя {username}: {str(e)}")
    
    report = f"{EMOJI['info']} Результаты блокировки:\n"
    report += f"Успешно заблокировано: {blocked_count}\n"
    if errors_count > 0:
        report += f"Ошибок: {errors_count}"
    
    bot.reply_to(message, report)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_channel:"))
@super_admin_required
def handle_delete_channel(call):
    channel_id = call.data.split(":")[1]
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            f"{EMOJI['success']} Да, удалить", 
            callback_data=f"confirm_delete_channel:{channel_id}"
        ),
        types.InlineKeyboardButton(
            f"{EMOJI['error']} Отмена", 
            callback_data=f"channel_info:{channel_id}"
        )
    )
    
    warning_text = f"{EMOJI['warning']} Вы уверены, что хотите удалить этот канал из базы бота?\n\n"
    warning_text += "❗️ Это действие:\n"
    warning_text += "• Удалит канал из базы данных бота\n"
    warning_text += "• Отвяжет всех администраторов\n"
    warning_text += "• Удалит всю статистику\n\n"
    warning_text += "‼️ Бот останется в канале, но потеряет все данные о нём"
    
    bot.edit_message_text(
        text=warning_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_channel:"))
@super_admin_required
def handle_confirm_delete_channel(call):
    channel_id = call.data.split(":")[1]
    
    try:
        # Проверяем существование канала
        if channel_id not in channels:
            bot.answer_callback_query(call.id, f"{EMOJI['error']} Канал не найден в базе данных.")
            return
        
        channel_info = channels[channel_id]
        
        # Удаляем канал из списков у всех пользователей
        for user_id in users:
            if 'channels' in users[user_id] and channel_id in users[user_id]['channels']:
                users[user_id]['channels'].remove(channel_id)
        
        # Удаляем канал из базы
        del channels[channel_id]
        save_data()
        
        # Отправляем подтверждение
        success_text = f"{EMOJI['success']} Канал {channel_info.get('title', 'Неизвестный')} успешно удален из базы данных."
        bot.edit_message_text(
            text=success_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        # Возвращаемся к списку каналов
        time.sleep(2)  # Даем время прочитать сообщение
        handle_manage_channels(call)
        
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка при удалении канала: {str(e)}"
        )
        logger.error(f"Ошибка при удалении канала {channel_id}: {str(e)}")

# Добавим обработку служебных сообщений в каналах
@bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document'])
def handle_channel_post(message):
    channel_id = str(message.chat.id)
    
    # Если канал не в базе, добавляем его
    if channel_id not in channels:
        try:
            chat_info = bot.get_chat(channel_id)
            channels[channel_id] = {
                'id': channel_id,
                'title': chat_info.title,
                'username': chat_info.username,
                'description': chat_info.description,
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'posts_count': 0,
                'views_count': 0
            }
        except Exception as e:
            logger.error(f"Ошибка при добавлении нового канала: {str(e)}")
            return
    
    # Обновляем статистику
    channels[channel_id]['posts_count'] = channels[channel_id].get('posts_count', 0) + 1
    save_data()

# Добавим функцию для проверки прав бота в канале
def check_bot_channel_rights(channel_id):
    try:
        bot_member = bot.get_chat_member(channel_id, bot.get_me().id)
        rights = {
            'can_change_info': bot_member.can_change_info,
            'can_post_messages': bot_member.can_post_messages,
            'can_edit_messages': bot_member.can_edit_messages,
            'can_delete_messages': bot_member.can_delete_messages,
            'can_invite_users': bot_member.can_invite_users,
            'is_admin': bot_member.status in ['administrator', 'creator']
        }
        return rights
    except Exception as e:
        logger.error(f"Ошибка при проверке прав бота в канале {channel_id}: {str(e)}")
        return None

# Добавим функцию периодического обновления статистики каналов
def update_channels_stats():
    for channel_id in channels.keys():
        try:
            chat_info = bot.get_chat(channel_id)
            member_count = bot.get_chat_member_count(channel_id)
            
            channels[channel_id].update({
                'title': chat_info.title,
                'username': chat_info.username,
                'description': chat_info.description,
                'member_count': member_count,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики канала {channel_id}: {str(e)}")
            continue
    
    save_data()
    logger.info("Статистика каналов обновлена")

# Добавим команду для ручного обновления статистики
@bot.message_handler(commands=['update_stats'])
@super_admin_required
def handle_update_stats(message):
    try:
        bot.reply_to(message, f"{EMOJI['info']} Начинаю обновление статистики каналов...")
        update_channels_stats()
        bot.reply_to(message, f"{EMOJI['success']} Статистика каналов успешно обновлена!")
    except Exception as e:
        bot.reply_to(message, f"{EMOJI['error']} Ошибка при обновлении статистики: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("mass_remove:"))
@super_admin_required
def handle_mass_remove(call):
    chat_id = call.data.split(":")[1]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Удалить по никам", callback_data=f"remove_by_username:{chat_id}"),
        types.InlineKeyboardButton("Удалить всех", callback_data=f"remove_all:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"chat_members:{chat_id}")
    )
    bot.edit_message_text("Выберите способ удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_by_username:"))
@super_admin_required
def handle_remove_by_username(call):
    chat_id = call.data.split(":")[1]
    msg = bot.send_message(call.message.chat.id, "Введите ники пользователей для удаления через запятую:")
    bot.register_next_step_handler(msg, process_remove_by_username, chat_id)

def process_remove_by_username(message, chat_id):
    usernames = [username.strip() for username in message.text.split(',')]
    removed = 0
    
    for username in usernames:
        try:
            # Ищем пользователя в базе
            user_id = None
            for uid, user in users.items():
                if user.get('username') == username.replace('@', ''):
                    user_id = uid
                    break
                    
            if user_id:
                # Применяем тот же агрессивный метод
                bot.restrict_chat_member(
                    chat_id, 
                    user_id,
                    permissions=types.ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_polls=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                        can_invite_users=False
                    ),
                    until_date=int(time.time()) + 31536000
                )
                bot._MakeRequest('banChatMember', {
                    'chat_id': chat_id,
                    'user_id': user_id,
                    'revoke_messages': True
                })
                
                # Удаляем из базы
                if user_id in chats[str(chat_id)]['members']:
                    chats[str(chat_id)]['members'].remove(user_id)
                removed += 1
                
        except Exception as e:
            continue
            
    save_data()
    bot.reply_to(message, f"✅ Удалено пользователей: {removed}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_all:"))
@super_admin_required
def handle_remove_all(call):
    try:
        raw_chat_id = call.data.split(":")[1]
        
        # Конвертируем ID чата в правильный формат
        if raw_chat_id.startswith('-100'):
            chat_id = int(raw_chat_id)
        else:
            chat_id = int(f'-100{raw_chat_id.replace("-", "")}')

        # Проверяем существование чата и права бота
        try:
            chat_info = bot.get_chat(chat_id)
            if not chat_info:
                raise Exception("Чат не найден")
        except Exception as e:
            logger.error(f"Ошибка получения информации о чате: {e}")
            raise Exception("Не удалось получить доступ к чату")

        # Проверяем права бота
        try:
            bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
            if not bot_member.can_restrict_members:
                raise Exception("У бота нет прав на ограничение участников")
        except Exception as e:
            logger.error(f"Ошибка проверки прав бота: {e}")
            raise Exception("Не удалось проверить права бота")

        # Получаем список администраторов
        admins = []
        try:
            admin_list = bot.get_chat_administrators(chat_id)
            admins = [str(admin.user.id) for admin in admin_list]
            logger.info(f"Найдено {len(admins)} админов в чате {chat_id}")
        except Exception as e:
            logger.error(f"Ошибка получения списка админов: {e}")
            raise Exception("Не удалось получить список администраторов")

        # Создаём сообщение о прогрессе
        progress_msg = bot.edit_message_text(
            f"{EMOJI['info']} Начинаю удаление участников...",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🛑 Отмена", callback_data=f"cancel_remove:{raw_chat_id}")
            )
        )

        # Получаем текущее количество участников
        try:
            member_count = bot.get_chat_member_count(chat_id)
            logger.info(f"Всего участников в чате: {member_count}")
        except Exception as e:
            logger.error(f"Ошибка получения количества участников: {e}")
            raise Exception("Не удалось получить количество участников")

        removed = 0
        failed = 0
        skipped = len(admins)

        # Список для хранения ID участников
        member_ids = []

        # Пробуем получить участников разными способами
        try:
            # Метод 1: Через message_thread_id (для супергрупп)
            if hasattr(chat_info, 'message_thread_id'):
                thread_id = chat_info.message_thread_id
                for i in range(1, member_count + 10):
                    try:
                        member = bot.get_chat_member(chat_id, i)
                        if member.user.id not in member_ids:
                            member_ids.append(member.user.id)
                    except:
                        continue

            # Метод 2: Прямой перебор последних известных ID
            recent_users = set()
            try:
                for user_id in range(member_count * 10):
                    try:
                        member = bot.get_chat_member(chat_id, user_id)
                        if member and member.user and member.user.id not in recent_users:
                            recent_users.add(member.user.id)
                            if len(recent_users) >= member_count:
                                break
                    except:
                        continue
                member_ids.extend(list(recent_users))
            except:
                pass

        except Exception as e:
            logger.error(f"Ошибка при сборе участников: {e}")

        # Удаляем участников
        for user_id in member_ids:
            try:
                str_user_id = str(user_id)
                if str_user_id not in admins and str_user_id != str(bot.get_me().id):
                    bot.ban_chat_member(chat_id, user_id)
                    bot.unban_chat_member(chat_id, user_id)
                    removed += 1

                    # Обновляем прогресс
                    if removed % 5 == 0:
                        try:
                            bot.edit_message_text(
                                f"{EMOJI['info']} Удаление участников...\n\n"
                                f"Удалено: {removed}\n"
                                f"Пропущено: {skipped}\n"
                                f"Ошибок: {failed}\n"
                                f"Прогресс: {min(100, int(removed * 100 / (member_count - skipped)))}%",
                                progress_msg.chat.id,
                                progress_msg.message_id,
                                reply_markup=types.InlineKeyboardMarkup().add(
                                    types.InlineKeyboardButton("🛑 Отмена", callback_data=f"cancel_remove:{raw_chat_id}")
                                )
                            )
                        except Exception as e:
                            logger.error(f"Ошибка обновления прогресса: {e}")

            except Exception as e:
                if "USER_NOT_FOUND" not in str(e) and "USER_ID_INVALID" not in str(e):
                    failed += 1
                    logger.error(f"Ошибка при удалении пользователя {user_id}: {e}")

        # Финальный отчёт
        final_text = (
            f"{EMOJI['success']} Процесс завершен!\n\n"
            f"Всего обработано: {len(member_ids)}\n"
            f"Успешно удалено: {removed}\n"
            f"Пропущено админов: {skipped}\n"
            f"Ошибок: {failed}"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"chat_members:{raw_chat_id}"))
        
        bot.edit_message_text(
            final_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Exception as e:
        error_msg = f"Критическая ошибка при массовом удалении: {str(e)}"
        logger.error(error_msg)
        bot.answer_callback_query(call.id, "Произошла ошибка при удалении участников")
        
        bot.edit_message_text(
            f"{EMOJI['error']} Ошибка при удалении участников:\n{str(e)}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"chat_members:{raw_chat_id}")
            )
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_remove:"))
@super_admin_required
def handle_cancel_remove(call):
    chat_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id, "Операция отменена")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"chat_members:{chat_id}"))
    
    bot.edit_message_text(
        f"{EMOJI['info']} Операция удаления участников отменена.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_remove:"))
@super_admin_required
def handle_cancel_remove(call):
    chat_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id, "Процесс удаления остановлен")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data=f"chat_members:{chat_id}"))
    
    bot.edit_message_text(
        f"{EMOJI['info']} Процесс удаления участников остановлен.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
            
def mass_remove_step(message, chat_id):
    user_ids = [id.strip() for id in message.text.split(',')]
    removed_count = 0
    
    for user_id in user_ids:
        if user_id in chats[chat_id]['members']:
            chats[chat_id]['members'].remove(user_id)
            if chat_id in users[user_id]['chats']:
                users[user_id]['chats'].remove(chat_id)
            removed_count += 1
    
    save_data()
    
    bot.reply_to(message, f"{EMOJI['success']} Удалено {removed_count} участников из чата.")
    
    fake_call = types.CallbackQuery(
        id='0', from_user=message.from_user, chat_instance='0',
        message=message, data=f"chat_members:{chat_id}", json_string='{}'
    )
    handle_chat_members(fake_call)
    logger.info(f"Суперадминистратор {message.from_user.id} удалил {removed_count} участников из чата {chat_id}")

@bot.callback_query_handler(func=lambda call: call.data == "blocked_users")
@super_admin_required
def handle_blocked_users(call):
    blocked_users = [user for user in users.values() if user.get('blocked', False)]
    
    text = f"{EMOJI['block']} Заблокированные пользователи:\n\n"
    for user in blocked_users[:10]:  # Показываем только первых 10 пользователей
        text += f"- {user['first_name']} {user['last_name'] or ''} (@{user['username'] or 'N/A'})\n"
    
    if len(blocked_users) > 10:
        text += f"\nИ еще {len(blocked_users) - 10} заблокированных пользователей..."
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_users"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел список заблокированных пользователей")

@bot.callback_query_handler(func=lambda call: call.data == "edit_user_rating")
@super_admin_required
def handle_edit_user_rating(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите ник пользователя, чей рейтинг хотите изменить:")
    bot.register_next_step_handler(msg, get_user_for_rating_edit)

def get_user_for_rating_edit(message):
    username = message.text.strip()
    user_id = next((uid for uid, user in users.items() if user.get('username') == username), None)
    if not user_id:
        bot.reply_to(message, f"{EMOJI['error']} Пользователь с таким ником не найден.")
        return
    msg = bot.reply_to(message, f"{EMOJI['edit']} Введите новое значение рейтинга:")
    bot.register_next_step_handler(msg, edit_user_rating, user_id)

def edit_user_rating(message, user_id):
    try:
        new_rating = int(message.text)
        if new_rating < 0:
            raise ValueError
        
        user = users.get(user_id)
        old_rating = calculate_rating(user)
        user['messages_count'] = new_rating
        user['reactions_received'] = 0
        save_data()
        
        bot.reply_to(message, f"{EMOJI['success']} Рейтинг пользователя успешно изменен с {old_rating} на {new_rating}")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил рейтинг пользователя {user_id} с {old_rating} на {new_rating}")
    except ValueError:
        bot.reply_to(message, f"{EMOJI['error']} Некорректное значение рейтинга. Пожалуйста, введите положительное целое число.")

def edit_user_rating_step(message):
    try:
        user_id, new_rating = message.text.split()
        new_rating = int(new_rating)
        
        if user_id not in users:
            bot.reply_to(message, f"{EMOJI['error']} Пользователь не найден.")
            return
        
        old_rating = calculate_rating(users[user_id])
        users[user_id]['messages_count'] = new_rating
        users[user_id]['reactions_received'] = 0
        save_data()
        
        bot.reply_to(message, f"{EMOJI['success']} Рейтинг пользователя изменен с {old_rating} на {new_rating}")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил рейтинг пользователя {user_id} с {old_rating} на {new_rating}")
    except ValueError:
        bot.reply_to(message, f"{EMOJI['error']} Неверный формат. Используйте: ID_пользователя новый_рейтинг")

    fake_call = types.CallbackQuery(
        id='0', from_user=message.from_user, chat_instance='0',
        message=message, data="manage_users", json_string='{}'
    )
    handle_manage_users(fake_call)

# Обновляем функцию handle_user_info для корректной работы кнопок
@bot.callback_query_handler(func=lambda call: call.data.startswith("user:"))
@super_admin_required
def handle_user_info(call):
    user_id = call.data.split(":")[1]
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Пользователь не найден.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if user.get('blocked', False):
        markup.add(types.InlineKeyboardButton(f"{EMOJI['unblock']} Разблокировать", callback_data=f"unblock_user:{user_id}"))
    else:
        markup.add(types.InlineKeyboardButton(f"{EMOJI['block']} Заблокировать", callback_data=f"block_user:{user_id}"))
    
    markup.add(types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить рейтинг", callback_data=f"edit_rating:{user_id}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['edit']} Написать", callback_data=f"message_user:{user_id}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="list_users"))
    
    user_info = f"{EMOJI['users']} Информация о пользователе:\n\n"
    user_info += f"ID: {user['id']}\n"
    user_info += f"Имя: {user['first_name']} {user['last_name'] or ''}\n"
    user_info += f"Username: @{user['username'] or 'Отсутствует'}\n"
    user_info += f"Рейтинг: {calculate_rating(user)}\n"
    user_info += f"Заблокирован: {'Да' if user.get('blocked', False) else 'Нет'}\n"
    user_info += f"Дата регистрации: {user['joined_at']}\n\n"
    user_info += f"Чаты пользователя:\n"
    for chat_id in user.get('chats', []):
        chat = chats.get(chat_id, {})
        user_info += f"- {chat.get('title', 'Неизвестный чат')}\n"
    user_info += f"\nКаналы пользователя:\n"
    for channel_id in user.get('channels', []):
        channel = channels.get(channel_id, {})
        user_info += f"- {channel.get('title', 'Неизвестный канал')}\n"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=user_info, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел информацию о пользователе {user_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("message_user:"))
@super_admin_required
def handle_message_user(call):
    user_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите сообщение для отправки пользователю:")
    bot.register_next_step_handler(msg, send_message_to_user, user_id)
    logger.info(f"Суперадминистратор {call.from_user.id} начал отправку сообщения пользователю {user_id}")

def send_message_to_user(message, user_id):
    try:
        bot.send_message(user_id, f"{EMOJI['info']} Сообщение от администрации:\n\n{message.text}")
        bot.reply_to(message, f"{EMOJI['success']} Сообщение успешно отправлено пользователю.")
        logger.info(f"Суперадминистратор {message.from_user.id} отправил сообщение пользователю {user_id}")
    except telebot.apihelper.ApiTelegramException as e:
        if e.error_code == 403:
            bot.reply_to(message, f"{EMOJI['error']} Пользователь заблокировал бота.")
        else:
            bot.reply_to(message, f"{EMOJI['error']} Ошибка при отправке сообщения: {str(e)}")
        logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {str(e)}")
    except Exception as e:
        bot.reply_to(message, f"{EMOJI['error']} Неизвестная ошибка при отправке сообщения: {str(e)}")
        logger.error(f"Неизвестная ошибка при отправке сообщения пользователю {user_id}: {str(e)}")
    
    # Возвращаемся к информации о пользователе
    handle_user_info(types.CallbackQuery(
        id='0', from_user=message.from_user, chat_instance='0',
        message=message, data=f"user:{user_id}", json_string='{}'
    ))

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_rating:"))
@super_admin_required
def handle_edit_rating(call):
    user_id = call.data.split(":")[1]
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите новое значение рейтинга для пользователя:")
    bot.register_next_step_handler(msg, process_edit_rating, user_id)
    logger.info(f"Суперадминистратор {call.from_user.id} начал процесс изменения рейтинга пользователя {user_id}")

def process_edit_rating(message, user_id):
    try:
        new_rating = int(message.text)
        if new_rating < 0:
            raise ValueError
        
        user = users.get(user_id)
        if not user:
            bot.reply_to(message, f"{EMOJI['error']} Пользователь не найден.")
            return
        
        old_rating = calculate_rating(user)
        user['messages_count'] = new_rating
        user['reactions_received'] = 0
        save_data()
        
        bot.reply_to(message, f"{EMOJI['success']} Рейтинг пользователя успешно изменен с {old_rating} на {new_rating}")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил рейтинг пользователя {user_id} с {old_rating} на {new_rating}")
    except ValueError:
        bot.reply_to(message, f"{EMOJI['error']} Некорректное значение рейтинга. Пожалуйста, введите положительное целое число.")
    
    fake_call = types.CallbackQuery(
        id='0', from_user=message.from_user, chat_instance='0',
        message=message, data=f"user:{user_id}", json_string='{}'
    )
    handle_user_info(fake_call)

@bot.callback_query_handler(func=lambda call: call.data == "channel_stats")
@super_admin_required
def handle_channel_stats(call):
    total_channels = len(channels)
    active_channels = sum(1 for channel in channels.values() if channel.get('is_active', True))
    total_subscribers = sum(len(channel.get('subscribers', [])) for channel in channels.values())
    
    stats_text = f"{EMOJI['stats']} Статистика каналов:\n\n"
    stats_text += f"Всего каналов: {total_channels}\n"
    stats_text += f"Активных каналов: {active_channels}\n"
    stats_text += f"Всего подписчиков: {total_subscribers}\n"
    
    top_channels = sorted(channels.values(), key=lambda x: len(x.get('subscribers', [])), reverse=True)[:5]
    stats_text += f"\nТоп-5 каналов по количеству подписчиков:\n"
    for i, channel in enumerate(top_channels, 1):
        stats_text += f"{i}. {channel['title']} - {len(channel.get('subscribers', []))} подписчиков\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_channels"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=stats_text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел статистику каналов")

@bot.callback_query_handler(func=lambda call: call.data == "search_channel")
@super_admin_required
def handle_search_channel(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['search']} Введите название или username канала для поиска:")
    bot.register_next_step_handler(msg, search_channel_step)
    logger.info(f"Суперадминистратор {call.from_user.id} начал поиск канала")

def search_channel_step(message):
    search_query = message.text.lower()
    found_channels = []
    for channel_id, channel in channels.items():
        if search_query in channel['title'].lower() or search_query in channel['username'].lower():
            found_channels.append(channel)
    
    if not found_channels:
        bot.reply_to(message, f"{EMOJI['error']} Каналы не найдены.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for channel in found_channels[:10]:  # Ограничиваем результаты поиска до 10
        channel_info = f"{channel['title']} (@{channel['username']})"
        markup.add(types.InlineKeyboardButton(channel_info, callback_data=f"channel_info:{channel['id']}"))
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_channels"))

    bot.send_message(message.chat.id, f"{EMOJI['success']} Найденные каналы:", reply_markup=markup)
    logger.info(f"Суперадминистратор {message.from_user.id} выполнил поиск каналов")

@bot.callback_query_handler(func=lambda call: call.data.startswith("channel_info:"))
@super_admin_required
def handle_channel_info(call):
    channel_id = call.data.split(":")[1]
    channel = channels.get(channel_id)
    
    if not channel:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Канал не найден.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить название", callback_data=f"rename_channel:{channel_id}"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить описание", callback_data=f"set_channel_description:{channel_id}"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить username", callback_data=f"change_username:channel:{channel_id}"),
        types.InlineKeyboardButton(f"{EMOJI['delete']} Удалить канал", callback_data=f"delete_channel:{channel_id}"),
        types.InlineKeyboardButton(f"{EMOJI['users']} Подписчики", callback_data=f"channel_subscribers:{channel_id}"),
        types.InlineKeyboardButton(f"{EMOJI['stats']} Статистика", callback_data=f"channel_detailed_stats:{channel_id}"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="list_channels")
    )
    
    channel_info = f"{EMOJI['channels']} Информация о канале:\n\n"
    channel_info += f"ID: {channel['id']}\n"
    channel_info += f"Название: {channel['title']}\n"
    channel_info += f"Username: @{channel['username']}\n"
    channel_info += f"Описание: {channel.get('description', 'Не задано')}\n"
    channel_info += f"Владелец: {channel['owner_id']}\n"
    channel_info += f"Количество подписчиков: {len(channel.get('subscribers', []))}\n"
    channel_info += f"Количество постов: {channel.get('posts_count', 0)}\n"
    channel_info += f"Просмотры: {channel.get('views_count', 0)}\n"
    channel_info += f"Дата создания: {channel.get('created_at', 'Неизвестно')}\n\n"
    channel_info += f"{EMOJI['thinking']} Выберите действие:"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=channel_info, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел информацию о канале {channel_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_chat:"))
@super_admin_required
def handle_delete_chat(call):
    chat_id = call.data.split(":")[1]
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['success']} Да, удалить", callback_data=f"confirm_delete_chat:{chat_id}"),
        types.InlineKeyboardButton(f"{EMOJI['error']} Отмена", callback_data=f"chat_info:{chat_id}")
    )
    
    bot.edit_message_text(
        f"{EMOJI['warning']} Вы уверены, что хотите удалить этот чат?\n"
        f"Это действие нельзя отменить, и все данные чата будут потеряны.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    logger.info(f"Суперадминистратор {call.from_user.id} запросил удаление чата {chat_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_chat:"))
@super_admin_required
def handle_confirm_delete_chat(call):
    chat_id = call.data.split(":")[1]
    
    if chat_id in chats:
        del chats[chat_id]
        save_data()
        bot.edit_message_text(
            f"{EMOJI['success']} Чат успешно удален.",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, f"{EMOJI['success']} Чат удален.")
        logger.info(f"Суперадминистратор {call.from_user.id} удалил чат {chat_id}")
    else:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Чат не найден.")
    
    handle_manage_chats(call)

@bot.callback_query_handler(func=lambda call: call.data == "manage_channels")
@super_admin_required
def handle_manage_channels(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['channels']} Список каналов", callback_data="list_channels"),
        types.InlineKeyboardButton(f"{EMOJI['search']} Найти канал", callback_data="search_channel"),
        types.InlineKeyboardButton(f"{EMOJI['stats']} Статистика каналов", callback_data="channel_stats"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="super_admin")
    )
    
    text = f"{EMOJI['channels']} Управление каналами\n\n"
    text += f"Всего каналов: {len(channels)}\n"
    text += f"Активных каналов: {sum(1 for channel in channels.values() if channel.get('is_active', True))}\n\n"
    text += f"{EMOJI['thinking']} Выберите действие:"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} открыл меню управления каналами")

@bot.callback_query_handler(func=lambda call: call.data == "list_channels")
@super_admin_required
def handle_list_channels(call):
    page = 0
    channels_per_page = 10
    total_channels = len(channels)
    total_pages = (total_channels - 1) // channels_per_page + 1

    def get_channel_list_markup(page):
        markup = types.InlineKeyboardMarkup(row_width=1)
        start = page * channels_per_page
        end = min(start + channels_per_page, total_channels)
        for channel in list(channels.values())[start:end]:
            channel_info = f"{channel['title']} (@{channel['username']})"
            markup.add(types.InlineKeyboardButton(channel_info, callback_data=f"channel_info:{channel['id']}"))
        
        nav_markup = types.InlineKeyboardMarkup(row_width=3)
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"channel_list_page:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"channel_list_page:{page+1}"))
        nav_markup.add(*nav_buttons)
        
        markup.add(*nav_markup.keyboard[0])
        markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="manage_channels"))
        return markup

    text = f"{EMOJI['channels']} Список каналов (страница {page+1}/{total_pages}):\n\n"
    text += f"{EMOJI['info']} Всего каналов: {total_channels}\n"
    text += f"{EMOJI['info']} Нажмите на канал для подробной информации"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=get_channel_list_markup(page))
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел список каналов")

@bot.callback_query_handler(func=lambda call: call.data == "bot_settings")
@super_admin_required
def handle_bot_settings(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['info']} Информация о боте", callback_data="bot_info"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить имя бота", callback_data="change_bot_name"),
        types.InlineKeyboardButton(f"{EMOJI['edit']} Изменить описание", callback_data="change_bot_description"),
        types.InlineKeyboardButton(f"{EMOJI['settings']} Настройки приватности", callback_data="privacy_settings"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Вернуться в меню", callback_data="super_admin")
    )
    
    text = f"{EMOJI['settings']} Настройки бота\n\n"
    text += f"{EMOJI['thinking']} Выберите действие:"
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} открыл настройки бота")

@bot.callback_query_handler(func=lambda call: call.data == "bot_info")
@super_admin_required
def handle_bot_info(call):
    bot_info = bot.get_me()
    info_text = f"{EMOJI['robot']} Информация о боте:\n\n"
    info_text += f"ID: {bot_info.id}\n"
    info_text += f"Имя: {bot_info.first_name}\n"
    info_text += f"Username: @{bot_info.username}\n"
    info_text += f"Может присоединяться к группам: {'Да' if bot_info.can_join_groups else 'Нет'}\n"
    info_text += f"Может читать все групповые сообщения: {'Да' if bot_info.can_read_all_group_messages else 'Нет'}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="bot_settings"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=info_text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} просмотрел информацию о боте")

@bot.callback_query_handler(func=lambda call: call.data == "change_bot_name")
@super_admin_required
def handle_change_bot_name(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите новое имя для бота:")
    bot.register_next_step_handler(msg, change_bot_name_step)
    logger.info(f"Суперадминистратор {call.from_user.id} начал процесс изменения имени бота")

def change_bot_name_step(message):
    new_name = message.text.strip()
    if len(new_name) < 3 or len(new_name) > 64:
        bot.reply_to(message, f"{EMOJI['error']} Имя бота должно содержать от 3 до 64 символов.")
        return
    
    try:
        bot.set_my_name(new_name)
        bot.reply_to(message, f"{EMOJI['success']} Имя бота успешно изменено на «{new_name}»")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил имя бота на {new_name}")
    except telebot.apihelper.ApiException as e:
        bot.reply_to(message, f"{EMOJI['error']} Ошибка при изменении имени бота: {str(e)}")
        logger.error(f"Ошибка при изменении имени бота: {str(e)}")
    
    handle_bot_settings(types.CallbackQuery(from_user=message.from_user, message=message, data="bot_settings"))

@bot.callback_query_handler(func=lambda call: call.data == "change_bot_description")
@super_admin_required
def handle_change_bot_description(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, f"{EMOJI['edit']} Введите новое описание для бота:")
    bot.register_next_step_handler(msg, change_bot_description_step)
    logger.info(f"Суперадминистратор {call.from_user.id} начал процесс изменения описания бота")

def change_bot_description_step(message):
    new_description = message.text.strip()
    if len(new_description) > 512:
        bot.reply_to(message, f"{EMOJI['error']} Описание бота не должно превышать 512 символов.")
        return
    
    try:
        bot.set_my_description(new_description)
        bot.reply_to(message, f"{EMOJI['success']} Описание бота успешно изменено")
        logger.info(f"Суперадминистратор {message.from_user.id} изменил описание бота")
    except telebot.apihelper.ApiException as e:
        bot.reply_to(message, f"{EMOJI['error']} Ошибка при изменении описания бота: {str(e)}")
        logger.error(f"Ошибка при изменении описания бота: {str(e)}")
    
    handle_bot_settings(types.CallbackQuery(from_user=message.from_user, message=message, data="bot_settings"))

@bot.callback_query_handler(func=lambda call: call.data == "privacy_settings")
@super_admin_required
def handle_privacy_settings(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Включить приватность", callback_data="set_privacy:on"),
        types.InlineKeyboardButton("Выключить приватность", callback_data="set_privacy:off"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="bot_settings")
    )
    
    text = f"{EMOJI['settings']} Настройки приватности бота\n\n"
    text += "Текущий статус приватности: Неизвестно\n\n"
    text += "При включенной приватности бот будет отвечать только на команды в личных сообщениях и в группах, где он является администратором."
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=text, 
                          reply_markup=markup)
    logger.info(f"Суперадминистратор {call.from_user.id} открыл настройки приватности бота")

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_privacy:"))
@super_admin_required
def handle_set_privacy(call):
    action = call.data.split(":")[1]
    try:
        if action == "on":
            bot.set_my_commands([], scope=types.BotCommandScopeDefault())
            bot.set_my_commands(bot.get_my_commands(), scope=types.BotCommandScopeAllPrivateChats())
            status = "включена"
        else:
            bot.set_my_commands(bot.get_my_commands(), scope=types.BotCommandScopeDefault())
            status = "выключена"
        
        bot.answer_callback_query(call.id, f"{EMOJI['success']} Приватность бота {status}")
        logger.info(f"Суперадминистратор {call.from_user.id} {status} приватность бота")
        
        # Обновляем текст сообщения с учетом нового статуса
        text = f"{EMOJI['settings']} Настройки приватности бота\n\n"
        text += f"Текущий статус приватности: {'Включена' if status == 'включена' else 'Выключена'}\n\n"
        text += "При включенной приватности бот будет отвечать только на команды в личных сообщениях и в группах, где он является администратором."
        
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, 
                                  message_id=call.message.message_id, 
                                  text=text, 
                                  reply_markup=call.message.reply_markup)
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e):
                pass  # Игнорируем ошибку, если сообщение не изменилось
            else:
                raise  # Пробрасываем другие ошибки
    except telebot.apihelper.ApiException as e:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Ошибка при изменении настроек приватности: {str(e)}")
        logger.error(f"Ошибка при изменении настроек приватности: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "view_logs")
@super_admin_required
def handle_view_logs(call):
    try:
        with open('bot.log', 'r', encoding='utf-8', errors='replace') as log_file:
            logs = log_file.readlines()[-50:]  # Получаем последние 50 строк лога
        
        log_text = f"{EMOJI['info']} Последние записи лога:\n\n"
        log_text += "".join(logs)
        
        if len(log_text) > 4096:
            for x in range(0, len(log_text), 4096):
                bot.send_message(call.message.chat.id, log_text[x:x+4096])
        else:
            bot.send_message(call.message.chat.id, log_text)
        
        logger.info(f"Суперадминистратор {call.from_user.id} просмотрел логи бота")
    except Exception as e:
        bot.answer_callback_query(call.id, f"{EMOJI['error']} Ошибка при чтении лога: {str(e)}")
        logger.error(f"Ошибка при чтении лога: {str(e)}")

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="bot_settings"))
    bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_rating")
def handle_show_rating(call):
    top_users = get_top_users(10)
    rating_text = get_localized_text('rating_info', str(call.from_user.id)) + "\n\n"
    for i, user in enumerate(top_users, 1):
        rating = calculate_rating(user)
        rating_text += f"{i}. {user['first_name']} {user['last_name'] or ''} - {rating} {get_localized_text('points', str(call.from_user.id))}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_localized_text('back_to_menu', str(call.from_user.id)), callback_data="menu"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=rating_text, 
                          reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "user_stats")
def handle_user_stats(call):
    user_id = str(call.from_user.id)
    user = users.get(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, get_localized_text('user_not_found', user_id))
        return
    
    stats_text = get_localized_text('user_stats', user_id) + "\n\n"
    stats_text += f"{get_localized_text('messages_count', user_id)}: {user.get('messages_count', 0)}\n"
    stats_text += f"{get_localized_text('reactions_received', user_id)}: {user.get('reactions_received', 0)}\n"
    stats_text += f"{get_localized_text('rating', user_id)}: {calculate_rating(user)}\n"
    stats_text += f"{get_localized_text('chats_count', user_id)}: {len(user.get('chats', []))}\n"
    stats_text += f"{get_localized_text('channels_count', user_id)}: {len(user.get('channels', []))}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(get_localized_text('back_to_menu', user_id), callback_data="menu"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          text=stats_text, 
                          reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "send_broadcast")
@super_admin_required
def handle_send_broadcast(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['users']} Всем пользователям", callback_data="broadcast_all_users"),
        types.InlineKeyboardButton(f"{EMOJI['chats']} В чаты", callback_data="broadcast_chats"),
        types.InlineKeyboardButton(f"{EMOJI['channels']} В каналы", callback_data="broadcast_channels"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="super_admin")
    )
    
    text = f"{EMOJI['rocket']} Выберите тип рассылки:\n\n"
    text += "• Всем пользователям - отправка в личные сообщения\n"
    text += "• В чаты - отправка во все чаты с ботом\n"
    text += "• В каналы - отправка во все каналы с ботом"
    
    bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_"))
@super_admin_required
def handle_broadcast_type(call):
    broadcast_type = call.data.split("_")[1]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJI['edit']} Обычное сообщение", callback_data=f"compose_broadcast:{broadcast_type}:text"),
        types.InlineKeyboardButton(f"{EMOJI['magic']} С форматированием", callback_data=f"compose_broadcast:{broadcast_type}:html"),
        types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="send_broadcast")
    )
    
    text = f"{EMOJI['edit']} Выберите тип сообщения для рассылки:\n\n"
    text += "• Обычное сообщение - простой текст\n"
    text += "• С форматированием - поддержка HTML-тегов"
    
    bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("compose_broadcast:"))
@super_admin_required
def handle_compose_broadcast(call):
    _, broadcast_type, message_type = call.data.split(":")
    
    bot.answer_callback_query(call.id)
    
    if message_type == "html":
        help_text = (
            f"{EMOJI['edit']} Введите сообщение для рассылки.\n"
            "Поддерживаемые HTML-теги:\n"
            "• <b>жирный</b>\n"
            "• <i>курсив</i>\n"
            "• <u>подчеркнутый</u>\n"
            "• <s>зачеркнутый</s>\n"
            "• <code>моноширинный</code>\n"
            "• <a href='URL'>ссылка</a>"
        )
    else:
        help_text = f"{EMOJI['edit']} Введите текст сообщения для рассылки:"
    
    msg = bot.send_message(call.message.chat.id, help_text)
    bot.register_next_step_handler(msg, process_broadcast_message, broadcast_type, message_type)

def process_broadcast_message(message, broadcast_type, message_type):
    broadcast_text = message.text.strip()
    if not broadcast_text:
        bot.reply_to(message, f"{EMOJI['error']} Сообщение не может быть пустым.")
        return
    
    # Создаем прогресс-сообщение
    progress_msg = bot.reply_to(
        message, 
        f"{EMOJI['info']} Подготовка к рассылке...",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(f"{EMOJI['error']} Отменить", callback_data="cancel_broadcast")
        )
    )
    
    try:
        successful = 0
        failed = 0
        blocked = 0
        total = 0
        
        if broadcast_type == "all_users":
            recipients = users.keys()
            total = len(users)
        elif broadcast_type == "chats":
            recipients = chats.keys()
            total = len(chats)
        else:  # channels
            recipients = channels.keys()
            total = len(channels)
        
        for i, recipient_id in enumerate(recipients, 1):
            try:
                if message_type == "html":
                    bot.send_message(
                        recipient_id,
                        broadcast_text,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                else:
                    bot.send_message(recipient_id, broadcast_text)
                successful += 1
                
                # Обновляем прогресс каждые 10 отправок
                if i % 10 == 0:
                    progress = (i / total) * 100
                    update_text = (
                        f"{EMOJI['info']} Прогресс рассылки: {progress:.1f}%\n"
                        f"Отправлено: {successful}\n"
                        f"Ошибок: {failed}\n"
                        f"Заблокировали: {blocked}"
                    )
                    try:
                        bot.edit_message_text(
                            update_text,
                            chat_id=progress_msg.chat.id,
                            message_id=progress_msg.message_id,
                            reply_markup=types.InlineKeyboardMarkup().add(
                                types.InlineKeyboardButton(f"{EMOJI['error']} Отменить", callback_data="cancel_broadcast")
                            )
                        )
                    except:
                        pass
                    
                time.sleep(0.05)  # Небольшая задержка между отправками
                
            except telebot.apihelper.ApiException as e:
                if "Forbidden" in str(e):
                    blocked += 1
                else:
                    failed += 1
                logger.error(f"Ошибка при отправке сообщения {recipient_id}: {str(e)}")
            except Exception as e:
                failed += 1
                logger.error(f"Неожиданная ошибка при отправке {recipient_id}: {str(e)}")
        
        # Финальный отчет
        report = (
            f"{EMOJI['success']} Рассылка завершена!\n\n"
            f"Всего получателей: {total}\n"
            f"Успешно отправлено: {successful}\n"
            f"Ошибок доставки: {failed}\n"
            f"Заблокировали бота: {blocked}"
        )
        
        try:
            bot.edit_message_text(
                report,
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )
        except:
            bot.reply_to(message, report)
        
    except Exception as e:
        error_text = f"{EMOJI['error']} Ошибка при выполнении рассылки: {str(e)}"
        try:
            bot.edit_message_text(
                error_text,
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )
        except:
            bot.reply_to(message, error_text)
        logger.error(f"Ошибка при выполнении рассылки: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_broadcast")
@super_admin_required
def handle_cancel_broadcast(call):
    # Здесь можно добавить логику отмены рассылки
    bot.answer_callback_query(call.id, f"{EMOJI['error']} Функция отмены рассылки пока не реализована")

def send_broadcast_step(message):
    broadcast_message = message.text.strip()
    successful = 0
    failed = 0
    
    progress_msg = bot.reply_to(message, f"{EMOJI['info']} Начинаем рассылку...")
    
    for user_id in users.keys():
        try:
            bot.send_message(user_id, f"{EMOJI['info']} Сообщение от администрации:\n\n{broadcast_message}")
            successful += 1
            if successful % 10 == 0:  # Обновляем прогресс каждые 10 успешных отправок
                bot.edit_message_text(f"{EMOJI['info']} Отправлено: {successful}, Ошибок: {failed}", 
                                      chat_id=message.chat.id, 
                                      message_id=progress_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {str(e)}")
            failed += 1
    
    report = f"{EMOJI['success']} Рассылка завершена:\n\n"
    report += f"Успешно отправлено: {successful}\n"
    report += f"Ошибок при отправке: {failed}"
    
    bot.edit_message_text(report, chat_id=message.chat.id, message_id=progress_msg.message_id)
    logger.info(f"Суперадминистратор {message.from_user.id} завершил рассылку. Успешно: {successful}, Ошибок: {failed}")
    
    handle_super_admin(message)

@bot.callback_query_handler(func=lambda call: call.data in ["super_admin", "manage_users", "manage_chats", "manage_channels", "bot_settings"])
def handle_navigation(call):
    navigation_functions = {
        "super_admin": callback_super_admin,
        "manage_users": handle_manage_users,
        "manage_chats": handle_manage_chats,
        "manage_channels": handle_manage_channels,
        "bot_settings": handle_bot_settings
    }
    
    navigation_functions[call.data](call)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if is_user_blocked(user_id):
        return

    if user_id not in users:
        users[user_id] = {
            'id': user_id,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'username': message.from_user.username,
            'joined_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'messages_count': 0,
            'reactions_received': 0,
            'chats': [],
            'channels': [],
            'language': 'ru'
        }
        save_data()

    users[user_id]['messages_count'] += 1

    if message.chat.type in ['group', 'supergroup']:
        if chat_id not in chats:
            chats[chat_id] = {
                'id': chat_id,
                'title': message.chat.title,
                'members': [],
                'messages_count': 0,
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        
        if user_id not in chats[chat_id]['members']:
            chats[chat_id]['members'].append(user_id)
        
        chats[chat_id]['messages_count'] += 1

    save_data()
    logger.info(f"Получено сообщение от пользователя {user_id} в чате {chat_id}")

    if message.chat.type == 'private':
        safe_send_message(message.chat.id, get_localized_text('unknown_command', user_id))

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_chat_members(message):
    chat_id = str(message.chat.id)
    
    # Проверяем существование чата в базе
    if chat_id not in chats:
        scan_chat_members(chat_id)  # Если чата нет, сканируем всех участников
    
    # Обрабатываем новых участников
    for new_member in message.new_chat_members:
        user_id = str(new_member.id)
        
        # Пропускаем бота
        if new_member.is_bot and new_member.username == bot.get_me().username:
            continue
        
        # Добавляем пользователя в базу
        if user_id not in users:
            users[user_id] = {
                'id': user_id,
                'first_name': new_member.first_name,
                'last_name': new_member.last_name,
                'username': new_member.username,
                'joined_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'messages_count': 0,
                'reactions_received': 0,
                'chats': [chat_id],
                'channels': [],
                'language': 'ru'
            }
        elif chat_id not in users[user_id]['chats']:
            users[user_id]['chats'].append(chat_id)
        
        # Добавляем пользователя в список участников чата
        if user_id not in chats[chat_id]['members']:
            chats[chat_id]['members'].append(user_id)
    
    save_data()
    logger.info(f"Новые участники добавлены в базу данных чата {chat_id}")

# Добавляем команду для принудительного сканирования
@bot.message_handler(commands=['scan_members'])
@super_admin_required
def handle_scan_members(message):
    """Принудительное сканирование участников чата"""
    try:
        chat_id = str(message.chat.id)
        members_count = scan_chat_members(chat_id)
        bot.reply_to(
            message,
            f"{EMOJI['success']} Сканирование завершено!\n"
            f"Обнаружено участников: {members_count}"
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"{EMOJI['error']} Ошибка при сканировании: {str(e)}"
        )

@bot.message_handler(content_types=['left_chat_member'])
def handle_left_chat_member(message):
    chat_id = str(message.chat.id)
    user_id = str(message.left_chat_member.id)
    
    if chat_id in chats and user_id in chats[chat_id]['members']:
        chats[chat_id]['members'].remove(user_id)
    
    if user_id in users and chat_id in users[user_id]['chats']:
        users[user_id]['chats'].remove(chat_id)
    
    save_data()
    logger.info(f"Участник {user_id} покинул чат {chat_id}")

@bot.my_chat_member_handler()
def handle_my_chat_member(message):
    """Обработка добавления/удаления бота из чата"""
    try:
        chat_id = str(message.chat.id)
        new_status = message.new_chat_member.status
        old_status = message.old_chat_member.status
        user_id = str(message.from_user.id)
        
        if new_status in ['member', 'administrator'] and old_status in ['left', 'kicked']:
            if message.chat.type in ['group', 'supergroup']:
                # Сканируем участников чата
                members_count = scan_chat_members(chat_id)
                
                # Отправляем приветственное сообщение
                try:
                    bot.send_message(
                        chat_id,
                        f"{EMOJI['welcome']} Спасибо, что добавили меня в чат!\n"
                        f"Я успешно получил информацию о {members_count} участниках."
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке приветствия: {e}")
                
                # Уведомляем админа
                try:
                    bot.send_message(
                        SUPER_ADMIN_ID,
                        f"{EMOJI['success']} Бот добавлен в чат: {message.chat.title}\n"
                        f"ID чата: {chat_id}\n"
                        f"Тип: {message.chat.type}\n"
                        f"Добавил: {message.from_user.first_name} ({user_id})\n"
                        f"Просканировано участников: {members_count}"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при уведомлении админа: {e}")
                    
        elif new_status in ['left', 'kicked']:
            # Обработка удаления бота из чата
            if chat_id in chats:
                chats[chat_id]['is_active'] = False
            save_data()
            
    except Exception as e:
        logger.error(f"Ошибка в обработчике my_chat_member: {e}")

@bot.message_handler(commands=['update_chats'])
@super_admin_required
def handle_update_chats(message):
    """Обновление списка чатов и проверка прав бота"""
    try:
        updated = 0
        errors = 0
        removed = 0
        
        # Создаем копию списка чатов для итерации
        chats_to_check = list(chats.keys())
        
        status_msg = bot.reply_to(message, f"{EMOJI['info']} Начинаю проверку чатов...")
        
        for chat_id in chats_to_check:
            try:
                # Проверяем наличие бота в чате и его права
                chat_info = bot.get_chat(chat_id)
                bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
                
                # Обновляем информацию о чате
                chats[chat_id].update({
                    'title': chat_info.title,
                    'type': chat_info.type,
                    'is_active': True,
                    'member_count': bot.get_chat_member_count(chat_id),
                    'bot_rights': {
                        'can_send_messages': getattr(bot_member, 'can_send_messages', None),
                        'can_send_media_messages': getattr(bot_member, 'can_send_media_messages', None),
                        'can_send_other_messages': getattr(bot_member, 'can_send_other_messages', None),
                        'can_delete_messages': getattr(bot_member, 'can_delete_messages', None),
                        'can_restrict_members': getattr(bot_member, 'can_restrict_members', None)
                    }
                })
                updated += 1
                
            except Exception as e:
                if "chat not found" in str(e) or "bot was kicked" in str(e):
                    # Если бот был удален из чата, удаляем чат из базы
                    del chats[chat_id]
                    removed += 1
                else:
                    errors += 1
                logger.error(f"Ошибка при проверке чата {chat_id}: {e}")
        
        save_data()
        
        report = f"{EMOJI['success']} Проверка чатов завершена:\n\n"
        report += f"✅ Обновлено: {updated}\n"
        report += f"❌ Ошибок: {errors}\n"
        report += f"🗑 Удалено: {removed}"
        
        bot.edit_message_text(
            report,
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id
        )
        
    except Exception as e:
        bot.reply_to(
            message,
            f"{EMOJI['error']} Ошибка при обновлении списка чатов: {str(e)}"
        )

# Улучшенное логирование
class CustomFormatter(logging.Formatter):
    """Кастомный форматтер для красивого вывода логов"""
    
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: blue + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Настройка улучшенного логирования
def setup_logging():
    """Настройка расширенного логирования"""
    
    # Основной файл лога
    main_handler = RotatingFileHandler(
        'bot.log',
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=5,
        encoding='utf-8'
    )
    main_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))

    # Отдельный файл для ошибок
    error_handler = RotatingFileHandler(
        'errors.log',
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s\nTraceback:\n%(exc_info)s'
    ))

    # Консольный вывод с цветным форматированием
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CustomFormatter())

    # Настройка логгера
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(main_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger

# Класс для отслеживания состояния бота
class BotHealthMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.error_count = 0
        self.message_count = 0
        self.last_error = None
        self.last_error_time = None
        self.is_running = True

    def log_error(self, error):
        """Логирование ошибки"""
        self.error_count += 1
        self.last_error = str(error)
        self.last_error_time = datetime.now()

    def log_message(self):
        """Подсчет обработанных сообщений"""
        self.message_count += 1

    def get_uptime(self):
        """Получение времени работы бота"""
        return datetime.now() - self.start_time

    def get_stats(self):
        """Получение статистики работы бота"""
        return {
            'uptime': self.get_uptime(),
            'error_count': self.error_count,
            'message_count': self.message_count,
            'messages_per_hour': self.message_count / (self.get_uptime().total_seconds() / 3600),
            'last_error': self.last_error,
            'last_error_time': self.last_error_time,
            'is_running': self.is_running
        }

# Создаем монитор
bot_monitor = BotHealthMonitor()

# Декоратор для отлова ошибок
def error_handler(func):
    """Декоратор для обработки ошибок в функциях бота"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Логируем ошибку
            error_text = f"Ошибка в функции {func.__name__}: {str(e)}"
            logger.error(error_text, exc_info=True)
            bot_monitor.log_error(error_text)
            
            # Уведомляем админа
            try:
                bot.send_message(
                    SUPER_ADMIN_ID,
                    f"{EMOJI['error']} Произошла ошибка!\n\n"
                    f"Функция: {func.__name__}\n"
                    f"Ошибка: {str(e)}\n"
                    f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except:
                pass
            
            # Если это callback, отвечаем пользователю
            if args and isinstance(args[0], types.CallbackQuery):
                try:
                    bot.answer_callback_query(
                        args[0].id,
                        f"{EMOJI['error']} Произошла ошибка. Администратор уведомлен."
                    )
                except:
                    pass
            # Если это сообщение, отвечаем пользователю
            elif args and isinstance(args[0], types.Message):
                try:
                    bot.reply_to(
                        args[0],
                        f"{EMOJI['error']} Произошла ошибка. Администратор уведомлен."
                    )
                except:
                    pass
    return wrapper

# Команда для просмотра состояния бота
@bot.message_handler(commands=['status'])
@super_admin_required
def handle_status(message):
    stats = bot_monitor.get_stats()
    
    status_text = f"{EMOJI['robot']} Статус бота:\n\n"
    status_text += f"Время работы: {stats['uptime'].days}д {stats['uptime'].seconds//3600}ч {(stats['uptime'].seconds//60)%60}м\n"
    status_text += f"Обработано сообщений: {stats['message_count']}\n"
    status_text += f"Сообщений в час: {stats['messages_per_hour']:.1f}\n"
    status_text += f"Количество ошибок: {stats['error_count']}\n"
    
    if stats['last_error']:
        status_text += f"\nПоследняя ошибка:\n{stats['last_error']}\n"
        status_text += f"Время ошибки: {stats['last_error_time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Просмотр логов", callback_data="view_logs"),
        types.InlineKeyboardButton("Очистить логи", callback_data="clear_logs"),
        types.InlineKeyboardButton("Статистика БД", callback_data="db_stats"),
        types.InlineKeyboardButton("Тест соединения", callback_data="test_connection")
    )
    
    bot.reply_to(message, status_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "test_connection")
@super_admin_required
def handle_test_connection(call):
    try:
        start_time = time.time()
        bot.get_me()
        response_time = (time.time() - start_time) * 1000
        
        test_text = f"{EMOJI['success']} Тест соединения:\n\n"
        test_text += f"Статус: Работает\n"
        test_text += f"Время ответа: {response_time:.1f}мс"
        
        bot.answer_callback_query(call.id, "Тест успешно выполнен")
        bot.edit_message_text(
            test_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=call.message.reply_markup
        )
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка соединения: {str(e)}"
        )

@bot.callback_query_handler(func=lambda call: call.data == "db_stats")
@super_admin_required
def handle_db_stats(call):
    try:
        db_size = os.path.getsize('data.json') / 1024  # размер в КБ
        
        stats_text = f"{EMOJI['stats']} Статистика базы данных:\n\n"
        stats_text += f"Размер файла: {db_size:.1f} КБ\n"
        stats_text += f"Пользователей: {len(users)}\n"
        stats_text += f"Чатов: {len(chats)}\n"
        stats_text += f"Каналов: {len(channels)}\n"
        
        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=call.message.reply_markup
        )
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка при получении статистики: {str(e)}"
        )

@bot.callback_query_handler(func=lambda call: call.data == "clear_logs")
@super_admin_required
def handle_clear_logs(call):
    try:
        # Очищаем основной лог
        with open('bot.log', 'w', encoding='utf-8') as f:
            f.write('')
        
        # Очищаем лог ошибок
        with open('errors.log', 'w', encoding='utf-8') as f:
            f.write('')
        
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['success']} Логи успешно очищены"
        )
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            f"{EMOJI['error']} Ошибка при очистке логов: {str(e)}"
        )

@bot.message_handler(func=lambda message: message.text.startswith('/') and message.text != '/super_admin', content_types=['text'])
def handle_unknown_command(message):
    user_id = str(message.from_user.id)
    bot.reply_to(message, get_localized_text('unknown_command', user_id))

class BotGuard:
    def __init__(self, port=48735, pid_file='bot_instance.json'):
        self.port = port
        self.pid_file = pid_file
        self.sock = None
        
    def acquire(self):
        """Попытка получить эксклюзивный доступ"""
        try:
            # 1. Проверяем и очищаем старые записи
            self._cleanup_old_instances()
            
            # 2. Пытаемся занять TCP порт
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.sock.bind(('localhost', self.port))
                self.sock.listen(1)
            except socket.error:
                print(f"{EMOJI['error']} Бот уже запущен (порт {self.port} занят)")
                return False
            
            # 3. Сохраняем информацию о текущем процессе
            instance_info = {
                'pid': os.getpid(),
                'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'script_path': os.path.abspath(sys.argv[0])
            }
            
            with open(self.pid_file, 'w') as f:
                json.dump(instance_info, f)
            
            return True
            
        except Exception as e:
            print(f"{EMOJI['error']} Ошибка при инициализации защиты: {e}")
            self.release()
            return False
    
    def release(self):
        """Освобождение ресурсов"""
        try:
            if self.sock:
                self.sock.close()
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
        except Exception as e:
            print(f"{EMOJI['error']} Ошибка при освобождении ресурсов: {e}")
    
    def _cleanup_old_instances(self):
        """Поиск и завершение зависших процессов бота"""
        try:
            # Проверяем существующий PID файл
            if os.path.exists(self.pid_file):
                with open(self.pid_file, 'r') as f:
                    try:
                        old_instance = json.load(f)
                        old_pid = old_instance.get('pid')
                        
                        if old_pid:
                            try:
                                process = psutil.Process(old_pid)
                                # Проверяем, что это действительно наш бот
                                if any('main.py' in cmd.lower() for cmd in process.cmdline()):
                                    print(f"{EMOJI['info']} Завершение предыдущего процесса бота (PID: {old_pid})")
                                    process.terminate()
                                    try:
                                        process.wait(timeout=3)
                                    except psutil.TimeoutExpired:
                                        process.kill()
                            except psutil.NoSuchProcess:
                                pass
                    except (json.JSONDecodeError, KeyError):
                                pass
                
                # Удаляем старый файл
                try:
                    os.remove(self.pid_file)
                except OSError:
                    pass
                    
        except Exception as e:
            print(f"{EMOJI['warning']} Ошибка при очистке старых процессов: {e}")

def run_bot_safely():
    """Запуск бота с защитой от множественных экземпляров"""
    guard = BotGuard()
    
    if not guard.acquire():
        sys.exit(1)
    
    try:
        logger.info(f"{EMOJI['rocket']} Бот запускается...")
        load_data()
        
        def shutdown_handler(signum=None, frame=None):
            """Обработчик сигналов завершения"""
            logger.info(f"{EMOJI['info']} Получен сигнал завершения. Корректное завершение работы...")
            try:
                save_data()
                guard.release()
            finally:
                sys.exit(0)
        
        # Регистрируем обработчики сигналов
        try:
            import signal
            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)
        except Exception as e:
            logger.warning(f"Не удалось установить обработчики сигналов: {e}")
        
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except Exception as e:
        logger.error(f"{EMOJI['error']} Критическая ошибка при работе бота: {str(e)}")
        try:
            safe_send_message(
                SUPER_ADMIN_ID,
                f"{EMOJI['error']} Критическая ошибка при работе бота:\n{str(e)}"
            )
        except:
            pass
        raise
        
    finally:
        guard.release()

if __name__ == "__main__":
    run_bot_safely()