import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TOKEN_HERE")
DB_PATH = os.getenv("DB_PATH", "wox_mafia.db")
GAME_TIMEOUT = 120  # секунд на регистрацию
NIGHT_TIMEOUT = 60
DAY_DISCUSSION_TIMEOUT = 120
VOTE_TIMEOUT = 60

# --- Дополнительные настройки ---
MIN_PLAYERS = 4
MAX_PLAYERS = 20
REG_EXTEND_SECONDS = 30
REG_MAX_SECONDS = 300
KAMIKAZE_TIMEOUT = 20

# Награды за игру
REWARD_WIN = 50
REWARD_LOSE = 15
GEM_MIN_PLAYERS = 8  # гем за победу, если в игре >= N игроков

# Обмен гема на монеты
GEM_RATE = 150

# Магазин: ключ -> параметры (column — колонка в таблице users)
SHOP_ITEMS = {
    "shield": {
        "emoji": "🛡",
        "name": "Защита",
        "price": 100,
        "column": "shield",
        "desc": "Спасает от одного ночного убийства в следующей игре",
    },
    "fake": {
        "emoji": "🎭",
        "name": "Фейк ID",
        "price": 200,
        "column": "fake_id",
        "desc": "Если ты мафия — комиссар один раз увидит тебя мирным",
    },
    "active": {
        "emoji": "⚡",
        "name": "Активная роль",
        "price": 500,
        "column": "active_role",
        "desc": "Если выпадет мирный житель — получишь активную роль",
    },
}
