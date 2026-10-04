import asyncio
import logging
import random
import time
from collections import Counter

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

import config
from database import db
from game_logic import Game, GAMES, USER_GAMES, find_game_by_user, drop_game
from keyboards import (
    join_game_kb, open_bot_kb, night_action_kb, komissar_mode_kb,
    vote_kb, kami_kb, again_kb, start_kb,
)
from roles import (
    Role, ROLE_EMOJI, ROLE_DESCRIPTIONS, MAFIA_TEAM, role_name, role_title,
)
from texts import t
from utils import esc, mention, safe_send, safe_edit

router = Router()

GROUP = F.chat.type.in_({"group", "supergroup"})


# =====================================================================
#  Вспомогательное
# =====================================================================

async def is_host_or_admin(bot: Bot, game: Game, user_id: int) -> bool:
    if user_id == game.creator_id:
        return True
    try:
        member = await bot.get_chat_member(game.chat_id, user_id)
        return member.status in ("administrator", "creator")
    except (TelegramBadRequest, TelegramForbiddenError):
        return False


async def finalize_drop(game: Game):
    drop_game(game)
    await db.delete_game(game.chat_id)


async def save(game: Game):
    try:
        await db.save_game(game.chat_id, **game.snapshot())
    except Exception:
        logging.exception("Не удалось сохранить игру")


def reg_text(game: Game) -> str:
    remaining = max(0, int(game.reg_deadline - time.monotonic()))
    players = "\n".join(
        t("reg_player_line", mention=mention(uid, p["name"]))
        for uid, p in game.players.items()
    ) or t("reg_none")
    return t(
        "reg_text", host=esc(game.creator_name), count=len(game.players),
        max=config.MAX_PLAYERS, players=players, seconds=remaining, min=config.MIN_PLAYERS,
    )


async def refresh_registration(bot: Bot, game: Game):
    if not game.reg_message_id:
        return
    me = await bot.me()
    try:
        await bot.edit_message_text(
            reg_text(game), chat_id=game.chat_id, message_id=game.reg_message_id,
            reply_markup=join_game_kb(me.username, game.chat_id),
        )
    except TelegramBadRequest:
        pass


def roles_summary(game: Game) -> str:
    counts = Counter(p["role"] for p in game.players.values())
    return "\n".join(
        f"{ROLE_EMOJI[r]} {role_name(r)} × {counts[r]}" for r in Role if counts.get(r)
    )


# =====================================================================
#  Регистрация
# =====================================================================

async def open_registration(bot: Bot, chat, user):
    if chat.type == "private":
        me = await bot.me()
        await safe_send(bot, chat.id, t("game_private_only"), reply_markup=start_kb(me.username))
        return
    if chat.id in GAMES:
        await safe_send(bot, chat.id, t("game_exists"))
        return

    game = Game(chat.id, user.id, chat.title or "", user.full_name)
    game.reg_deadline = time.monotonic() + config.GAME_TIMEOUT
    GAMES[chat.id] = game

    # Ведущий сразу в игре, если писал боту в личку
    await db.ensure_user(user.id, user.username or user.full_name)
    if user.id not in USER_GAMES:
        ok = await safe_send(bot, user.id, t("join_ok_private", chat=esc(game.chat_title)))
        if ok:
            game.add_player(user.id, user.full_name)

    me = await bot.me()
    msg = await bot.send_message(
        chat.id, reg_text(game), reply_markup=join_game_kb(me.username, chat.id)
    )
    game.reg_message_id = msg.message_id
    game.task = asyncio.create_task(game_lifecycle(bot, game))


async def try_join(bot: Bot, user, chat_id: int) -> str:
    game = GAMES.get(chat_id)
    if not game or game.state != "registration":
        return t("join_closed")
    if user.id in game.players:
        return t("join_already")
    if user.id in USER_GAMES:
        return t("join_busy")
    if len(game.players) >= config.MAX_PLAYERS:
        return t("join_full", max=config.MAX_PLAYERS)
    await db.ensure_user(user.id, user.username or user.full_name)
    game.add_player(user.id, user.full_name)
    await refresh_registration(bot, game)
    return t("join_ok_private", chat=esc(game.chat_title))


@router.message(Command("game"))
async def cmd_game(message: Message):
    await open_registration(message.bot, message.chat, message.from_user)


@router.callback_query(F.data == "again")
async def cb_again(callback: CallbackQuery):
    await callback.answer()
    await open_registration(callback.bot, callback.message.chat, callback.from_user)


@router.message(CommandStart(deep_link=True, magic=F.args.regexp(r"^join_-?\d+$")),
                F.chat.type == "private")
async def deep_link_join(message: Message, command: CommandObject):
    chat_id = int(command.args[len("join_"):])
    await message.answer(await try_join(message.bot, message.from_user, chat_id))


@router.callback_query(F.data == "start_now")
async def cb_start_now(callback: CallbackQuery):
    game = GAMES.get(callback.message.chat.id)
    if not game or game.state != "registration":
        await callback.answer(t("join_closed"), show_alert=True)
        return
    if not await is_host_or_admin(callback.bot, game, callback.from_user.id):
        await callback.answer(t("only_host"), show_alert=True)
        return
    if len(game.players) < config.MIN_PLAYERS:
        await callback.answer(
            t("need_min", min=config.MIN_PLAYERS, count=len(game.players)), show_alert=True)
        return
    game.reg_deadline = time.monotonic()
    game.reg_wakeup.set()
    await callback.answer(t("reg_started"))


@router.message(Command("start"), GROUP)
async def cmd_start_group(message: Message):
    game = GAMES.get(message.chat.id)
    if not game or game.state != "registration":
        return
    if not await is_host_or_admin(message.bot, game, message.from_user.id):
        await message.answer(t("only_host"))
        return
    if len(game.players) < config.MIN_PLAYERS:
        await message.answer(t("need_min", min=config.MIN_PLAYERS, count=len(game.players)))
        return
    game.reg_deadline = time.monotonic()
    game.reg_wakeup.set()


@router.callback_query(F.data == "extend")
async def cb_extend(callback: CallbackQuery):
    game = GAMES.get(callback.message.chat.id)
    if not game or game.state != "registration":
        await callback.answer(t("join_closed"), show_alert=True)
        return
    if game.reg_deadline - time.monotonic() + config.REG_EXTEND_SECONDS > config.REG_MAX_SECONDS:
        await callback.answer(t("reg_extend_max"), show_alert=True)
        return
    game.reg_deadline += config.REG_EXTEND_SECONDS
    game.warned = False
    await callback.answer(t("reg_extended"))
    await refresh_registration(callback.bot, game)


@router.callback_query(F.data == "leave_reg")
async def cb_leave_reg(callback: CallbackQuery):
    game = GAMES.get(callback.message.chat.id)
    if not game or game.state != "registration":
        await callback.answer(t("join_closed"), show_alert=True)
        return
    if callback.from_user.id not in game.players:
        await callback.answer(t("not_in_game"), show_alert=True)
        return
    game.remove_player(callback.from_user.id)
    await callback.answer(t("reg_leave_ok"))
    await refresh_registration(callback.bot, game)


# =====================================================================
#  Жизненный цикл игры
# =====================================================================

async def game_lifecycle(bot: Bot, game: Game):
    try:
        if not await registration_phase(bot, game):
            return
        await run_game(bot, game)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.exception("Игра в чате %s упала", game.chat_id)
        await safe_send(bot, game.chat_id, t("game_error"))
        await finalize_drop(game)


async def registration_phase(bot: Bot, game: Game) -> bool:
    last_refresh = time.monotonic()
    while True:
        remaining = game.reg_deadline - time.monotonic()
        if remaining <= 0:
            break
        if remaining <= 30 and not game.warned:
            game.warned = True
            await safe_send(bot, game.chat_id, t("reg_warning"))
        if time.monotonic() - last_refresh >= 20:
            last_refresh = time.monotonic()
            await refresh_registration(bot, game)
        game.reg_wakeup.clear()
        try:
            await asyncio.wait_for(game.reg_wakeup.wait(), timeout=min(remaining, 3))
        except asyncio.TimeoutError:
            pass

    if len(game.players) < config.MIN_PLAYERS:
        await safe_send(bot, game.chat_id, t("reg_cancelled_min", min=config.MIN_PLAYERS))
        await finalize_drop(game)
        return False
    return True


async def run_game(bot: Bot, game: Game):
    await start_game(bot, game)
    while True:
        game.round_num += 1
        res = await night_phase(bot, game)
        await day_report(bot, game, res)
        if await finish_if_won(bot, game):
            return
        await asyncio.sleep(config.DAY_DISCUSSION_TIMEOUT)
        outcome = await voting_phase(bot, game)
        if await finish_if_won(bot, game, outcome):
            return


async def finish_if_won(bot: Bot, game: Game, forced=None) -> bool:
    winner = forced or game.check_win()
    if not winner:
        return False
    await end_game(bot, game, winner)
    return True


# ---------- старт ----------

async def start_game(bot: Bot, game: Game):
    game.state = "starting"

    # Предметы из магазина
    want_active = []
    for uid in game.players:
        row = await db.get_user(uid)
        if row and row["active_role"] > 0:
            want_active.append(uid)
    granted = set(game.assign_roles(want_active))
    for uid in granted:
        await db.consume_item(uid, "active_role")
    for uid, p in game.players.items():
        if await db.consume_item(uid, "shield"):
            p["shield"] = True
        if await db.consume_item(uid, "fake_id"):
            p["fake"] = True

    failed = []
    for uid, p in game.players.items():
        role = p["role"]
        extra = ""
        if role in MAFIA_TEAM:
            mates = [
                f"{role_title(game.get_role(m))} — {esc(game.name_of(m))}"
                for m in game.players if m != uid and game.get_role(m) in MAFIA_TEAM
            ]
            if mates:
                extra += t("mafia_mates_extra", mates="\n".join(mates))
        if p["shield"]:
            extra += t("shield_active")
        if p["fake"]:
            extra += t("fake_active")
        if uid in granted:
            extra += t("active_granted")
        sent = await safe_send(bot, uid, t(
            "role_dm", emoji=ROLE_EMOJI[role], name=role_name(role),
            desc=ROLE_DESCRIPTIONS[role], extra=extra,
        ))
        if not sent:
            failed.append(esc(p["name"]))

    await bot.send_message(game.chat_id, t(
        "game_start", count=len(game.players), roles=roles_summary(game)))
    if failed:
        await safe_send(bot, game.chat_id, t("dm_failed", names=", ".join(failed)))
    await save(game)


# ---------- ночь ----------

async def send_night_prompt(bot: Bot, game: Game, uid: int, role: Role):
    n = game.round_num
    alive = game.alive_players()
    others = [(u, nm) for u, nm in alive if u != uid]

    if role in (Role.DON, Role.MAFIA):
        targets = [(u, nm) for u, nm in alive if game.get_role(u) not in MAFIA_TEAM]
        text = t("prompt_kill", n=n) + t("mafia_chat_hint")
        kb = night_action_kb(targets, "kill", "🔪")
    elif role == Role.ADVOKAT:
        text = t("prompt_protect", n=n) + t("mafia_chat_hint")
        kb = night_action_kb(alive, "protect", "⚖️")
    elif role == Role.MANYAK:
        text = t("prompt_manyak", n=n)
        kb = night_action_kb(others, "kill", "🪓")
    elif role == Role.DOKTOR:
        targets = alive if not game.players[uid]["heal_self_used"] else others
        text = t("prompt_heal", n=n)
        kb = night_action_kb(targets, "heal", "💉")
    elif role == Role.KOMISSAR:
        text = t("prompt_check_mode", n=n)
        kb = komissar_mode_kb()
    elif role == Role.LYUBOVNITSA:
        text = t("prompt_block", n=n)
        kb = night_action_kb(others, "block", "💋")
    elif role == Role.BOMZH:
        text = t("prompt_watch", n=n)
        kb = night_action_kb(others, "watch", "🧳")
    else:
        return
    await safe_send(bot, uid, text, reply_markup=kb)


async def night_phase(bot: Bot, game: Game):
    game.state = "night"
    game.night_actions = {}
    game.muted = set()
    game.night_event = asyncio.Event()

    me = await bot.me()
    await safe_send(
        bot, game.chat_id,
        t("night_start", n=game.round_num, seconds=config.NIGHT_TIMEOUT),
        reply_markup=open_bot_kb(me.username),
    )

    actors = game.night_actors()
    game.pending = {uid for uid, _ in actors}
    await save(game)
    for uid, role in actors:
        await send_night_prompt(bot, game, uid, role)
    if not game.pending:
        game.night_event.set()

    try:
        await asyncio.wait_for(game.night_event.wait(), config.NIGHT_TIMEOUT)
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(2)

    game.state = "resolving"
    res = game.resolve_night()
    for uid, text in res.private:
        await safe_send(bot, uid, text)
    return res


async def day_report(bot: Bot, game: Game, res):
    game.state = "day"
    if res.dead:
        report = "\n".join(
            t("night_dead", mention=mention(uid, game.name_of(uid)),
              emoji=ROLE_EMOJI[game.get_role(uid)], role=role_name(game.get_role(uid)))
            for uid, _ in res.dead
        )
    else:
        report = t("night_nobody")
    alive = game.alive_players()
    await bot.send_message(game.chat_id, t(
        "day_start", n=game.round_num, report=report, count=len(alive),
        alive="\n".join(t("alive_line", mention=mention(u, nm)) for u, nm in alive),
        seconds=config.DAY_DISCUSSION_TIMEOUT,
    ))
    await save(game)


# ---------- голосование ----------

def vote_tally_text(game: Game) -> str:
    counts, skip = game.vote_counts()
    lines = [
        t("vote_line", name=esc(game.name_of(uid)), n=n)
        for uid, n in counts.most_common()
    ]
    if skip:
        lines.append(t("vote_line", name="⏭ Пропустить", n=skip))
    body = "\n".join(lines) or t("vote_none")
    done = len([v for v in game.day_votes if game.is_alive(v)])
    return body + "\n\n" + t("vote_progress", done=done, total=len(game.alive_players()))


async def voting_phase(bot: Bot, game: Game):
    game.state = "voting"
    game.day_votes = {}
    game.vote_event = asyncio.Event()

    alive = game.alive_players()
    msg = await bot.send_message(
        game.chat_id,
        t("vote_start", seconds=config.VOTE_TIMEOUT, tally=vote_tally_text(game)),
        reply_markup=vote_kb(alive),
    )
    game.vote_message_id = msg.message_id
    await save(game)

    try:
        await asyncio.wait_for(game.vote_event.wait(), config.VOTE_TIMEOUT)
    except asyncio.TimeoutError:
        pass

    game.state = "resolving"
    lynched, counts, skip = game.tally_votes()

    try:
        await bot.edit_message_text(
            t("vote_closed", tally=vote_tally_text(game)),
            chat_id=game.chat_id, message_id=msg.message_id, reply_markup=None,
        )
    except TelegramBadRequest:
        pass

    if lynched is None:
        await safe_send(bot, game.chat_id, t("no_lynch"))
        return None

    role = game.get_role(lynched)
    game.kill(lynched)
    await safe_send(bot, game.chat_id, t(
        "lynch", mention=mention(lynched, game.name_of(lynched)),
        emoji=ROLE_EMOJI[role], role=role_name(role)))

    outcome = None
    if role == Role.SAMOUBIYTSA:
        outcome = "suicide"
    elif role == Role.KAMIKADZE:
        await kamikaze_flow(bot, game, lynched)

    if not outcome:
        for uid, text in game.promote():
            await safe_send(bot, uid, text)
    return outcome


async def kamikaze_flow(bot: Bot, game: Game, kami_uid: int):
    voters = [v for v, tg in game.day_votes.items() if tg == kami_uid and game.is_alive(v)]
    pool = voters or [u for u, _ in game.alive_players()]
    if not pool:
        return

    game.kami_uid = kami_uid
    game.kami_pool = set(pool)
    game.kami_choice = None
    game.kami_event = asyncio.Event()

    sent = await safe_send(
        bot, kami_uid, t("kamikaze_prompt", seconds=config.KAMIKAZE_TIMEOUT),
        reply_markup=kami_kb([(u, game.name_of(u)) for u in pool]),
    )
    if sent:
        try:
            await asyncio.wait_for(game.kami_event.wait(), config.KAMIKAZE_TIMEOUT)
        except asyncio.TimeoutError:
            pass

    victim = game.kami_choice if game.kami_choice in pool else random.choice(pool)
    game.kami_uid = None
    game.kill(victim)
    role = game.get_role(victim)
    await safe_send(bot, game.chat_id, t(
        "kamikaze_take", kami=mention(kami_uid, game.name_of(kami_uid)),
        victim=mention(victim, game.name_of(victim)),
        emoji=ROLE_EMOJI[role], role=role_name(role)))


@router.callback_query(F.data.startswith("vote_"))
async def cb_vote(callback: CallbackQuery):
    game = GAMES.get(callback.message.chat.id)
    if not game or game.state != "voting":
        await callback.answer(t("err_not_voting"), show_alert=True)
        return
    voter = callback.from_user.id
    if not game.is_alive(voter):
        await callback.answer(t("err_dead_vote"), show_alert=True)
        return

    data = callback.data[len("vote_"):]
    if data == "skip":
        target = None
        toast = t("vote_skip_accepted")
    else:
        try:
            target = int(data)
        except ValueError:
            await callback.answer()
            return
        if not game.is_alive(target):
            await callback.answer(t("err_bad_target"), show_alert=True)
            return
        if target == voter:
            await callback.answer(t("err_self_vote"), show_alert=True)
            return
        toast = t("vote_accepted", target=game.name_of(target))

    game.day_votes[voter] = target
    await callback.answer(toast)

    counts, skip = game.vote_counts()
    await safe_edit(
        callback.message,
        t("vote_start", seconds=config.VOTE_TIMEOUT, tally=vote_tally_text(game)),
        vote_kb(game.alive_players(), counts, skip),
    )
    if game.all_voted():
        game.vote_event.set()


# ---------- конец игры ----------

async def end_game(bot: Bot, game: Game, winner: str):
    game.state = "ended"
    winners = set(game.winner_ids(winner))

    roles_text = "\n".join(
        t("role_line", status="✅" if p["alive"] else "💀",
          mention=mention(uid, p["name"]),
          emoji=ROLE_EMOJI[p["role"]], role=role_name(p["role"]))
        for uid, p in game.players.items()
    )
    await bot.send_message(game.chat_id, t(
        "end_game", winner=t(f"win_{winner}"), roles=roles_text, rounds=game.round_num),
        reply_markup=again_kb())

    for uid in game.players:
        is_win = uid in winners
        money = config.REWARD_WIN if is_win else config.REWARD_LOSE
        gems = 1 if is_win and len(game.players) >= config.GEM_MIN_PLAYERS else 0
        try:
            await db.update_stats(uid, money=money, gems=gems, played=1, win=1 if is_win else 0)
        except Exception:
            logging.exception("Не удалось обновить статистику %s", uid)
        if is_win:
            gem_text = t("reward_gems", gems=gems) if gems else ""
            await safe_send(bot, uid, t("reward_win", money=money, gems=gem_text))
        else:
            await safe_send(bot, uid, t("reward_lose", money=money))

    await finalize_drop(game)


# =====================================================================
#  /leave, /stop
# =====================================================================

@router.message(Command("leave"))
async def cmd_leave(message: Message):
    uid = message.from_user.id
    game = find_game_by_user(uid)
    if not game:
        await message.answer(t("not_in_game"))
        return

    if game.state == "registration":
        game.remove_player(uid)
        await refresh_registration(message.bot, game)
        await message.answer(t("reg_leave_ok"))
        return

    if not game.is_alive(uid):
        await message.answer(t("err_dead"))
        return

    role = game.get_role(uid)
    game.kill(uid)
    await safe_send(message.bot, game.chat_id, t(
        "left_game", mention=mention(uid, game.name_of(uid)),
        emoji=ROLE_EMOJI[role], role=role_name(role)))
    await message.answer(t("left_ok"))

    game.pending.discard(uid)
    if game.state == "night" and not game.pending:
        game.night_event.set()
    if game.state == "voting":
        game.day_votes.pop(uid, None)
        if game.all_voted():
            game.vote_event.set()


@router.message(Command("stop"), GROUP)
async def cmd_stop(message: Message):
    game = GAMES.get(message.chat.id)
    if not game:
        await message.answer(t("no_game"))
        return
    if not await is_host_or_admin(message.bot, game, message.from_user.id):
        await message.answer(t("only_host"))
        return
    if game.task and not game.task.done():
        game.task.cancel()
    await finalize_drop(game)
    await message.answer(t("game_stopped"))


# =====================================================================
#  Чат: ночью и для мёртвых/заблокированных — удаляем сообщения
#  (обработчик должен быть последним среди сообщений группы)
# =====================================================================

def _not_command(message: Message) -> bool:
    return not (message.text or "").startswith("/")


@router.message(GROUP, _not_command)
async def moderate_chat(message: Message):
    game = GAMES.get(message.chat.id)
    if not game or not message.from_user or message.from_user.is_bot:
        return
    if game.state in ("registration", "starting", "ended"):
        return
    uid = message.from_user.id
    player = game.players.get(uid)

    should_delete = False
    if game.state == "night":
        should_delete = True
    elif player and (not player["alive"] or uid in game.muted):
        should_delete = True

    if should_delete:
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
