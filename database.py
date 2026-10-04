import aiosqlite

from config import DB_PATH

# Колонки инвентаря, которые разрешено изменять
INVENTORY_COLUMNS = ("shield", "fake_id", "active_role")


class Database:
    def __init__(self, path):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    money INTEGER DEFAULT 0,
                    gems INTEGER DEFAULT 0,
                    games_played INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    shield INTEGER DEFAULT 0,
                    fake_id INTEGER DEFAULT 0,
                    active_role INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    chat_id INTEGER PRIMARY KEY,
                    state TEXT,
                    players TEXT,
                    roles TEXT,
                    night_actions TEXT,
                    day_votes TEXT,
                    round_num INTEGER DEFAULT 0
                )
            """)
            # Миграция для баз, созданных по старой схеме
            async with db.execute("PRAGMA table_info(users)") as cur:
                existing = {row[1] for row in await cur.fetchall()}
            for col in INVENTORY_COLUMNS:
                if col not in existing:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
            # Незавершённые игры после перезапуска восстановить нельзя
            await db.execute("DELETE FROM games")
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
                return await cur.fetchone()

    async def create_user(self, user_id, username):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            await db.commit()

    async def ensure_user(self, user_id, username):
        """Создаёт пользователя (если нет), обновляет имя и возвращает запись."""
        await self.create_user(user_id, username)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            await db.commit()
        return await self.get_user(user_id)

    async def update_stats(self, user_id, money=0, gems=0, played=0, win=0):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                UPDATE users SET money = money + ?, gems = gems + ?,
                games_played = games_played + ?, wins = wins + ?
                WHERE user_id = ?
            """, (money, gems, played, win, user_id))
            await db.commit()

    async def get_top(self, limit=10):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT username, wins, games_played FROM users "
                "WHERE games_played > 0 ORDER BY wins DESC, games_played ASC LIMIT ?",
                (limit,),
            ) as cur:
                return await cur.fetchall()

    async def buy_item(self, user_id, column, price):
        """Атомарная покупка предмета. Возвращает True, если хватило монет."""
        if column not in INVENTORY_COLUMNS:
            return False
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                f"UPDATE users SET money = money - ?, {column} = {column} + 1 "
                "WHERE user_id = ? AND money >= ?",
                (price, user_id, price),
            )
            await db.commit()
            return cur.rowcount > 0

    async def consume_item(self, user_id, column):
        if column not in INVENTORY_COLUMNS:
            return False
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                f"UPDATE users SET {column} = {column} - 1 WHERE user_id = ? AND {column} > 0",
                (user_id,),
            )
            await db.commit()
            return cur.rowcount > 0

    async def exchange_gem(self, user_id, rate):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE users SET gems = gems - 1, money = money + ? WHERE user_id = ? AND gems > 0",
                (rate, user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def save_game(self, chat_id, state, players, roles, night_actions, day_votes, round_num):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO games
                (chat_id, state, players, roles, night_actions, day_votes, round_num)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (chat_id, state, players, roles, night_actions, day_votes, round_num))
            await db.commit()

    async def get_game(self, chat_id):
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT * FROM games WHERE chat_id = ?", (chat_id,)) as cur:
                return await cur.fetchone()

    async def delete_game(self, chat_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
            await db.commit()


# Общий экземпляр, который используют все модули
db = Database(DB_PATH)
