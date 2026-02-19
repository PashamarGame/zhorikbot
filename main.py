import telebot
from telebot import types
import random
import json
import os
import time
from threading import Thread
import uuid
import logging
from datetime import datetime, timedelta
import sys
import select
import threading
import zipfile
import shutil
import io
from collections import Counter

# Конфигурация
API_TOKEN = '8252338928:AAGNGNj34g1sp4ik6pgY0jQl9m_h7LbuM3g'
MAIN_ADMIN = 'Ishy_svoi_nik_rob_pasha'  # Основной админ для первого входа
DROP_COOLDOWN = 301  # Задержка 5 минут (300 секунд)
bot = telebot.TeleBot(API_TOKEN)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Пути к файлам
DATA_DIR = 'bot_data'
CARDS_DIR = os.path.join(DATA_DIR, 'cards')
IMAGES_DIR = os.path.join(DATA_DIR, 'images')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
CARDS_FILE = os.path.join(DATA_DIR, 'cards.json')
MARKET_FILE = os.path.join(DATA_DIR, 'market.json')
ROLES_FILE = os.path.join(DATA_DIR, 'roles.json')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

# Создание директорий
for dir_path in [DATA_DIR, CARDS_DIR, IMAGES_DIR, BACKUP_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

# Редкости карт с ПРАВИЛЬНЫМИ шансами выпадения
RARITIES = {
    'обычная': 60,           # 60% - очень часто
    'обычно-редкая': 25,      # 25% - часто
    'редкая': 10,             # 10% - редко
    'редко-мифическая': 3,    # 3% - очень редко
    'мифическая': 1,          # 1% - крайне редко
    'мифо-легендарная': 0.5,  # 0.5% - почти никогда
    'легендарная': 0.3,       # 0.3% - легендарная редкость
    'легендо-легендарная': 0.15, # 0.15% - невероятная редкость
    'легендо-лего-легендарная': 0.05 # 0.05% - мифическая редкость (1 из 2000)
}

# Хранилище состояний создания и редактирования карт
card_creation_states = {}
card_editing_states = {}

# Функция для безопасного чтения JSON
def safe_json_load(file_path, default):
    try:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Создаем файл с дефолтными данными
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default, f, ensure_ascii=False, indent=4)
            return default
    except (json.JSONDecodeError, FileNotFoundError):
        # Если файл поврежден, создаем новый
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=4)
        return default

# Инициализация файлов данных
def init_json_file(file_path, default_data):
    safe_json_load(file_path, default_data)

init_json_file(USERS_FILE, {})
init_json_file(CARDS_FILE, [])
init_json_file(MARKET_FILE, [])
init_json_file(ROLES_FILE, {'admins': [], 'card_creators': []})

# Класс для работы с пользователями
class UserManager:
    @staticmethod
    def get_user(user_id):
        users = safe_json_load(USERS_FILE, {})

        user_id_str = str(user_id)
        if user_id_str not in users:
            users[user_id_str] = {
                'balance': 100,  # Начальный баланс
                'cards': [],
                'username': '',
                'first_name': '',
                'last_name': '',
                'last_drop': None,
                'registered_at': datetime.now().isoformat()
            }
            UserManager.save_users(users)

        return users[user_id_str]

    @staticmethod
    def save_users(users):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=4)

    @staticmethod
    def update_balance(user_id, amount):
        users = UserManager.get_all_users()
        user_id_str = str(user_id)
        if user_id_str in users:
            users[user_id_str]['balance'] += amount
            UserManager.save_users(users)
            return True
        return False

    @staticmethod
    def get_all_users():
        return safe_json_load(USERS_FILE, {})

    @staticmethod
    def get_user_by_username(username):
        users = UserManager.get_all_users()
        username = username.lower().replace('@', '')
        for user_id, user_data in users.items():
            if user_data.get('username', '').lower() == username:
                return user_id, user_data
        return None, None

    @staticmethod
    def get_user_by_id(user_id):
        users = UserManager.get_all_users()
        return users.get(str(user_id))

    @staticmethod
    def update_user_info(user_id, first_name, last_name, username):
        users = UserManager.get_all_users()
        user_id_str = str(user_id)
        if user_id_str in users:
            users[user_id_str]['first_name'] = first_name
            users[user_id_str]['last_name'] = last_name or ''
            users[user_id_str]['username'] = username or ''
            UserManager.save_users(users)
            return True
        return False

    @staticmethod
    def add_coins_to_all_users(amount):
        users = UserManager.get_all_users()
        for user_id in users:
            users[user_id]['balance'] += amount
        UserManager.save_users(users)
        return len(users)

    @staticmethod
    def can_drop_card(user_id):
        """Проверяет, может ли пользователь вытянуть карту"""
        user = UserManager.get_user(user_id)
        if not user.get('last_drop'):
            return True, 0

        try:
            last_drop = datetime.fromisoformat(user['last_drop'])
            time_diff = datetime.now() - last_drop
            if time_diff.total_seconds() >= DROP_COOLDOWN:
                return True, 0
            else:
                wait_time = int(DROP_COOLDOWN - time_diff.total_seconds())
                return False, wait_time
        except:
            # Если ошибка в формате даты, сбрасываем
            return True, 0

    @staticmethod
    def update_last_drop(user_id):
        """Обновляет время последнего выпадения карты"""
        users = UserManager.get_all_users()
        users[str(user_id)]['last_drop'] = datetime.now().isoformat()
        UserManager.save_users(users)

# Класс для работы с картами
class CardManager:
    @staticmethod
    def get_all_cards():
        return safe_json_load(CARDS_FILE, [])

    @staticmethod
    def save_cards(cards):
        with open(CARDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(cards, f, ensure_ascii=False, indent=4)

    @staticmethod
    def add_card(card_data, creator_id=None):
        cards = CardManager.get_all_cards()
        card_id = str(uuid.uuid4())[:8]
        card_data['id'] = card_id
        card_data['owner_id'] = None
        card_data['created_at'] = datetime.now().isoformat()
        card_data['created_by'] = str(creator_id) if creator_id else None
        card_data['last_edited'] = None
        card_data['edited_by'] = None
        cards.append(card_data)
        CardManager.save_cards(cards)
        return card_id

    @staticmethod
    def update_card(card_id, updated_data, editor_id=None):
        cards = CardManager.get_all_cards()
        for i, card in enumerate(cards):
            if card['id'] == card_id:
                # Сохраняем старое изображение если нужно
                old_image = card.get('image_path')
                new_image = updated_data.get('image_path')

                # Если изображение изменилось и старое существует - удаляем
                if old_image and new_image != old_image and os.path.exists(old_image):
                    try:
                        os.remove(old_image)
                    except:
                        pass

                # Обновляем карту
                for key, value in updated_data.items():
                    cards[i][key] = value
                cards[i]['last_edited'] = datetime.now().isoformat()
                cards[i]['edited_by'] = str(editor_id) if editor_id else None
                CardManager.save_cards(cards)
                return True
        return False

    @staticmethod
    def get_card(card_id):
        cards = CardManager.get_all_cards()
        for card in cards:
            if card['id'] == card_id:
                return card
        return None

    @staticmethod
    def get_random_card():
        """Получить случайную карту с учетом редкости"""
        cards = CardManager.get_all_cards()
        if not cards:
            return None

        # Группируем карты по редкости
        cards_by_rarity = {}
        for card in cards:
            rarity = card['rarity']
            if rarity not in cards_by_rarity:
                cards_by_rarity[rarity] = []
            cards_by_rarity[rarity].append(card)

        # Создаем список доступных редкостей
        available_rarities = [r for r in cards_by_rarity.keys()]
        if not available_rarities:
            return None

        # Выбираем редкость на основе шансов
        random_number = random.uniform(0, 100)

        # Сортируем редкости по шансу (от большего к меньшему)
        sorted_rarities = sorted(RARITIES.items(), key=lambda x: x[1], reverse=True)

        cumulative = 0
        for rarity, chance in sorted_rarities:
            if rarity in available_rarities:
                cumulative += chance
                if random_number <= cumulative:
                    return random.choice(cards_by_rarity[rarity])

        # Если не выбрали (например, из-за округления), берем самую частую доступную
        most_common_rarity = max(available_rarities, key=lambda r: RARITIES.get(r, 0))
        return random.choice(cards_by_rarity[most_common_rarity])

    @staticmethod
    def test_drop_distribution(trials=10000):
        """Тестирует распределение выпадения карт"""
        cards = CardManager.get_all_cards()
        if not cards:
            return "Нет карт для тестирования"

        results = []
        for _ in range(trials):
            card = CardManager.get_random_card()
            if card:
                results.append(card['rarity'])

        if not results:
            return "Ошибка при тестировании"

        counter = Counter(results)

        text = f"📊 Тестирование распределения ({trials} попыток):\n\n"
        total = sum(counter.values())

        for rarity, chance in sorted(RARITIES.items(), key=lambda x: x[1], reverse=True):
            count = counter.get(rarity, 0)
            percentage = (count / total) * 100 if total > 0 else 0
            expected = chance

            # Определяем символ для отклонения
            if abs(percentage - expected) < 1:
                diff_symbol = "✅"  # Отлично
            elif abs(percentage - expected) < 3:
                diff_symbol = "⚠️"  # Нормально
            else:
                diff_symbol = "❌"  # Плохо

            # Добавляем информацию о том, сколько карт этой редкости в базе
            cards_count = len([c for c in cards if c['rarity'] == rarity])

            text += f"{rarity}:\n"
            text += f"  • Карт в базе: {cards_count}\n"
            text += f"  • Ожидалось: {expected:.2f}%\n"
            text += f"  • Получено: {percentage:.2f}% ({count} раз) {diff_symbol}\n\n"

        return text

    @staticmethod
    def add_card_to_user(user_id, card_id):
        users = UserManager.get_all_users()
        user_id_str = str(user_id)
        if user_id_str in users:
            if card_id not in users[user_id_str]['cards']:
                users[user_id_str]['cards'].append(card_id)
                UserManager.save_users(users)

                # Обновляем владельца карты
                cards = CardManager.get_all_cards()
                for card in cards:
                    if card['id'] == card_id:
                        card['owner_id'] = user_id_str
                        break
                CardManager.save_cards(cards)
                return True
        return False

    @staticmethod
    def remove_card_from_user(user_id, card_id):
        users = UserManager.get_all_users()
        user_id_str = str(user_id)
        if user_id_str in users and card_id in users[user_id_str]['cards']:
            users[user_id_str]['cards'].remove(card_id)
            UserManager.save_users(users)

            # Обновляем владельца карты
            cards = CardManager.get_all_cards()
            for card in cards:
                if card['id'] == card_id:
                    card['owner_id'] = None
                    break
            CardManager.save_cards(cards)
            return True
        return False

    @staticmethod
    def delete_card(card_id):
        cards = CardManager.get_all_cards()
        card_to_delete = None
        for card in cards:
            if card['id'] == card_id:
                card_to_delete = card
                break

        if card_to_delete:
            # Удаляем изображение если есть
            if card_to_delete.get('image_path') and os.path.exists(card_to_delete['image_path']):
                try:
                    os.remove(card_to_delete['image_path'])
                except:
                    pass

        cards = [card for card in cards if card['id'] != card_id]
        CardManager.save_cards(cards)

        # Удаляем карту у всех пользователей
        users = UserManager.get_all_users()
        for user_id in users:
            if card_id in users[user_id]['cards']:
                users[user_id]['cards'].remove(card_id)
        UserManager.save_users(users)

        # Удаляем из маркетплейса
        listings = MarketManager.get_all_listings()
        listings = [l for l in listings if l['card_id'] != card_id]
        MarketManager.save_listings(listings)

        return True

    @staticmethod
    def get_cards_by_creator(creator_id):
        cards = CardManager.get_all_cards()
        creator_id_str = str(creator_id)
        return [card for card in cards if card.get('created_by') == creator_id_str]

# Класс для работы с маркетплейсом
class MarketManager:
    @staticmethod
    def get_all_listings():
        return safe_json_load(MARKET_FILE, [])

    @staticmethod
    def save_listings(listings):
        with open(MARKET_FILE, 'w', encoding='utf-8') as f:
            json.dump(listings, f, ensure_ascii=False, indent=4)

    @staticmethod
    def add_listing(seller_id, card_id, price):
        listings = MarketManager.get_all_listings()
        listing = {
            'id': str(uuid.uuid4())[:8],
            'seller_id': str(seller_id),
            'card_id': card_id,
            'price': price,
            'created_at': datetime.now().isoformat()
        }
        listings.append(listing)
        MarketManager.save_listings(listings)
        return listing['id']

    @staticmethod
    def remove_listing(listing_id):
        listings = MarketManager.get_all_listings()
        listings = [l for l in listings if l['id'] != listing_id]
        MarketManager.save_listings(listings)

# Класс для работы с ролями
class RoleManager:
    @staticmethod
    def get_roles():
        return safe_json_load(ROLES_FILE, {'admins': [], 'card_creators': []})

    @staticmethod
    def save_roles(roles):
        with open(ROLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(roles, f, ensure_ascii=False, indent=4)

    @staticmethod
    def is_admin(user_id):
        roles = RoleManager.get_roles()
        return str(user_id) in roles['admins']

    @staticmethod
    def can_create_cards(user_id):
        roles = RoleManager.get_roles()
        return str(user_id) in roles['card_creators'] or RoleManager.is_admin(user_id)

    @staticmethod
    def can_edit_all_cards(user_id):
        return RoleManager.is_admin(user_id)

    @staticmethod
    def can_edit_card(user_id, card):
        return RoleManager.is_admin(user_id) or str(user_id) == card.get('created_by')

    @staticmethod
    def add_admin(user_id):
        roles = RoleManager.get_roles()
        user_id_str = str(user_id)
        if user_id_str not in roles['admins']:
            roles['admins'].append(user_id_str)
            RoleManager.save_roles(roles)
            return True
        return False

    @staticmethod
    def remove_admin(user_id):
        roles = RoleManager.get_roles()
        user_id_str = str(user_id)
        if user_id_str in roles['admins']:
            roles['admins'].remove(user_id_str)
            RoleManager.save_roles(roles)
            return True
        return False

    @staticmethod
    def add_card_creator(user_id):
        roles = RoleManager.get_roles()
        user_id_str = str(user_id)
        if user_id_str not in roles['card_creators']:
            roles['card_creators'].append(user_id_str)
            RoleManager.save_roles(roles)
            return True
        return False

    @staticmethod
    def remove_card_creator(user_id):
        roles = RoleManager.get_roles()
        user_id_str = str(user_id)
        if user_id_str in roles['card_creators']:
            roles['card_creators'].remove(user_id_str)
            RoleManager.save_roles(roles)
            return True
        return False

    @staticmethod
    def get_all_admins():
        roles = RoleManager.get_roles()
        return roles['admins']

    @staticmethod
    def get_all_creators():
        roles = RoleManager.get_roles()
        return roles['card_creators']

# Класс для работы с бэкапами
class BackupManager:
    @staticmethod
    def create_backup():
        """Создает ZIP архив со всеми данными"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.zip"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Добавляем JSON файлы
            for file in [USERS_FILE, CARDS_FILE, MARKET_FILE, ROLES_FILE]:
                if os.path.exists(file):
                    arcname = os.path.basename(file)
                    zipf.write(file, arcname)

            # Добавляем изображения
            if os.path.exists(IMAGES_DIR):
                for root, dirs, files in os.walk(IMAGES_DIR):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('images', file)
                        zipf.write(file_path, arcname)

        return backup_path

    @staticmethod
    def restore_from_backup(backup_file):
        """Восстанавливает данные из ZIP архива"""
        try:
            with zipfile.ZipFile(backup_file, 'r') as zipf:
                # Создаем временную директорию для распаковки
                temp_dir = os.path.join(DATA_DIR, 'temp_restore')
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)

                # Распаковываем все файлы
                zipf.extractall(temp_dir)

                # Восстанавливаем JSON файлы
                json_files = ['users.json', 'cards.json', 'market.json', 'roles.json']
                for json_file in json_files:
                    src = os.path.join(temp_dir, json_file)
                    dst = os.path.join(DATA_DIR, json_file)
                    if os.path.exists(src):
                        shutil.copy2(src, dst)

                # Восстанавливаем изображения
                images_src = os.path.join(temp_dir, 'images')
                if os.path.exists(images_src):
                    # Очищаем текущую папку с изображениями
                    if os.path.exists(IMAGES_DIR):
                        shutil.rmtree(IMAGES_DIR)
                    # Копируем новые изображения
                    shutil.copytree(images_src, IMAGES_DIR)

                # Удаляем временную директорию
                shutil.rmtree(temp_dir)

            return True
        except Exception as e:
            logger.error(f"Ошибка при восстановлении из бэкапа: {e}")
            return False

    @staticmethod
    def get_backups_list():
        """Возвращает список доступных бэкапов"""
        backups = []
        if os.path.exists(BACKUP_DIR):
            for file in os.listdir(BACKUP_DIR):
                if file.startswith('backup_') and file.endswith('.zip'):
                    file_path = os.path.join(BACKUP_DIR, file)
                    size = os.path.getsize(file_path)
                    created = datetime.fromtimestamp(os.path.getctime(file_path))
                    backups.append({
                        'filename': file,
                        'path': file_path,
                        'size': size,
                        'created': created
                    })
        return sorted(backups, key=lambda x: x['created'], reverse=True)

# Консольное управление админами
class ConsoleAdminManager:
    def __init__(self):
        self.running = True
        self.thread = threading.Thread(target=self.console_listener)
        self.thread.daemon = True
        self.thread.start()

    def console_listener(self):
        print("\n" + "="*50)
        print("КОНСОЛЬНОЕ УПРАВЛЕНИЕ АДМИНАМИ")
        print("="*50)
        print("Доступные команды:")
        print("  /addadmin <user_id or @username> - добавить админа")
        print("  /removeadmin <user_id or @username> - удалить админа")
        print("  /addcreator <user_id or @username> - добавить создателя карт")
        print("  /removecreator <user_id or @username> - удалить создателя карт")
        print("  /listadmins - список всех админов")
        print("  /listcreators - список всех создателей карт")
        print("  /backup - создать бэкап")
        print("  /restore <filename> - восстановить из бэкапа")
        print("  /listbackups - список бэкапов")
        print("  /help - показать это сообщение")
        print("  /exit - выход из консольного управления")
        print("="*50 + "\n")

        while self.running:
            try:
                # Неблокирующее чтение из stdin
                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                    command = sys.stdin.readline().strip()
                    if command:
                        self.process_command(command)
            except Exception as e:
                logger.error(f"Ошибка в консольном управлении: {e}")

    def process_command(self, command):
        parts = command.split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == '/addadmin' and len(parts) > 1:
            self.add_admin(parts[1])
        elif cmd == '/removeadmin' and len(parts) > 1:
            self.remove_admin(parts[1])
        elif cmd == '/addcreator' and len(parts) > 1:
            self.add_creator(parts[1])
        elif cmd == '/removecreator' and len(parts) > 1:
            self.remove_creator(parts[1])
        elif cmd == '/listadmins':
            self.list_admins()
        elif cmd == '/listcreators':
            self.list_creators()
        elif cmd == '/backup':
            self.create_backup()
        elif cmd == '/restore' and len(parts) > 1:
            self.restore_backup(parts[1])
        elif cmd == '/listbackups':
            self.list_backups()
        elif cmd == '/help':
            self.show_help()
        elif cmd == '/exit':
            self.running = False
            print("Консольное управление остановлено")
        else:
            print(f"Неизвестная команда: {cmd}")

    def get_user_id_from_input(self, user_input):
        """Получить ID пользователя из ввода (число или @username)"""
        # Если это число, просто возвращаем
        if user_input.isdigit():
            return user_input

        # Если это @username, ищем пользователя
        if user_input.startswith('@'):
            username = user_input[1:]
        else:
            username = user_input

        user_id, user_data = UserManager.get_user_by_username(username)
        if user_id:
            return user_id
        else:
            print(f"❌ Пользователь с username @{username} не найден в базе")
            return None

    def add_admin(self, user_input):
        user_id = self.get_user_id_from_input(user_input)
        if not user_id:
            return

        if RoleManager.add_admin(user_id):
            print(f"✅ Пользователь {user_id} добавлен в админы")

            # Уведомление пользователя в Telegram
            try:
                bot.send_message(int(user_id), "👑 Вам выданы права администратора!")
            except:
                pass
        else:
            print(f"ℹ️ Пользователь {user_id} уже является админом")

    def remove_admin(self, user_input):
        user_id = self.get_user_id_from_input(user_input)
        if not user_id:
            return

        if RoleManager.remove_admin(user_id):
            print(f"✅ Пользователь {user_id} удален из админов")

            # Уведомление пользователя в Telegram
            try:
                bot.send_message(int(user_id), "👑 Ваши права администратора были отозваны.")
            except:
                pass
        else:
            print(f"ℹ️ Пользователь {user_id} не является админом")

    def add_creator(self, user_input):
        user_id = self.get_user_id_from_input(user_input)
        if not user_id:
            return

        if RoleManager.add_card_creator(user_id):
            print(f"✅ Пользователь {user_id} добавлен в создатели карт")

            # Уведомление пользователя в Telegram
            try:
                bot.send_message(int(user_id), "🎴 Вам выданы права создателя карт!")
            except:
                pass
        else:
            print(f"ℹ️ Пользователь {user_id} уже является создателем карт")

    def remove_creator(self, user_input):
        user_id = self.get_user_id_from_input(user_input)
        if not user_id:
            return

        if RoleManager.remove_card_creator(user_id):
            print(f"✅ Пользователь {user_id} удален из создателей карт")

            # Уведомление пользователя в Telegram
            try:
                bot.send_message(int(user_id), "🎴 Ваши права создателя карт были отозваны.")
            except:
                pass
        else:
            print(f"ℹ️ Пользователь {user_id} не является создателем карт")

    def list_admins(self):
        admins = RoleManager.get_all_admins()
        if admins:
            print("\n👑 Список администраторов:")
            for admin_id in admins:
                # Пытаемся получить username
                users = UserManager.get_all_users()
                user_data = users.get(admin_id, {})
                username = user_data.get('username', 'Нет username')
                first_name = user_data.get('first_name', '')
                print(f"  - ID: {admin_id} | @{username} | {first_name}")
        else:
            print("📭 Нет администраторов")

    def list_creators(self):
        creators = RoleManager.get_all_creators()
        if creators:
            print("\n🎴 Список создателей карт:")
            for creator_id in creators:
                # Пытаемся получить username
                users = UserManager.get_all_users()
                user_data = users.get(creator_id, {})
                username = user_data.get('username', 'Нет username')
                first_name = user_data.get('first_name', '')
                print(f"  - ID: {creator_id} | @{username} | {first_name}")
        else:
            print("📭 Нет создателей карт")

    def create_backup(self):
        print("📦 Создание бэкапа...")
        backup_path = BackupManager.create_backup()
        print(f"✅ Бэкап создан: {os.path.basename(backup_path)}")

    def restore_backup(self, filename):
        backup_path = os.path.join(BACKUP_DIR, filename)
        if not os.path.exists(backup_path):
            print(f"❌ Бэкап {filename} не найден!")
            return

        print(f"🔄 Восстановление из {filename}...")
        if BackupManager.restore_from_backup(backup_path):
            print("✅ Данные успешно восстановлены!")
        else:
            print("❌ Ошибка при восстановлении!")

    def list_backups(self):
        backups = BackupManager.get_backups_list()
        if not backups:
            print("📭 Нет доступных бэкапов")
            return

        print("\n📋 Доступные бэкапы:")
        for backup in backups:
            size_kb = backup['size'] / 1024
            created_str = backup['created'].strftime("%Y-%m-%d %H:%M:%S")
            print(f"  • {backup['filename']} ({size_kb:.1f} KB) - {created_str}")

    def show_help(self):
        print("\nДоступные команды:")
        print("  /addadmin <user_id or @username> - добавить админа")
        print("  /removeadmin <user_id or @username> - удалить админа")
        print("  /addcreator <user_id or @username> - добавить создателя карт")
        print("  /removecreator <user_id or @username> - удалить создателя карт")
        print("  /listadmins - список всех админов")
        print("  /listcreators - список всех создателей карт")
        print("  /backup - создать бэкап")
        print("  /restore <filename> - восстановить из бэкапа")
        print("  /listbackups - список бэкапов")
        print("  /help - показать это сообщение")
        print("  /exit - выход из консольного управления")

# Функция для создания клавиатуры с редкостями
def get_rarity_keyboard(current_rarity=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for rarity, chance in RARITIES.items():
        text = f"{rarity} ({chance}%)"
        if rarity == current_rarity:
            text = "✅ " + text
        btn = types.InlineKeyboardButton(text, callback_data=f"rarity_{rarity}")
        markup.add(btn)
    btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_creation")
    markup.add(btn_cancel)
    return markup

# Функция для создания клавиатуры отмены
def get_cancel_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_creation")
    markup.add(btn_cancel)
    return markup

# Функция для создания клавиатуры редактирования карты
def get_edit_card_keyboard(card_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_name = types.InlineKeyboardButton("📝 Название", callback_data=f"edit_name_{card_id}")
    btn_rarity = types.InlineKeyboardButton("📊 Редкость", callback_data=f"edit_rarity_{card_id}")
    btn_positive = types.InlineKeyboardButton("✅ Положительное", callback_data=f"edit_positive_{card_id}")
    btn_negative = types.InlineKeyboardButton("❌ Отрицательное", callback_data=f"edit_negative_{card_id}")
    btn_price = types.InlineKeyboardButton("💰 Цена", callback_data=f"edit_price_{card_id}")
    btn_coins = types.InlineKeyboardButton("🪙 Монеты", callback_data=f"edit_coins_{card_id}")
    btn_image = types.InlineKeyboardButton("🖼 Изображение", callback_data=f"edit_image_{card_id}")
    btn_back = types.InlineKeyboardButton("◀ Назад", callback_data=f"card_info_{card_id}")
    markup.add(btn_name, btn_rarity, btn_positive, btn_negative, btn_price, btn_coins, btn_image, btn_back)
    return markup

# Функция для форматирования времени ожидания
def format_wait_time(seconds):
    minutes = seconds // 60
    secs = seconds % 60
    if minutes > 0:
        return f"{minutes} мин {secs} сек"
    else:
        return f"{secs} сек"

# Функция для анимированного выпадения карты с защитой от rate limit
def animated_card_drop(chat_id, card, user_id):
    # Анимация загрузки
    animation_frames = ["🎴", "🃏", "🎴", "🃏", "⭐"]
    msg = bot.send_message(chat_id, "Выпадение карты...")

    for frame in animation_frames:
        time.sleep(0.5)
        try:
            bot.edit_message_text(f"{frame} Выпадение карты...", chat_id, msg.message_id)
        except:
            pass

    time.sleep(0.5)

    # Формирование сообщения с картой
    card_text = f"🎴 <b>{card['name']}</b>\n"
    card_text += f"📊 Редкость: {card['rarity']}\n"

    if card.get('positive'):
        card_text += f"✅ + {card['positive']}\n"
    if card.get('negative'):
        card_text += f"❌ - {card['negative']}\n"

    card_text += f"💰 Цена: {card['price']} zhm\n"

    if card.get('coins'):
        card_text += f"🪙 +{card['coins']} монет"

    # Отправка с задержкой для избежания rate limit
    time.sleep(1)

    # Отправка изображения если есть
    try:
        if card.get('image_path') and os.path.exists(card['image_path']):
            with open(card['image_path'], 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=card_text, parse_mode='HTML')
        else:
            bot.send_message(chat_id, card_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка при отправке карты: {e}")
        try:
            # Пробуем отправить только текст
            bot.send_message(chat_id, card_text, parse_mode='HTML')
        except:
            pass

    # Добавление карты пользователю
    CardManager.add_card_to_user(user_id, card['id'])

    # Начисление монет за карту
    if card.get('coins'):
        UserManager.update_balance(user_id, card['coins'])

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    # Регистрация пользователя
    user = UserManager.get_user(user_id)
    UserManager.update_user_info(user_id, first_name, last_name, username)

    welcome_text = (
        f"👋 Привет, {first_name}!\n\n"
        f"🎴 Я бот для выпадения случайных карт!\n\n"
        f"Команды:\n"
        f"🎲 Отправь 'жоркарта' (или другие падежи) - получить случайную карту\n"
        f"💰 /balance - проверить баланс\n"
        f"📦 /mycards - мои карты\n"
        f"🏪 /market - маркетплейс\n"
        f"📊 /stats - статистика\n"
        f"⏳ Задержка между выпадениями: 5 минут\n\n"
        f"📈 Шансы выпадения карт:\n"
    )

    # Добавляем информацию о шансах
    for rarity, chance in sorted(RARITIES.items(), key=lambda x: x[1], reverse=True):
        welcome_text += f"  • {rarity}: {chance}%\n"

    if RoleManager.is_admin(user_id) or RoleManager.can_create_cards(user_id):
        welcome_text += "\n⚙️ Панель управления: /admin"

    bot.send_message(message.chat.id, welcome_text)

# Обработчик для выпадения карты
@bot.message_handler(func=lambda message: 'жоркарта' in message.text.lower() or 
                    any(padezh in message.text.lower() for padezh in ['жоркарты', 'жоркарте', 'жоркарту', 'жоркартой', 'жоркартах']))
def drop_card(message):
    user_id = message.from_user.id

    # Проверка на задержку
    can_drop, wait_time = UserManager.can_drop_card(user_id)

    if not can_drop:
        wait_str = format_wait_time(wait_time)
        bot.send_message(message.chat.id, f"⏳ Подождите еще {wait_str} перед следующим выпадением!")
        return

    card = CardManager.get_random_card()

    if not card:
        bot.send_message(message.chat.id, "😕 В базе пока нет карт! Обратитесь к администратору.")
        return

    # Обновляем время последнего выпадения
    UserManager.update_last_drop(user_id)

    # Запускаем анимацию в отдельном потоке
    Thread(target=animated_card_drop, args=(message.chat.id, card, user_id)).start()

# Команда баланса
@bot.message_handler(commands=['balance'])
def balance_command(message):
    user_id = message.from_user.id
    user = UserManager.get_user(user_id)
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {user['balance']} zhm")

# Команда моих карт
@bot.message_handler(commands=['mycards'])
def mycards_command(message):
    user_id = str(message.from_user.id)
    user = UserManager.get_user(user_id)
    cards = CardManager.get_all_cards()

    user_cards = [card for card in cards if card['id'] in user['cards']]

    if not user_cards:
        bot.send_message(message.chat.id, "📭 У вас пока нет карт!")
        return

    # Группируем по редкости
    cards_by_rarity = {}
    for card in user_cards:
        rarity = card['rarity']
        if rarity not in cards_by_rarity:
            cards_by_rarity[rarity] = []
        cards_by_rarity[rarity].append(card)

    text = "📦 Ваши карты:\n\n"

    # Сортируем по редкости (самые редкие сверху)
    sorted_rarities = sorted(cards_by_rarity.keys(), key=lambda r: RARITIES.get(r, 0))

    for rarity in sorted_rarities:
        text += f"📊 {rarity}:\n"
        for card in cards_by_rarity[rarity]:
            text += f"  • 🎴 {card['name']} - {card['price']} zhm\n"
        text += "\n"

    # Разбиваем на части если текст слишком длинный
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            bot.send_message(message.chat.id, text[i:i+4000])
    else:
        bot.send_message(message.chat.id, text)

# Команда маркетплейса
@bot.message_handler(commands=['market'])
def market_command(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_list = types.InlineKeyboardButton("📋 Список продаж", callback_data="market_list")
    btn_sell = types.InlineKeyboardButton("💰 Продать карту", callback_data="market_sell")
    btn_buy = types.InlineKeyboardButton("🛒 Купить карту", callback_data="market_buy")
    btn_back = types.InlineKeyboardButton("◀ Закрыть", callback_data="market_back")
    markup.add(btn_list, btn_sell, btn_buy, btn_back)

    bot.send_message(message.chat.id, "🏪 Маркетплейс zhm\nВыберите действие:", reply_markup=markup)

# Статистика
@bot.message_handler(commands=['stats'])
def stats_command(message):
    users = UserManager.get_all_users()
    cards = CardManager.get_all_cards()
    listings = MarketManager.get_all_listings()

    # Подсчет карт по редкостям
    rarity_stats = {}
    for card in cards:
        rarity = card['rarity']
        rarity_stats[rarity] = rarity_stats.get(rarity, 0) + 1

    text = (
        f"📊 Статистика бота:\n\n"
        f"👥 Пользователей: {len(users)}\n"
        f"🎴 Всего карт: {len(cards)}\n"
        f"🏪 Активных продаж: {len(listings)}\n\n"
        f"📈 Карты по редкостям:\n"
    )

    for rarity, chance in sorted(RARITIES.items(), key=lambda x: x[1], reverse=True):
        count = rarity_stats.get(rarity, 0)
        percentage = (count / len(cards) * 100) if cards else 0
        text += f"  • {rarity}: {count} шт. ({percentage:.1f}% от всех карт)\n"

    bot.send_message(message.chat.id, text)

# Админ-панель (доступна админам и креаторам)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id

    # Проверяем, есть ли у пользователя права (админ или создатель карт)
    if not (RoleManager.is_admin(user_id) or RoleManager.can_create_cards(user_id)):
        bot.send_message(message.chat.id, "🚫 У вас нет прав доступа к панели управления!")
        return

    # Создаем клавиатуру в зависимости от прав
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Кнопка создания карты доступна всем (и админам, и креаторам)
    btn_create_card = types.InlineKeyboardButton("➕ Создать карту", callback_data="admin_create_card")
    markup.add(btn_create_card)

    if RoleManager.is_admin(user_id):
        # Для админов - полный доступ
        btn_manage_users = types.InlineKeyboardButton("👤 Управление пользователями", callback_data="admin_users_menu")
        btn_all_cards = types.InlineKeyboardButton("📋 Все карты", callback_data="admin_all_cards")
        btn_test_drops = types.InlineKeyboardButton("🎲 Тест выпадений", callback_data="admin_test_drops")
        btn_console_info = types.InlineKeyboardButton("ℹ️ Консольное управление", callback_data="admin_console_info")
        btn_stats = types.InlineKeyboardButton("📊 Детальная статистика", callback_data="admin_detailed_stats")
        btn_backup = types.InlineKeyboardButton("💾 Экспорт/Импорт", callback_data="admin_backup_menu")
        markup.add(btn_manage_users, btn_all_cards, btn_test_drops, btn_console_info, btn_stats, btn_backup)
    else:
        # Для креаторов - только создание и просмотр своих карт
        btn_my_cards = types.InlineKeyboardButton("📋 Мои созданные карты", callback_data="admin_my_cards")
        markup.add(btn_my_cards)

    btn_back = types.InlineKeyboardButton("◀ Закрыть", callback_data="admin_back")
    markup.add(btn_back)

    # Персонализированное приветствие
    if RoleManager.is_admin(user_id):
        welcome = "👑 Админ-панель"
    else:
        welcome = "🎴 Панель создателя карт"

    bot.send_message(message.chat.id, f"{welcome}\nВыберите действие:", reply_markup=markup)

# Обработчики callback-запросов
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id

    if call.data == "admin_create_card":
        if not RoleManager.can_create_cards(user_id):
            bot.answer_callback_query(call.id, "🚫 У вас нет прав на создание карт!")
            return

        # Сохраняем состояние создания карты
        card_creation_states[user_id] = {'step': 'name'}

        markup = get_cancel_keyboard()
        msg = bot.send_message(call.message.chat.id, "Введите название карты:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_card_name, user_id)

    elif call.data == "admin_my_cards":
        if not RoleManager.can_create_cards(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        cards = CardManager.get_cards_by_creator(user_id)

        if not cards:
            bot.send_message(call.message.chat.id, "📭 Вы еще не создали ни одной карты!")
            return

        # Создаем клавиатуру для навигации по картам
        markup = types.InlineKeyboardMarkup(row_width=1)
        for i, card in enumerate(cards[:10]):  # Показываем первые 10 карт
            btn = types.InlineKeyboardButton(
                f"{card['name']} - {card['rarity']}",
                callback_data=f"card_info_{card['id']}"
            )
            markup.add(btn)

        btn_back = types.InlineKeyboardButton("◀ Назад", callback_data="admin_back")
        markup.add(btn_back)

        bot.edit_message_text("📋 Ваши созданные карты:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_test_drops":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        bot.answer_callback_query(call.id, "🔄 Тестирую распределение...")
        test_result = CardManager.test_drop_distribution(10000)
        bot.send_message(call.message.chat.id, test_result)

    elif call.data == "admin_users_menu":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_list = types.InlineKeyboardButton("📋 Список пользователей", callback_data="admin_users_list")
        btn_search = types.InlineKeyboardButton("🔍 Поиск пользователя", callback_data="admin_users_search")
        btn_balance = types.InlineKeyboardButton("💰 Выдать монеты", callback_data="admin_users_add_coins")
        btn_all_coins = types.InlineKeyboardButton("👥 Выдать всем монеты", callback_data="admin_users_all_coins")
        btn_back = types.InlineKeyboardButton("◀ Назад", callback_data="admin_back")
        markup.add(btn_list, btn_search, btn_balance, btn_all_coins, btn_back)

        bot.edit_message_text("👤 Управление пользователями:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_users_list":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        users = UserManager.get_all_users()
        if not users:
            bot.send_message(call.message.chat.id, "📭 Нет зарегистрированных пользователей!")
            return

        text = "📋 Список пользователей:\n\n"
        for uid, user_data in list(users.items())[:50]:  # Ограничим 50 пользователей
            username = user_data.get('username', 'Нет username')
            first_name = user_data.get('first_name', '')
            balance = user_data.get('balance', 0)
            cards_count = len(user_data.get('cards', []))
            text += f"🆔 {uid}\n👤 {first_name} (@{username})\n💰 {balance} zhm | 🎴 {cards_count} карт\n\n"

        # Разбиваем на части если текст слишком длинный
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                bot.send_message(call.message.chat.id, text[i:i+4000])
        else:
            bot.send_message(call.message.chat.id, text)

    elif call.data == "admin_users_search":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        markup = get_cancel_keyboard()
        msg = bot.send_message(call.message.chat.id, "Введите ID пользователя или @username для поиска:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_user_search)

    elif call.data == "admin_users_add_coins":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        markup = get_cancel_keyboard()
        msg = bot.send_message(call.message.chat.id, "Введите ID пользователя или @username и сумму через пробел\nНапример: @username 100", reply_markup=markup)
        bot.register_next_step_handler(msg, process_add_coins)

    elif call.data == "admin_users_all_coins":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        markup = get_cancel_keyboard()
        msg = bot.send_message(call.message.chat.id, "Введите сумму монет для выдачи ВСЕМ пользователям:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_add_coins_to_all)

    elif call.data == "admin_detailed_stats":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        users = UserManager.get_all_users()
        cards = CardManager.get_all_cards()
        listings = MarketManager.get_all_listings()
        creators = RoleManager.get_all_creators()

        total_balance = sum(u.get('balance', 0) for u in users.values())
        total_cards = sum(len(u.get('cards', [])) for u in users.values())

        text = (
            f"📊 Детальная статистика:\n\n"
            f"👥 Всего пользователей: {len(users)}\n"
            f"💰 Общий баланс: {total_balance} zhm\n"
            f"🎴 Всего карт в игре: {len(cards)}\n"
            f"📦 Карт у пользователей: {total_cards}\n"
            f"🏪 Активных продаж: {len(listings)}\n"
            f"💎 Средний баланс: {total_balance // max(len(users), 1)} zhm\n"
            f"👑 Админов: {len(RoleManager.get_all_admins())}\n"
            f"🎨 Создателей карт: {len(creators)}\n"
        )

        bot.send_message(call.message.chat.id, text)

    elif call.data == "admin_backup_menu":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_export = types.InlineKeyboardButton("📤 Экспорт данных", callback_data="admin_export_data")
        btn_import = types.InlineKeyboardButton("📥 Импорт данных", callback_data="admin_import_data")
        btn_list = types.InlineKeyboardButton("📋 Список бэкапов", callback_data="admin_list_backups")
        btn_back = types.InlineKeyboardButton("◀ Назад", callback_data="admin_back")
        markup.add(btn_export, btn_import, btn_list, btn_back)

        bot.edit_message_text("💾 Экспорт/Импорт данных\nВыберите действие:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_export_data":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        bot.answer_callback_query(call.id, "📦 Создание бэкапа...")
        backup_path = BackupManager.create_backup()

        # Отправляем файл пользователю
        with open(backup_path, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"✅ Бэкап создан: {os.path.basename(backup_path)}")

    elif call.data == "admin_import_data":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        msg = bot.send_message(call.message.chat.id, "📥 Отправьте ZIP файл с бэкапом для восстановления данных:")
        bot.register_next_step_handler(msg, process_import_backup)

    elif call.data == "admin_list_backups":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        backups = BackupManager.get_backups_list()
        if not backups:
            bot.send_message(call.message.chat.id, "📭 Нет доступных бэкапов")
            return

        text = "📋 Доступные бэкапы:\n\n"
        for backup in backups[:10]:  # Показываем последние 10
            size_kb = backup['size'] / 1024
            created_str = backup['created'].strftime("%Y-%m-%d %H:%M:%S")
            text += f"📦 {backup['filename']}\n"
            text += f"   📏 {size_kb:.1f} KB | 📅 {created_str}\n\n"

        bot.send_message(call.message.chat.id, text)

    elif call.data == "admin_console_info":
        info_text = (
            "ℹ️ Управление администраторами и создателями карт\n"
            "производится через консоль!\n\n"
            "Команды консоли:\n"
            "/addadmin <id или @username>\n"
            "/removeadmin <id или @username>\n"
            "/addcreator <id или @username>\n"
            "/removecreator <id или @username>\n"
            "/listadmins\n"
            "/listcreators\n"
            "/backup - создать бэкап\n"
            "/restore <filename> - восстановить из бэкапа\n"
            "/listbackups - список бэкапов\n"
            "/help\n\n"
            "Для получения ID пользователя:\n"
            "1. Используйте 'Управление пользователями' в админ-панели\n"
            "2. Попросите пользователя написать боту"
        )
        bot.send_message(call.message.chat.id, info_text)

    elif call.data == "admin_all_cards":
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        cards = CardManager.get_all_cards()
        if not cards:
            bot.send_message(call.message.chat.id, "📭 Карт пока нет!")
            return

        # Создаем клавиатуру для навигации по картам
        markup = types.InlineKeyboardMarkup(row_width=1)
        for i, card in enumerate(cards[:10]):  # Показываем первые 10 карт
            btn = types.InlineKeyboardButton(
                f"{card['name']} - {card['rarity']}",
                callback_data=f"card_info_{card['id']}"
            )
            markup.add(btn)

        if len(cards) > 10:
            btn_next = types.InlineKeyboardButton("▶ Далее", callback_data="cards_page_2")
            markup.add(btn_next)

        btn_back = types.InlineKeyboardButton("◀ Назад", callback_data="admin_back")
        markup.add(btn_back)

        bot.edit_message_text("📋 Список всех карт (страница 1):", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("card_info_"):
        card_id = call.data.replace("card_info_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        owner_info = "Никому не принадлежит"
        if card['owner_id']:
            owner = UserManager.get_user_by_id(card['owner_id'])
            if owner:
                owner_info = f"ID: {card['owner_id']} (@{owner.get('username', 'Нет username')})"

        creator_info = "Неизвестен"
        if card.get('created_by'):
            creator = UserManager.get_user_by_id(card['created_by'])
            if creator:
                creator_info = f"@{creator.get('username', 'Нет username')}"

        edit_info = ""
        if card.get('last_edited'):
            edit_time = datetime.fromisoformat(card['last_edited']).strftime("%Y-%m-%d %H:%M")
            editor = "Неизвестно"
            if card.get('edited_by'):
                editor_user = UserManager.get_user_by_id(card['edited_by'])
                if editor_user:
                    editor = f"@{editor_user.get('username', 'Нет username')}"
            edit_info = f"\n✏️ Последнее редактирование: {edit_time}\n   Редактор: {editor}"

        # Добавляем информацию о шансе выпадения
        drop_chance = RARITIES.get(card['rarity'], 0)

        text = (
            f"🎴 <b>{card['name']}</b>\n"
            f"🆔 ID: {card['id']}\n"
            f"📊 Редкость: {card['rarity']}\n"
            f"🎲 Шанс выпадения: {drop_chance}%\n"
            f"✅ + {card.get('positive', 'Нет')}\n"
            f"❌ - {card.get('negative', 'Нет')}\n"
            f"💰 Цена: {card['price']} zhm\n"
            f"🪙 Монет: {card.get('coins', 0)}\n"
            f"👤 Владелец: {owner_info}\n"
            f"🎨 Создатель: {creator_info}"
            f"{edit_info}\n"
            f"📅 Создана: {card.get('created_at', 'Неизвестно')[:10]}\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)

        # Кнопка редактирования (доступна создателю или админу)
        if RoleManager.can_edit_card(user_id, card):
            btn_edit = types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_card_{card_id}")
            markup.add(btn_edit)

        # Кнопка удаления (только для админов)
        if RoleManager.is_admin(user_id):
            btn_delete = types.InlineKeyboardButton("🗑 Удалить карту", callback_data=f"delete_card_{card_id}")
            markup.add(btn_delete)

        btn_back = types.InlineKeyboardButton("◀ Назад к списку", callback_data="admin_all_cards")
        markup.add(btn_back)

        try:
            if card.get('image_path') and os.path.exists(card['image_path']):
                with open(card['image_path'], 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption=text, parse_mode='HTML', reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка при отправке карты: {e}")
            bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)

    elif call.data.startswith("edit_card_"):
        card_id = call.data.replace("edit_card_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        if not RoleManager.can_edit_card(user_id, card):
            bot.answer_callback_query(call.id, "🚫 У вас нет прав на редактирование этой карты!")
            return

        # Показываем меню редактирования
        bot.edit_message_text(
            f"✏️ Редактирование карты: {card['name']}\n\nВыберите, что хотите изменить:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_edit_card_keyboard(card_id)
        )

    elif call.data.startswith("edit_name_"):
        card_id = call.data.replace("edit_name_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'name'}
        markup = get_cancel_keyboard()
        bot.edit_message_text(
            f"Текущее название: {card['name']}\n\nВведите новое название:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.register_next_step_handler(call.message, process_edit_field, user_id)

    elif call.data.startswith("edit_rarity_"):
        card_id = call.data.replace("edit_rarity_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'rarity'}
        bot.edit_message_text(
            f"Текущая редкость: {card['rarity']} (шанс {RARITIES.get(card['rarity'], 0)}%)\n\nВыберите новую редкость:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_rarity_keyboard(card['rarity'])
        )

    elif call.data.startswith("edit_positive_"):
        card_id = call.data.replace("edit_positive_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'positive'}
        markup = get_cancel_keyboard()
        current = card.get('positive', 'Нет')
        bot.edit_message_text(
            f"Текущий положительный текст: {current}\n\nВведите новый текст (или '-' если нет):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.register_next_step_handler(call.message, process_edit_field, user_id)

    elif call.data.startswith("edit_negative_"):
        card_id = call.data.replace("edit_negative_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'negative'}
        markup = get_cancel_keyboard()
        current = card.get('negative', 'Нет')
        bot.edit_message_text(
            f"Текущий отрицательный текст: {current}\n\nВведите новый текст (или '-' если нет):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.register_next_step_handler(call.message, process_edit_field, user_id)

    elif call.data.startswith("edit_price_"):
        card_id = call.data.replace("edit_price_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'price'}
        markup = get_cancel_keyboard()
        bot.edit_message_text(
            f"Текущая цена: {card['price']} zhm\n\nВведите новую цену (число):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.register_next_step_handler(call.message, process_edit_field, user_id)

    elif call.data.startswith("edit_coins_"):
        card_id = call.data.replace("edit_coins_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'coins'}
        markup = get_cancel_keyboard()
        bot.edit_message_text(
            f"Текущие монеты: {card.get('coins', 0)}\n\nВведите новое количество монет (число):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.register_next_step_handler(call.message, process_edit_field, user_id)

    elif call.data.startswith("edit_image_"):
        card_id = call.data.replace("edit_image_", "")
        card = CardManager.get_card(card_id)

        if not card:
            bot.answer_callback_query(call.id, "❌ Карта не найдена!")
            return

        card_editing_states[user_id] = {'card_id': card_id, 'field': 'image'}
        markup = get_cancel_keyboard()
        bot.edit_message_text(
            "Отправьте новое изображение для карты (или отправьте '-' чтобы удалить текущее):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.register_next_step_handler(call.message, process_edit_image, user_id)

    elif call.data.startswith("delete_card_"):
        if not RoleManager.is_admin(user_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен!")
            return

        card_id = call.data.replace("delete_card_", "")

        # Подтверждение удаления
        markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить удаление", callback_data=f"confirm_delete_{card_id}")
        btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data=f"card_info_{card_id}")
        markup.add(btn_confirm, btn_cancel)

        bot.send_message(call.message.chat.id, "⚠️ Вы уверены, что хотите удалить эту карту? Это действие нельзя отменить!", reply_markup=markup)

    elif call.data.startswith("confirm_delete_"):
        card_id = call.data.replace("confirm_delete_", "")

        if CardManager.delete_card(card_id):
            bot.answer_callback_query(call.id, "✅ Карта успешно удалена!")
            bot.send_message(call.message.chat.id, "✅ Карта удалена из базы данных.")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при удалении карты!")

    elif call.data == "cancel_creation":
        if user_id in card_creation_states:
            del card_creation_states[user_id]
        if user_id in card_editing_states:
            del card_editing_states[user_id]
        bot.answer_callback_query(call.id, "❌ Операция отменена")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel(call.message)

    elif call.data.startswith("rarity_"):
        rarity = call.data.replace("rarity_", "")

        if user_id in card_creation_states:
            # Режим создания
            card_creation_states[user_id]['rarity'] = rarity
            card_creation_states[user_id]['step'] = 'positive'

            markup = get_cancel_keyboard()
            bot.edit_message_text(f"Выбрана редкость: {rarity} (шанс {RARITIES[rarity]}%)\n\nВведите положительный текст карты (или отправьте '-' если нет):", 
                                call.message.chat.id, call.message.message_id, reply_markup=markup)
            bot.register_next_step_handler(call.message, process_card_positive, user_id)

        elif user_id in card_editing_states:
            # Режим редактирования
            state = card_editing_states[user_id]
            if state['field'] == 'rarity':
                card_id = state['card_id']
                card = CardManager.get_card(card_id)

                if card:
                    # Обновляем редкость
                    CardManager.update_card(card_id, {'rarity': rarity}, user_id)
                    bot.answer_callback_query(call.id, f"✅ Редкость обновлена! Новый шанс: {RARITIES[rarity]}%")
                    del card_editing_states[user_id]

                    # Показываем обновленную карту
                    callback_handler(types.CallbackQuery(
                        id=call.id,
                        from_user=call.from_user,
                        message=call.message,
                        data=f"card_info_{card_id}"
                    ))

    elif call.data == "market_list":
        listings = MarketManager.get_all_listings()
        cards = CardManager.get_all_cards()

        if not listings:
            bot.send_message(call.message.chat.id, "🏪 На маркетплейсе пока нет продаж!")
            return

        text = "📋 Продажи на маркетплейсе:\n\n"
        for listing in listings:
            card = next((c for c in cards if c['id'] == listing['card_id']), None)
            if card:
                text += f"ID: {listing['id']}\n"
                text += f"🎴 {card['name']} - {card['rarity']}\n"
                text += f"💰 Цена: {listing['price']} zhm\n"
                text += f"👤 Продавец: {listing['seller_id']}\n\n"

        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                bot.send_message(call.message.chat.id, text[i:i+4000])
        else:
            bot.send_message(call.message.chat.id, text)

    elif call.data == "market_sell":
        user_id_str = str(user_id)
        user = UserManager.get_user(user_id_str)
        cards = CardManager.get_all_cards()

        user_cards = [card for card in cards if card['id'] in user['cards']]

        if not user_cards:
            bot.answer_callback_query(call.id, "📭 У вас нет карт для продажи!")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for card in user_cards[:10]:  # Ограничим до 10 карт для удобства
            btn = types.InlineKeyboardButton(
                f"{card['name']} - {card['price']} zhm",
                callback_data=f"sell_{card['id']}"
            )
            markup.add(btn)

        btn_back = types.InlineKeyboardButton("◀ Назад", callback_data="market_back")
        markup.add(btn_back)

        bot.edit_message_text("Выберите карту для продажи:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("sell_"):
        card_id = call.data.split("_")[1]
        markup = get_cancel_keyboard()
        msg = bot.send_message(call.message.chat.id, "Введите цену продажи в zhm:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_sell_price, card_id)

    elif call.data == "market_buy":
        listings = MarketManager.get_all_listings()

        if not listings:
            bot.send_message(call.message.chat.id, "🏪 На маркетплейсе пока нет продаж!")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        cards = CardManager.get_all_cards()

        for listing in listings[:10]:
            card = next((c for c in cards if c['id'] == listing['card_id']), None)
            if card:
                btn = types.InlineKeyboardButton(
                    f"{card['name']} - {listing['price']} zhm",
                    callback_data=f"buy_{listing['id']}"
                )
                markup.add(btn)

        btn_back = types.InlineKeyboardButton("◀ Назад", callback_data="market_back")
        markup.add(btn_back)

        bot.edit_message_text("Выберите карту для покупки:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("buy_"):
        listing_id = call.data.split("_")[1]
        listings = MarketManager.get_all_listings()
        listing = next((l for l in listings if l['id'] == listing_id), None)

        if not listing:
            bot.answer_callback_query(call.id, "❌ Это объявление уже не существует!")
            return

        # Проверка баланса
        user = UserManager.get_user(user_id)
        if user['balance'] < listing['price']:
            bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Нужно {listing['price']} zhm")
            return

        # Проверка, что пользователь не покупает свою карту
        if str(user_id) == listing['seller_id']:
            bot.answer_callback_query(call.id, "❌ Нельзя купить свою собственную карту!")
            return

        # Совершение покупки
        UserManager.update_balance(user_id, -listing['price'])
        UserManager.update_balance(int(listing['seller_id']), listing['price'])

        # Передача карты
        CardManager.remove_card_from_user(int(listing['seller_id']), listing['card_id'])
        CardManager.add_card_to_user(user_id, listing['card_id'])

        # Удаление объявления
        MarketManager.remove_listing(listing_id)

        bot.answer_callback_query(call.id, "✅ Покупка успешно совершена!")
        bot.send_message(call.message.chat.id, f"✅ Вы купили карту за {listing['price']} zhm!")

    elif call.data == "admin_back" or call.data == "market_back":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        if call.data == "admin_back":
            admin_panel(call.message)
        else:
            market_command(call.message)

# Обработчики шагов создания карты
def process_card_name(message, user_id):
    if user_id not in card_creation_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, "❌ Создание карты отменено")
        admin_panel(message)
        return

    card_creation_states[user_id]['name'] = message.text
    card_creation_states[user_id]['step'] = 'rarity'

    bot.send_message(message.chat.id, "Выберите редкость карты:", reply_markup=get_rarity_keyboard())

def process_card_positive(message, user_id):
    if user_id not in card_creation_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, "❌ Создание карты отменено")
        admin_panel(message)
        return

    positive = message.text if message.text != '-' else ""
    card_creation_states[user_id]['positive'] = positive
    card_creation_states[user_id]['step'] = 'negative'

    markup = get_cancel_keyboard()
    msg = bot.send_message(message.chat.id, "Введите отрицательный текст карты (или отправьте '-' если нет):", reply_markup=markup)
    bot.register_next_step_handler(msg, process_card_negative, user_id)

def process_card_negative(message, user_id):
    if user_id not in card_creation_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, "❌ Создание карты отменено")
        admin_panel(message)
        return

    negative = message.text if message.text != '-' else ""
    card_creation_states[user_id]['negative'] = negative
    card_creation_states[user_id]['step'] = 'price'

    markup = get_cancel_keyboard()
    msg = bot.send_message(message.chat.id, "Введите цену карты (число):", reply_markup=markup)
    bot.register_next_step_handler(msg, process_card_price, user_id)

def process_card_price(message, user_id):
    if user_id not in card_creation_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, "❌ Создание карты отменено")
        admin_panel(message)
        return

    try:
        price = int(message.text)
        card_creation_states[user_id]['price'] = price
        card_creation_states[user_id]['step'] = 'coins'

        markup = get_cancel_keyboard()
        msg = bot.send_message(message.chat.id, "Введите количество монет, которое дает карта (число):", reply_markup=markup)
        bot.register_next_step_handler(msg, process_card_coins, user_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")
        return

def process_card_coins(message, user_id):
    if user_id not in card_creation_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, "❌ Создание карты отменено")
        admin_panel(message)
        return

    try:
        coins = int(message.text)
        card_creation_states[user_id]['coins'] = coins
        card_creation_states[user_id]['step'] = 'image'

        markup = get_cancel_keyboard()
        msg = bot.send_message(message.chat.id, "Отправьте изображение для карты (или отправьте '-' если без изображения):", reply_markup=markup)
        bot.register_next_step_handler(msg, process_card_image, user_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")
        return

def process_card_image(message, user_id):
    if user_id not in card_creation_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, "❌ Создание карты отменено")
        admin_panel(message)
        return

    card_data = card_creation_states[user_id]

    if message.text == '-':
        # Создание карты без изображения
        card_info = {
            'name': card_data['name'],
            'rarity': card_data['rarity'],
            'positive': card_data.get('positive', ''),
            'negative': card_data.get('negative', ''),
            'price': card_data['price'],
            'coins': card_data['coins'],
            'image_path': None
        }

        card_id = CardManager.add_card(card_info, user_id)
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, f"✅ Карта успешно создана! ID: {card_id}")
    elif message.photo:
        # Сохранение изображения
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Генерация имени файла
        filename = f"{uuid.uuid4()}.jpg"
        image_path = os.path.join(IMAGES_DIR, filename)

        with open(image_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        # Создание карты с изображением
        card_info = {
            'name': card_data['name'],
            'rarity': card_data['rarity'],
            'positive': card_data.get('positive', ''),
            'negative': card_data.get('negative', ''),
            'price': card_data['price'],
            'coins': card_data['coins'],
            'image_path': image_path
        }

        card_id = CardManager.add_card(card_info, user_id)
        del card_creation_states[user_id]
        bot.send_message(message.chat.id, f"✅ Карта успешно создана с изображением! ID: {card_id}")
    else:
        bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте изображение или '-'")
        return

    admin_panel(message)

# Обработчики редактирования карт
def process_edit_field(message, user_id):
    if user_id not in card_editing_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_editing_states[user_id]
        bot.send_message(message.chat.id, "❌ Редактирование отменено")
        admin_panel(message)
        return

    state = card_editing_states[user_id]
    card_id = state['card_id']
    field = state['field']

    card = CardManager.get_card(card_id)
    if not card:
        bot.send_message(message.chat.id, "❌ Карта не найдена!")
        del card_editing_states[user_id]
        return

    update_data = {}

    if field in ['name', 'positive', 'negative']:
        if field in ['positive', 'negative']:
            value = message.text if message.text != '-' else ""
        else:
            value = message.text
        update_data[field] = value

        if CardManager.update_card(card_id, update_data, user_id):
            bot.send_message(message.chat.id, f"✅ Поле '{field}' успешно обновлено!")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при обновлении!")

    elif field in ['price', 'coins']:
        try:
            value = int(message.text)
            update_data[field] = value

            if CardManager.update_card(card_id, update_data, user_id):
                bot.send_message(message.chat.id, f"✅ Поле '{field}' успешно обновлено!")
            else:
                bot.send_message(message.chat.id, "❌ Ошибка при обновлении!")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите число!")
            return

    del card_editing_states[user_id]

    # Показываем обновленную карту
    callback_handler(types.CallbackQuery(
        id='0',
        from_user=message.from_user,
        message=message,
        data=f"card_info_{card_id}"
    ))

def process_edit_image(message, user_id):
    if user_id not in card_editing_states:
        return

    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        del card_editing_states[user_id]
        bot.send_message(message.chat.id, "❌ Редактирование отменено")
        admin_panel(message)
        return

    state = card_editing_states[user_id]
    card_id = state['card_id']

    card = CardManager.get_card(card_id)
    if not card:
        bot.send_message(message.chat.id, "❌ Карта не найдена!")
        del card_editing_states[user_id]
        return

    update_data = {}

    if message.text == '-':
        # Удаление изображения
        if card.get('image_path') and os.path.exists(card['image_path']):
            try:
                os.remove(card['image_path'])
            except:
                pass
        update_data['image_path'] = None

        if CardManager.update_card(card_id, update_data, user_id):
            bot.send_message(message.chat.id, "✅ Изображение удалено!")

    elif message.photo:
        # Сохранение нового изображения
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Удаляем старое изображение
        if card.get('image_path') and os.path.exists(card['image_path']):
            try:
                os.remove(card['image_path'])
            except:
                pass

        # Генерация имени файла
        filename = f"{uuid.uuid4()}.jpg"
        image_path = os.path.join(IMAGES_DIR, filename)

        with open(image_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        update_data['image_path'] = image_path

        if CardManager.update_card(card_id, update_data, user_id):
            bot.send_message(message.chat.id, "✅ Изображение обновлено!")

    else:
        bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте изображение или '-'")
        return

    del card_editing_states[user_id]

    # Показываем обновленную карту
    callback_handler(types.CallbackQuery(
        id='0',
        from_user=message.from_user,
        message=message,
        data=f"card_info_{card_id}"
    ))

# Обработчик импорта бэкапа
def process_import_backup(message):
    if not RoleManager.is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Доступ запрещен!")
        return

    if message.document and message.document.file_name.endswith('.zip'):
        bot.send_message(message.chat.id, "📥 Получен файл, восстанавливаю данные...")

        # Скачиваем файл
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Сохраняем временно
        temp_path = os.path.join(DATA_DIR, 'temp_import.zip')
        with open(temp_path, 'wb') as f:
            f.write(downloaded_file)

        # Восстанавливаем
        if BackupManager.restore_from_backup(temp_path):
            bot.send_message(message.chat.id, "✅ Данные успешно восстановлены из бэкапа!")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при восстановлении данных!")

        # Удаляем временный файл
        try:
            os.remove(temp_path)
        except:
            pass
    else:
        bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте ZIP файл с бэкапом!")

# Обработчики управления пользователями
def process_user_search(message):
    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        bot.send_message(message.chat.id, "❌ Поиск отменен")
        admin_panel(message)
        return

    search_term = message.text.strip()

    # Поиск по ID
    if search_term.isdigit():
        user_data = UserManager.get_user_by_id(search_term)
        if user_data:
            show_user_info(message, search_term, user_data)
            return

    # Поиск по username
    if search_term.startswith('@'):
        username = search_term[1:]
    else:
        username = search_term

    user_id, user_data = UserManager.get_user_by_username(username)
    if user_data:
        show_user_info(message, user_id, user_data)
    else:
        bot.send_message(message.chat.id, "❌ Пользователь не найден!")

def show_user_info(message, user_id, user_data):
    # Проверка ролей
    is_admin = RoleManager.is_admin(user_id)
    is_creator = RoleManager.can_create_cards(user_id) and not is_admin

    roles_text = []
    if is_admin:
        roles_text.append("👑 Админ")
    if is_creator:
        roles_text.append("🎨 Создатель карт")

    roles = ", ".join(roles_text) if roles_text else "👤 Обычный пользователь"

    # Получаем время последнего выпадения
    last_drop_info = "Никогда"
    if user_data.get('last_drop'):
        try:
            last_drop = datetime.fromisoformat(user_data['last_drop'])
            last_drop_info = last_drop.strftime("%Y-%m-%d %H:%M")
        except:
            pass

    text = (
        f"👤 Информация о пользователе:\n\n"
        f"🆔 ID: {user_id}\n"
        f"📝 Имя: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📧 Username: @{user_data.get('username', 'Нет')}\n"
        f"💰 Баланс: {user_data.get('balance', 0)} zhm\n"
        f"🎴 Карт: {len(user_data.get('cards', []))}\n"
        f"⏳ Последнее выпадение: {last_drop_info}\n"
        f"📅 Зарегистрирован: {user_data.get('registered_at', 'Неизвестно')[:10]}\n"
        f"⚡️ Роли: {roles}\n"
    )

    bot.send_message(message.chat.id, text)

def process_add_coins(message):
    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        bot.send_message(message.chat.id, "❌ Операция отменена")
        admin_panel(message)
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Неверный формат! Используйте: @username 100 или ID 100")
        return

    user_input = parts[0]
    try:
        amount = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Сумма должна быть числом!")
        return

    # Поиск пользователя
    if user_input.isdigit():
        user_id = user_input
        user_data = UserManager.get_user_by_id(user_id)
    else:
        if user_input.startswith('@'):
            username = user_input[1:]
        else:
            username = user_input
        user_id, user_data = UserManager.get_user_by_username(username)

    if not user_data:
        bot.send_message(message.chat.id, "❌ Пользователь не найден!")
        return

    # Начисление монет
    UserManager.update_balance(int(user_id), amount)
    new_balance = user_data['balance'] + amount
    bot.send_message(message.chat.id, f"✅ Пользователю {user_input} начислено {amount} zhm!\nНовый баланс: {new_balance} zhm")

    # Уведомление пользователя
    try:
        bot.send_message(int(user_id), f"💰 Вам начислено {amount} zhm администратором!")
    except:
        pass

def process_add_coins_to_all(message):
    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        bot.send_message(message.chat.id, "❌ Операция отменена")
        admin_panel(message)
        return

    try:
        amount = int(message.text)
        count = UserManager.add_coins_to_all_users(amount)
        bot.send_message(message.chat.id, f"✅ Всем {count} пользователям начислено по {amount} zhm!")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Сумма должна быть числом!")

# Обработчик продажи
def process_sell_price(message, card_id):
    if message.text == '/cancel' or (message.reply_markup and 'Отмена' in str(message.reply_markup)):
        bot.send_message(message.chat.id, "❌ Продажа отменена")
        market_command(message)
        return

    try:
        price = int(message.text)
        if price <= 0:
            bot.send_message(message.chat.id, "❌ Цена должна быть положительной!")
            return

        # Проверка, что карта принадлежит пользователю
        user_id = message.from_user.id
        user = UserManager.get_user(user_id)

        if card_id not in user['cards']:
            bot.send_message(message.chat.id, "❌ У вас нет такой карты!")
            return

        # Добавление в маркетплейс
        listing_id = MarketManager.add_listing(user_id, card_id, price)

        # Удаление карты у пользователя (она теперь на продаже)
        CardManager.remove_card_from_user(user_id, card_id)

        bot.send_message(message.chat.id, f"✅ Карта выставлена на продажу за {price} zhm! ID объявления: {listing_id}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")

# Запуск бота
if __name__ == '__main__':
    logger.info("Бот запущен...")
    print("\n" + "="*50)
    print("ЗАПУСК БОТА")
    print("="*50)

    # Запуск консольного управления админами
    console_manager = ConsoleAdminManager()

    # Добавление главного админа при первом запуске
    roles = RoleManager.get_roles()
    if MAIN_ADMIN not in roles['admins'] and MAIN_ADMIN != 'zhorik200':
        # Ищем ID пользователя по username
        user_id, _ = UserManager.get_user_by_username(MAIN_ADMIN)
        if user_id:
            roles['admins'].append(user_id)
            RoleManager.save_roles(roles)
            logger.info(f"Главный админ {MAIN_ADMIN} (ID: {user_id}) добавлен")
            print(f"✅ Главный админ @{MAIN_ADMIN} добавлен")

    print("\n" + "="*50)
    print("Бот успешно запущен!")
    print(f"⏳ Задержка между выпадениями: 5 минут")
    print("\n📊 Шансы выпадения карт:")
    for rarity, chance in sorted(RARITIES.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {rarity}: {chance}%")
    print("\nИспользуйте консольные команды для управления админами")
    print("Нажмите Ctrl+C для остановки")
    print("="*50 + "\n")

    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
        print("\nБот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        print(f"\n❌ Ошибка: {e}")
