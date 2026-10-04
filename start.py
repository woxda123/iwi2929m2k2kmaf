from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from database import db
from keyboards import start_kb, back_main_kb, roles_kb, role_back_kb
from roles import Role, ROLE_EMOJI, ROLE_DESCRIPTIONS, TEAM_TITLES, role_team, role_name
from texts import t
from utils import safe_edit

router = Router()


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    user = message.from_user
    await db.ensure_user(user.id, user.username or user.full_name)
    me = await message.bot.me()
    await message.answer(t("start_private"), reply_markup=start_kb(me.username))


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(t("help"), reply_markup=back_main_kb() if message.chat.type == "private" else None)


@router.message(Command("roles"))
async def cmd_roles(message: Message):
    await message.answer(t("roles_menu"), reply_markup=roles_kb())


@router.callback_query(F.data == "menu_main")
async def cb_main(callback: CallbackQuery):
    me = await callback.bot.me()
    await safe_edit(callback.message, t("start_private"), start_kb(me.username))
    await callback.answer()


@router.callback_query(F.data == "menu_help")
async def cb_help(callback: CallbackQuery):
    await safe_edit(callback.message, t("help"), back_main_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_roles")
async def cb_roles(callback: CallbackQuery):
    await safe_edit(callback.message, t("roles_menu"), roles_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("role_"))
async def cb_role_info(callback: CallbackQuery):
    try:
        role = Role[callback.data[len("role_"):]]
    except KeyError:
        await callback.answer()
        return
    await safe_edit(
        callback.message,
        t("role_card", emoji=ROLE_EMOJI[role], name=role_name(role),
          team=TEAM_TITLES[role_team(role)], desc=ROLE_DESCRIPTIONS[role]),
        role_back_kb(),
    )
    await callback.answer()
