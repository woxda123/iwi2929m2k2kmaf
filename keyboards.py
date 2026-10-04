from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as Btn

import config
from roles import Role, ROLE_EMOJI, role_name


def _short(name: str, limit: int = 18) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _rows(buttons: list, per_row: int = 2) -> list:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


# ---------- Главное меню ----------

def start_kb(bot_username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ Добавить в группу",
             url=f"https://t.me/{bot_username}?startgroup=true&admin=delete_messages+pin_messages")],
        [Btn(text="📖 Правила", callback_data="menu_help"),
         Btn(text="🎭 Роли", callback_data="menu_roles")],
        [Btn(text="👤 Профиль", callback_data="menu_profile"),
         Btn(text="🛒 Магазин", callback_data="shop")],
        [Btn(text="🏆 Топ игроков", callback_data="top")],
    ])


def back_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="⬅️ Назад", callback_data="menu_main")]
    ])


def roles_kb():
    buttons = [
        Btn(text=f"{ROLE_EMOJI[r]} {role_name(r)}", callback_data=f"role_{r.name}")
        for r in Role
    ]
    rows = _rows(buttons, 2)
    rows.append([Btn(text="⬅️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="⬅️ К списку ролей", callback_data="menu_roles")]
    ])


# ---------- Регистрация ----------

def join_game_kb(bot_username: str = "", chat_id: int = 0):
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ Присоединиться",
             url=f"https://t.me/{bot_username}?start=join_{chat_id}")],
        [Btn(text="▶️ Начать сейчас", callback_data="start_now"),
         Btn(text="⏱ +30 сек", callback_data="extend")],
        [Btn(text="🚪 Выйти", callback_data="leave_reg")],
    ])


def open_bot_kb(bot_username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🤖 Открыть бота", url=f"https://t.me/{bot_username}")]
    ])


def again_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🎮 Играть снова", callback_data="again")]
    ])


# ---------- Ночь ----------

def night_action_kb(players: list, action_type: str, emoji: str = "🎯", back: bool = False):
    buttons = [
        Btn(text=f"{emoji} {_short(name)}", callback_data=f"night_{action_type}_{pid}")
        for pid, name in players
    ]
    rows = _rows(buttons, 2)
    if back:
        rows.append([Btn(text="⬅️ Назад", callback_data="kmode_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def komissar_mode_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🔍 Проверить", callback_data="kmode_check"),
         Btn(text="🔫 Выстрелить", callback_data="kmode_shoot")],
    ])


def kami_kb(players: list):
    buttons = [
        Btn(text=f"💥 {_short(name)}", callback_data=f"kami_{pid}")
        for pid, name in players
    ]
    return InlineKeyboardMarkup(inline_keyboard=_rows(buttons, 2))


# ---------- День ----------

def vote_kb(players: list, counts=None, skip_count: int = 0):
    counts = counts or {}
    buttons = []
    for pid, name in players:
        n = counts.get(pid, 0)
        label = f"👤 {_short(name, 14)}" + (f" • {n}" if n else "")
        buttons.append(Btn(text=label, callback_data=f"vote_{pid}"))
    rows = _rows(buttons, 2)
    skip_label = "⏭ Пропустить" + (f" • {skip_count}" if skip_count else "")
    rows.append([Btn(text=skip_label, callback_data="vote_skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Профиль и магазин ----------

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🛒 Магазин", callback_data="shop"),
         Btn(text="🏆 Статистика", callback_data="stats")],
        [Btn(text="🥇 Топ-10", callback_data="top")],
    ])


def shop_kb():
    rows = []
    for key, item in config.SHOP_ITEMS.items():
        rows.append([Btn(
            text=f"{item['emoji']} {item['name']} — {item['price']} 💰",
            callback_data=f"buy_{key}",
        )])
    rows.append([Btn(text=f"💎 → 💰 Обменять гем (+{config.GEM_RATE})", callback_data="buy_gem")])
    rows.append([Btn(text="⬅️ В профиль", callback_data="menu_profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="⬅️ В профиль", callback_data="menu_profile")]
    ])
