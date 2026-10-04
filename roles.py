from enum import Enum


class Role(Enum):
    MIRNY = "мирный житель"
    DON = "дон"
    MAFIA = "мафия"
    KOMISSAR = "комиссар"
    SERZHANT = "сержант"
    DOKTOR = "доктор"
    MANYAK = "маньяк"
    LYUBOVNITSA = "любовница"
    ADVOKAT = "адвокат"
    SAMOUBIYTSA = "самоубийца"
    BOMZH = "бомж"
    SCHASTLIVCHIK = "счастливчик"
    KAMIKADZE = "камикадзе"


ROLE_EMOJI = {
    Role.MIRNY: "👨‍🌾",
    Role.DON: "🤵",
    Role.MAFIA: "🕴",
    Role.KOMISSAR: "🕵️",
    Role.SERZHANT: "👮",
    Role.DOKTOR: "👨‍⚕️",
    Role.MANYAK: "🔪",
    Role.LYUBOVNITSA: "💃",
    Role.ADVOKAT: "👨‍⚖️",
    Role.SAMOUBIYTSA: "🤡",
    Role.BOMZH: "🧙‍♂️",
    Role.SCHASTLIVCHIK: "🍀",
    Role.KAMIKADZE: "💣",
}

ROLE_DESCRIPTIONS = {
    Role.MIRNY: "Ночью спишь, днём вычисляешь мафию и голосуешь за линч.",
    Role.DON: "Глава мафии. Твой голос приравнивается к двум. Выбираешь жертву ночью.",
    Role.MAFIA: "Подчиняйся дону. После его смерти становишься новым доном.",
    Role.KOMISSAR: "Ночью проверяешь роль одного игрока или убиваешь.",
    Role.SERZHANT: "Помощник комиссара. Видишь его проверки. При смерти комиссара занимаешь его место.",
    Role.DOKTOR: "Ночью спасаешь одного игрока от смерти. Один раз можешь спасти себя.",
    Role.MANYAK: "Одиночка. Каждую ночь убиваешь. Цель — убить всех.",
    Role.LYUBOVNITSA: "Блокируешь ход игрока ночью и его чат днём.",
    Role.ADVOKAT: "Играешь за мафию. Защищаешь игрока: если комиссар проверит его — покажет как мирного.",
    Role.SAMOUBIYTSA: "Нейтрал. Побеждаешь только если тебя казнят днём.",
    Role.BOMZH: "Ночью ходишь к игроку и видишь, кто к нему приходил.",
    Role.SCHASTLIVCHIK: "Мирный житель с шансом 50% выжить при убийстве.",
    Role.KAMIKADZE: "Мирный. При казни днём забираешь одного игрока с собой.",
}

# Команда мафии (Адвокат помогает мафии, но сам не убивает)
MAFIA_TEAM = (Role.DON, Role.MAFIA, Role.ADVOKAT)

# Мирные роли с ночным ходом / особыми способностями
ACTIVE_TOWN_ROLES = (
    Role.KOMISSAR, Role.DOKTOR, Role.BOMZH, Role.LYUBOVNITSA,
    Role.SERZHANT, Role.KAMIKADZE, Role.SCHASTLIVCHIK,
)

# Роли, которым ночью приходит меню с кнопками
NIGHT_ROLES = (
    Role.DON, Role.MAFIA, Role.DOKTOR, Role.KOMISSAR, Role.MANYAK,
    Role.LYUBOVNITSA, Role.ADVOKAT, Role.BOMZH,
)

TEAM_TITLES = {
    "mafia": "😈 Команда: Мафия",
    "town": "🕊 Команда: Мирные жители",
    "neutral": "🎲 Нейтральная роль",
}


def role_team(role: Role) -> str:
    if role in MAFIA_TEAM:
        return "mafia"
    if role in (Role.MANYAK, Role.SAMOUBIYTSA):
        return "neutral"
    return "town"


def role_name(role: Role) -> str:
    return role.value.capitalize()


def role_title(role: Role) -> str:
    return f"{ROLE_EMOJI[role]} {role_name(role)}"


def get_roles_for_player_count(count: int) -> list:
    """Распределение ролей в зависимости от количества игроков."""
    roles = [Role.DON, Role.DOKTOR]
    if count >= 5:
        roles.append(Role.MAFIA)
    if count >= 6:
        roles.append(Role.KOMISSAR)
    if count >= 8:
        roles.append(Role.KAMIKADZE)
        roles.append(Role.BOMZH)
    if count >= 9:
        roles.append(Role.SCHASTLIVCHIK)
    if count >= 10:
        roles.append(Role.LYUBOVNITSA)
        roles.append(Role.MAFIA)
    if count >= 11:
        roles.append(Role.SAMOUBIYTSA)
    if count >= 12:
        roles.append(Role.SERZHANT)
    if count >= 14:
        roles.append(Role.MANYAK)
    if count >= 15:
        roles.append(Role.MAFIA)
    if count >= 16:
        roles.append(Role.ADVOKAT)
    # Добавляем мирных до нужного количества
    while len(roles) < count:
        roles.append(Role.MIRNY)
    return roles[:count]
