from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from game_logic import find_game_by_user
from keyboards import night_action_kb, komissar_mode_kb
from roles import Role, MAFIA_TEAM
from texts import t
from utils import esc, safe_send, safe_edit

router = Router()

# какое действие какой ролью доступно
ACTION_ROLES = {
    "kill": (Role.DON, Role.MAFIA, Role.MANYAK),
    "heal": (Role.DOKTOR,),
    "check": (Role.KOMISSAR,),
    "shoot": (Role.KOMISSAR,),
    "block": (Role.LYUBOVNITSA,),
    "protect": (Role.ADVOKAT,),
    "watch": (Role.BOMZH,),
}

ACCEPT_TEXT = {
    "kill": "accepted_kill",
    "heal": "accepted_heal",
    "check": "accepted_check",
    "shoot": "accepted_shoot",
    "block": "accepted_block",
    "protect": "accepted_protect",
    "watch": "accepted_watch",
}


def _night_guard(game, uid):
    """Возвращает текст ошибки или None, если действовать можно."""
    if not game or game.state != "night":
        return t("err_not_night")
    if not game.is_alive(uid):
        return t("err_dead")
    if uid not in game.pending:
        return t("err_already_acted")
    return None


@router.callback_query(F.data.startswith("kmode_"))
async def cb_komissar_mode(callback: CallbackQuery):
    uid = callback.from_user.id
    game = find_game_by_user(uid)
    error = _night_guard(game, uid)
    if error:
        await callback.answer(error, show_alert=True)
        return
    if game.get_role(uid) != Role.KOMISSAR:
        await callback.answer(t("err_not_your_role"), show_alert=True)
        return

    mode = callback.data[len("kmode_"):]
    if mode == "back":
        await safe_edit(callback.message, t("prompt_check_mode", n=game.round_num),
                        komissar_mode_kb())
    elif mode in ("check", "shoot"):
        targets = [(u, n) for u, n in game.alive_players() if u != uid]
        emoji = "🔍" if mode == "check" else "🔫"
        await safe_edit(callback.message, t(f"prompt_{mode}"),
                        night_action_kb(targets, mode, emoji, back=True))
    await callback.answer()


@router.callback_query(F.data.startswith("night_"))
async def cb_night_action(callback: CallbackQuery):
    uid = callback.from_user.id
    game = find_game_by_user(uid)
    error = _night_guard(game, uid)
    if error:
        await callback.answer(error, show_alert=True)
        return

    try:
        _, action, raw_target = callback.data.split("_", 2)
        target = int(raw_target)
    except ValueError:
        await callback.answer()
        return

    role = game.get_role(uid)
    if action not in ACTION_ROLES or role not in ACTION_ROLES[action]:
        await callback.answer(t("err_not_your_role"), show_alert=True)
        return
    if not game.is_alive(target):
        await callback.answer(t("err_bad_target"), show_alert=True)
        return

    # Ограничения по целям
    if action == "kill" and role in (Role.DON, Role.MAFIA) and game.get_role(target) in MAFIA_TEAM:
        await callback.answer(t("err_bad_target"), show_alert=True)
        return
    if action in ("kill", "check", "shoot", "block", "watch") and target == uid and role != Role.DOKTOR:
        await callback.answer(t("err_bad_target"), show_alert=True)
        return
    if action == "heal" and target == uid:
        if game.players[uid]["heal_self_used"]:
            await callback.answer(t("err_self_heal"), show_alert=True)
            return
        game.players[uid]["heal_self_used"] = True

    game.night_actions[uid] = {"type": action, "target": target}
    game.pending.discard(uid)

    target_name = game.name_of(target)
    await safe_edit(callback.message, t(ACCEPT_TEXT[action], target=esc(target_name)))
    await callback.answer("✅")

    # Мафия видит выбор друг друга
    if action == "kill" and role in (Role.DON, Role.MAFIA):
        note = t("mafia_vote_note", name=esc(game.name_of(uid)), target=esc(target_name))
        for mate in game.mafia_team_alive():
            if mate != uid:
                await safe_send(callback.bot, mate, note)

    if not game.pending:
        game.night_event.set()


@router.callback_query(F.data.startswith("kami_"))
async def cb_kamikaze(callback: CallbackQuery):
    uid = callback.from_user.id
    game = find_game_by_user(uid)
    if not game or game.kami_uid != uid:
        await callback.answer(t("err_kami"), show_alert=True)
        return
    try:
        target = int(callback.data[len("kami_"):])
    except ValueError:
        await callback.answer()
        return
    if target not in game.kami_pool:
        await callback.answer(t("err_bad_target"), show_alert=True)
        return
    game.kami_choice = target
    game.kami_event.set()
    await safe_edit(callback.message, f"💥 Ты забираешь с собой: <b>{esc(game.name_of(target))}</b>")
    await callback.answer("💥")


def _private_text(message: Message) -> bool:
    return bool(message.text) and not message.text.startswith("/")


@router.message(F.chat.type == "private", _private_text)
async def mafia_relay(message: Message):
    """Ночью сообщения мафии из личного чата пересылаются остальным членам команды."""
    uid = message.from_user.id
    game = find_game_by_user(uid)
    if not game or game.state != "night" or not game.is_alive(uid):
        return
    if game.get_role(uid) not in MAFIA_TEAM:
        return
    text = t("mafia_relay", name=esc(game.name_of(uid)), text=esc(message.text))
    for mate in game.mafia_team_alive():
        if mate != uid:
            await safe_send(message.bot, mate, text)
