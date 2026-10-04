from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

import config
from database import db
from keyboards import profile_kb, shop_kb, back_profile_kb
from texts import t
from utils import esc, safe_edit

router = Router()

RANKS = [
    (100, "👑 Легенда"),
    (50, "💎 Мастер"),
    (20, "🥇 Профи"),
    (5, "🥈 Игрок"),
    (0, "🥉 Новичок"),
]


def rank_of(wins: int) -> str:
    for need, title in RANKS:
        if wins >= need:
            return title
    return RANKS[-1][1]


def next_rank_line(wins: int) -> str:
    for need, title in reversed(RANKS):
        if wins < need:
            return f"\n🎯 До звания {title}: ещё <b>{need - wins}</b> побед"
    return "\n🌟 У тебя максимальное звание!"


def winrate(row) -> int:
    return round(row["wins"] * 100 / row["games_played"]) if row["games_played"] else 0


async def load_user(user):
    return await db.ensure_user(user.id, user.username or user.full_name)


def profile_text(user, row) -> str:
    return t(
        "profile_text", name=esc(user.full_name), rank=rank_of(row["wins"]),
        money=row["money"], gems=row["gems"], games=row["games_played"],
        wins=row["wins"], winrate=winrate(row),
        shield=row["shield"], fake=row["fake_id"], active=row["active_role"],
    )


def shop_text(row) -> str:
    items = "\n\n".join(
        t("shop_item", emoji=i["emoji"], name=i["name"], price=i["price"],
          desc=i["desc"], owned=row[i["column"]])
        for i in config.SHOP_ITEMS.values()
    )
    return t("shop_text", money=row["money"], gems=row["gems"], items=items, rate=config.GEM_RATE)


# ---------- профиль ----------

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    row = await load_user(message.from_user)
    await message.answer(profile_text(message.from_user, row), reply_markup=profile_kb())


@router.callback_query(F.data == "menu_profile")
async def cb_profile(callback: CallbackQuery):
    row = await load_user(callback.from_user)
    await safe_edit(callback.message, profile_text(callback.from_user, row), profile_kb())
    await callback.answer()


# ---------- статистика ----------

@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    row = await load_user(callback.from_user)
    text = t(
        "stats_text", games=row["games_played"], wins=row["wins"],
        losses=row["games_played"] - row["wins"], winrate=winrate(row),
        progress=next_rank_line(row["wins"]),
    )
    await safe_edit(callback.message, text, back_profile_kb())
    await callback.answer()


# ---------- магазин ----------

@router.message(Command("shop"))
async def cmd_shop(message: Message):
    row = await load_user(message.from_user)
    await message.answer(shop_text(row), reply_markup=shop_kb())


@router.callback_query(F.data == "shop")
async def cb_shop(callback: CallbackQuery):
    row = await load_user(callback.from_user)
    await safe_edit(callback.message, shop_text(row), shop_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: CallbackQuery):
    await load_user(callback.from_user)
    key = callback.data[len("buy_"):]

    if key == "gem":
        ok = await db.exchange_gem(callback.from_user.id, config.GEM_RATE)
        toast = t("shop_gem_ok", rate=config.GEM_RATE) if ok else t("shop_gem_fail")
    elif key in config.SHOP_ITEMS:
        item = config.SHOP_ITEMS[key]
        ok = await db.buy_item(callback.from_user.id, item["column"], item["price"])
        toast = (t("shop_bought", item=f"{item['emoji']} {item['name']}")
                 if ok else t("shop_no_money"))
    else:
        await callback.answer()
        return

    await callback.answer(toast, show_alert=not ok)
    row = await db.get_user(callback.from_user.id)
    await safe_edit(callback.message, shop_text(row), shop_kb())


# ---------- рейтинг ----------

MEDALS = ["🥇", "🥈", "🥉"]


async def top_text() -> str:
    rows = await db.get_top(10)
    if not rows:
        return t("top_empty")
    lines = [
        t("top_line", medal=MEDALS[i] if i < 3 else f"{i + 1}.",
          name=esc(r["username"] or "Игрок"), wins=r["wins"], games=r["games_played"])
        for i, r in enumerate(rows)
    ]
    return t("top_text", lines="\n".join(lines))


@router.message(Command("top"))
async def cmd_top(message: Message):
    await message.answer(await top_text())


@router.callback_query(F.data == "top")
async def cb_top(callback: CallbackQuery):
    await safe_edit(callback.message, await top_text(), back_profile_kb())
    await callback.answer()
