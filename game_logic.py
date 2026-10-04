import asyncio
import json
import random
from collections import Counter
from dataclasses import dataclass, field

from roles import (
    Role, MAFIA_TEAM, NIGHT_ROLES, ACTIVE_TOWN_ROLES,
    get_roles_for_player_count,
)
from texts import t
from utils import esc

# chat_id -> Game
GAMES: dict = {}
# user_id -> chat_id (в какой игре сейчас участвует игрок)
USER_GAMES: dict = {}


def find_game_by_user(user_id):
    chat_id = USER_GAMES.get(user_id)
    return GAMES.get(chat_id) if chat_id is not None else None


@dataclass
class NightResult:
    dead: list = field(default_factory=list)     # [(uid, источник)]
    private: list = field(default_factory=list)  # [(uid, текст)]


class Game:
    def __init__(self, chat_id, creator_id, chat_title="", creator_name=""):
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.chat_title = chat_title
        self.creator_name = creator_name
        # user_id -> {"name", "alive", "role", "shield", "fake", "heal_self_used"}
        self.players = {}
        self.state = "registration"  # registration, starting, night, day, voting, resolving, ended
        self.round_num = 0
        self.night_actions = {}  # uid -> {"type": str, "target": int}
        self.day_votes = {}      # voter -> target | None
        self.night_results = []
        self.muted = set()       # игроки, заблокированные любовницей (чат днём)
        self.pending = set()     # кто ещё не сделал ночной ход

        self.reg_deadline = 0.0
        self.reg_message_id = None
        self.warned = False
        self.reg_wakeup = asyncio.Event()
        self.night_event = asyncio.Event()
        self.vote_event = asyncio.Event()
        self.vote_message_id = None

        self.kami_uid = None
        self.kami_pool = set()
        self.kami_choice = None
        self.kami_event = asyncio.Event()

        self.task = None

    # ---------- игроки ----------

    def add_player(self, user_id, name):
        if user_id in self.players:
            return False
        self.players[user_id] = {
            "name": name, "alive": True, "role": None,
            "shield": False, "fake": False, "heal_self_used": False,
        }
        USER_GAMES[user_id] = self.chat_id
        return True

    def remove_player(self, user_id):
        self.players.pop(user_id, None)
        if USER_GAMES.get(user_id) == self.chat_id:
            USER_GAMES.pop(user_id, None)

    def is_alive(self, user_id):
        return bool(self.players.get(user_id, {}).get("alive"))

    def alive_players(self):
        return [(uid, d["name"]) for uid, d in self.players.items() if d["alive"]]

    def get_role(self, user_id):
        return self.players.get(user_id, {}).get("role")

    def name_of(self, user_id):
        return self.players.get(user_id, {}).get("name", "?")

    def kill(self, user_id):
        if user_id in self.players:
            self.players[user_id]["alive"] = False

    def mafia_team_alive(self):
        return [uid for uid, d in self.players.items()
                if d["alive"] and d["role"] in MAFIA_TEAM]

    # ---------- роли ----------

    def assign_roles(self, want_active=()):
        """Раздаёт роли. Возвращает uid игроков, у которых сработала «Активная роль»."""
        roles = get_roles_for_player_count(len(self.players))
        random.shuffle(roles)
        for (uid, data), role in zip(self.players.items(), roles):
            data["role"] = role

        granted = []
        swappable = [uid for uid, p in self.players.items()
                     if p["role"] in ACTIVE_TOWN_ROLES and uid not in want_active]
        for uid in want_active:
            p = self.players.get(uid)
            if p and p["role"] == Role.MIRNY and swappable:
                other = swappable.pop(random.randrange(len(swappable)))
                p["role"], self.players[other]["role"] = self.players[other]["role"], Role.MIRNY
                granted.append(uid)
        return granted

    def night_actors(self):
        return [(uid, p["role"]) for uid, p in self.players.items()
                if p["alive"] and p["role"] in NIGHT_ROLES]

    def promote(self):
        """Дон -> новый Дон из мафии, Комиссар -> Сержант. Возвращает [(uid, текст)]."""
        msgs = []
        alive = [(uid, p) for uid, p in self.players.items() if p["alive"]]
        if not any(p["role"] == Role.DON for _, p in alive):
            for uid, p in alive:
                if p["role"] == Role.MAFIA:
                    p["role"] = Role.DON
                    msgs.append((uid, t("promoted_don")))
                    break
        if not any(p["role"] == Role.KOMISSAR for _, p in alive):
            for uid, p in alive:
                if p["role"] == Role.SERZHANT:
                    p["role"] = Role.KOMISSAR
                    msgs.append((uid, t("promoted_kom")))
                    break
        return msgs

    # ---------- ночь ----------

    def resolve_night(self) -> NightResult:
        res = NightResult()
        acts = self.night_actions

        # 1. Блокировки любовницы
        blocked = set()
        for uid, a in acts.items():
            if (self.get_role(uid) == Role.LYUBOVNITSA and a["type"] == "block"
                    and a.get("target") in self.players):
                blocked.add(a["target"])
        self.muted = set(blocked)
        for uid in blocked:
            res.private.append((uid, t("blocked_note")))

        # Кто к кому приходил (для бомжа)
        visits = {}
        for uid, a in acts.items():
            if uid in blocked or not a.get("target"):
                continue
            visits.setdefault(a["target"], []).append(uid)

        # 2. Выбор цели мафии: Дон = 2 голоса, при ничьей решает Дон
        votes = Counter()
        don_choice = None
        for uid, a in acts.items():
            role = self.get_role(uid)
            if uid in blocked or a["type"] != "kill" or role not in (Role.DON, Role.MAFIA):
                continue
            votes[a["target"]] += 2 if role == Role.DON else 1
            if role == Role.DON:
                don_choice = a["target"]
        attacks = []
        if votes:
            top = max(votes.values())
            cands = [x for x, c in votes.items() if c == top]
            attacks.append((don_choice if don_choice in cands else random.choice(cands), "mafia"))

        for uid, a in acts.items():
            role = self.get_role(uid)
            if uid in blocked or not a.get("target"):
                continue
            if a["type"] == "kill" and role == Role.MANYAK:
                attacks.append((a["target"], "maniac"))
            elif a["type"] == "shoot" and role == Role.KOMISSAR:
                attacks.append((a["target"], "komissar"))

        # 3. Лечение
        heal_target = None
        doctor_uid = None
        for uid, a in acts.items():
            if (self.get_role(uid) == Role.DOKTOR and a["type"] == "heal"
                    and uid not in blocked):
                heal_target, doctor_uid = a["target"], uid

        # 4. Убийства
        killed = set()
        for target, source in attacks:
            if target in killed or not self.is_alive(target):
                continue
            p = self.players[target]
            if heal_target == target:
                res.private.append((target, t("saved_by_doctor")))
                if doctor_uid:
                    res.private.append((doctor_uid, t("saved_patient", target=esc(p["name"]))))
                continue
            if p.get("shield"):
                p["shield"] = False
                res.private.append((target, t("shield_saved")))
                continue
            if p["role"] == Role.SCHASTLIVCHIK and random.random() < 0.5:
                res.private.append((target, t("lucky_saved")))
                continue
            killed.add(target)
            self.kill(target)
            res.dead.append((target, source))
            res.private.append((target, t("you_died")))

        # 5. Проверки комиссара
        protected = {a["target"] for uid, a in acts.items()
                     if self.get_role(uid) == Role.ADVOKAT and a["type"] == "protect"
                     and uid not in blocked}
        for uid, a in acts.items():
            if (self.get_role(uid) != Role.KOMISSAR or a["type"] != "check"
                    or uid in blocked or a.get("target") not in self.players):
                continue
            target = a["target"]
            p = self.players[target]
            shows_mafia = p["role"] in MAFIA_TEAM
            if shows_mafia and target in protected:
                shows_mafia = False
            elif shows_mafia and p.get("fake"):
                p["fake"] = False
                shows_mafia = False
            key = "check_mafia" if shows_mafia else "check_peace"
            res.private.append((uid, t(key, name=esc(p["name"]))))
            result_text = "😈 <b>МАФИЯ!</b>" if shows_mafia else "🙂 <b>не мафия</b>"
            for sid, sp in self.players.items():
                if sp["alive"] and sp["role"] == Role.SERZHANT:
                    res.private.append((sid, t("sergeant_note", name=esc(p["name"]), result=result_text)))

        # 6. Бомж
        for uid, a in acts.items():
            if (self.get_role(uid) != Role.BOMZH or a["type"] != "watch"
                    or uid in blocked or a.get("target") not in self.players):
                continue
            target = a["target"]
            visitors = [esc(self.players[v]["name"]) for v in visits.get(target, []) if v != uid]
            res.private.append((uid, t(
                "bomzh_result",
                target=esc(self.players[target]["name"]),
                visitors=", ".join(visitors) or t("bomzh_none"),
            )))

        # 7. Смена Дона / Комиссара
        res.private.extend(self.promote())
        return res

    # ---------- день ----------

    def vote_counts(self):
        counts = Counter()
        skip = 0
        for voter, target in self.day_votes.items():
            if not self.is_alive(voter):
                continue
            if target is None:
                skip += 1
            else:
                counts[target] += 1
        return counts, skip

    def all_voted(self):
        alive = {uid for uid, _ in self.alive_players()}
        return bool(alive) and alive <= set(self.day_votes)

    def tally_votes(self):
        """Возвращает (казнённый uid или None, Counter, число «пропустить»)."""
        counts, skip = self.vote_counts()
        lynched = None
        if counts:
            top = max(counts.values())
            cands = [uid for uid, c in counts.items() if c == top]
            if len(cands) == 1 and top > skip:
                lynched = cands[0]
        return lynched, counts, skip

    # ---------- победа ----------

    def check_win(self):
        alive = [p for p in self.players.values() if p["alive"]]
        mafia = sum(1 for p in alive if p["role"] in MAFIA_TEAM)
        maniac = sum(1 for p in alive if p["role"] == Role.MANYAK)
        others = len(alive) - mafia - maniac

        if mafia == 0 and maniac == 0:
            return "town"
        if maniac == 0 and mafia >= others:
            return "mafia"
        if mafia == 0 and maniac >= others:
            return "maniac"
        if mafia and maniac:
            if mafia >= others + maniac:
                return "mafia"
            if maniac >= others + mafia:
                return "maniac"
        return None

    def winner_ids(self, winner):
        ids = []
        for uid, p in self.players.items():
            role = p["role"]
            if winner == "mafia" and role in MAFIA_TEAM:
                ids.append(uid)
            elif winner == "maniac" and role == Role.MANYAK:
                ids.append(uid)
            elif winner == "suicide" and role == Role.SAMOUBIYTSA:
                ids.append(uid)
            elif winner == "town" and role not in MAFIA_TEAM + (Role.MANYAK, Role.SAMOUBIYTSA):
                ids.append(uid)
        return ids

    # ---------- сохранение ----------

    def snapshot(self):
        players = {
            str(uid): {
                "name": p["name"], "alive": p["alive"],
                "role": p["role"].name if p["role"] else None,
            }
            for uid, p in self.players.items()
        }
        roles = [p["role"].name for p in self.players.values() if p["role"]]
        return {
            "state": self.state,
            "players": json.dumps(players, ensure_ascii=False),
            "roles": json.dumps(roles),
            "night_actions": json.dumps({str(k): v for k, v in self.night_actions.items()}),
            "day_votes": json.dumps({str(k): v for k, v in self.day_votes.items()}),
            "round_num": self.round_num,
        }


def drop_game(game: Game):
    """Убирает игру из памяти (БД чистится отдельно)."""
    if GAMES.get(game.chat_id) is game:
        GAMES.pop(game.chat_id, None)
    for uid in list(game.players):
        if USER_GAMES.get(uid) == game.chat_id:
            USER_GAMES.pop(uid, None)
