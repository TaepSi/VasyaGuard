import discord
from discord.ext import commands
import datetime
import os
import aiosqlite
import asyncpg 
from flask import Flask
from threading import Thread
from collections import defaultdict
import time

# --- БЛОК ОЖИВЛЯЛКИ (ИСПРАВЛЕН ПОРТ) ---
app = Flask('')
@app.route('/')
def home(): return "VasyaGuard is online!"

def run_web():
    # Render автоматически подставит нужный порт
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("DISCORD_TOKEN")
MUTE_LOGS_ID = 1501939058803474473
WARN_LOGS_ID = 1502244124223471737
DEBATE_CHANNEL_ID = 1501863197701963786
ADMIN_ROLE_ID = 1501598779931885741
MOD_ROLE_ID = 1501599782047580302
BAN_LOGS_ID = 1502297873298227222

# Исправленные корни, чтобы не было ложных мутов
MUTE_WORDS = [
    'хуй', 'пизд', 'еба', 'ебл', 'бля', 'гандон', 'пидор', 'пидар', 
    'хуе', 'охуе', 'заеб', 'муда', 'шлюх', 'курва', 'дроч', 'сучк', ' трах',
    'уеб', 'гавн', 'гонд', ' член ', 'даун', ' дебил', 'уродец', 'уродин', ' сука'
]
# Заметил пробелы? Например ' сука' не даст мут за слово 'рисунок'

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Слова, которые бот должен игнорировать, даже если там есть плохой корень
SAFE_WORDS = [
    'дебаты', 'дебат', 'дебют', 'дебетор', 
    'благоговение', 'благоговеть', 'природа', 'урожай',
    'плохо', 'плохой', 'лохматый', 'колебаться', 'неупотребление',
    'страхование', 'страховка', 'застраховать', 'подстраховаться', 
    'правки', 'правили', 'исправлений', 'источниками', 'страх', 'страница'
]


# =========================================
# АНТИСПАМ
# =========================================

user_messages = defaultdict(list)

SPAM_LIMIT = 5      # сообщений
SPAM_TIME = 4       # секунд
SPAM_TIMEOUT = 10   # минут

# =========================================
# АНТИ МАСС УПОМИНАНИЯ
# =========================================

MAX_MENTIONS = 5
MENTION_TIMEOUT = 30

class DebateModView(discord.ui.View):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=None)
        self.message = message

    @discord.ui.button(label="Удалить сообщение", style=discord.ButtonStyle.danger)
    async def delete_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав: только админ или модер
        if not any(role.id in [ADMIN_ROLE_ID, MOD_ROLE_ID] for role in interaction.user.roles):
            return await interaction.response.send_message("У вас нет власти здесь!", ephemeral=True)
        
        try:
            await self.message.delete()
            await interaction.response.edit_message(content=f"✅ Сообщение удалено модератором {interaction.user.mention}", view=None)
        except:
            await interaction.response.send_message("Не удалось удалить. Возможно, оно уже удалено.", ephemeral=True)

    @discord.ui.button(label="Оставить", style=discord.ButtonStyle.secondary)
    async def keep_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id in [ADMIN_ROLE_ID, MOD_ROLE_ID] for role in interaction.user.roles):
            return await interaction.response.send_message("У вас нет власти здесь!", ephemeral=True)
            
        await interaction.response.edit_message(content=f"⚪ Модератор {interaction.user.mention} разрешил оставить это сообщение.", view=None)


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    content = message.content.lower()
    is_admin = message.author.guild_permissions.administrator

    # =========================================
    # АНТИСПАМ
    # =========================================

    now = time.time()

    user_messages[message.author.id].append(now)

    # оставляем только свежие сообщения
    user_messages[message.author.id] = [
        t for t in user_messages[message.author.id]
        if now - t <= SPAM_TIME
    ]

    # если спамит
    if len(user_messages[message.author.id]) >= SPAM_LIMIT and not is_admin:

        try:
            duration = datetime.timedelta(minutes=SPAM_TIMEOUT)

            await message.author.timeout(
                duration,
                reason="Антиспам"
            )

            await message.channel.send(
                f"🚫 {message.author.mention} получил мут за спам.",
                delete_after=5
            )

            # ЛОГ В КАНАЛ МУТОВ
            mute_channel = bot.get_channel(MUTE_LOGS_ID)

            if mute_channel:

                embed = discord.Embed(
                    title="🚫 АНТИСПАМ",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )

                embed.add_field(
                    name="Пользователь",
                    value=f"{message.author} ({message.author.id})",
                    inline=False
                )

                embed.add_field(
                    name="Наказание",
                    value=f"{SPAM_TIMEOUT} минут тайм-аут",
                    inline=False
                )

                await mute_channel.send(embed=embed)

            user_messages[message.author.id].clear()

            return

        except Exception as e:
            print(f"Ошибка антиспама: {e}")

    # =========================================
    # АНТИ МАСС УПОМИНАНИЯ
    # =========================================

    if len(message.mentions) >= MAX_MENTIONS and not is_admin:

        try:
            await message.delete()

            duration = datetime.timedelta(minutes=MENTION_TIMEOUT)

            await message.author.timeout(
                duration,
                reason="Массовые упоминания"
            )

            await message.channel.send(
                f"🚫 {message.author.mention} получил мут за массовые упоминания.",
                delete_after=5
            )

            # ЛОГ В КАНАЛ МУТОВ
            mute_channel = bot.get_channel(MUTE_LOGS_ID)

            if mute_channel:

                embed = discord.Embed(
                    title="🚫 МАСС УПОМИНАНИЯ",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )

                embed.add_field(
                    name="Пользователь",
                    value=f"{message.author} ({message.author.id})",
                    inline=False
                )

                embed.add_field(
                    name="Упоминаний",
                    value=str(len(message.mentions)),
                    inline=False
                )

                embed.add_field(
                    name="Наказание",
                    value=f"{MENTION_TIMEOUT} минут тайм-аут",
                    inline=False
                )

                await mute_channel.send(embed=embed)

            return

        except Exception as e:
            print(f"Ошибка анти-масс-пинга: {e}")

        # =========================================
    # УМНАЯ МОДЕРАЦИЯ (6 УРОВНЕЙ НАКАЗАНИЙ)
    # =========================================
    if not is_admin:
        check_content = content
        for safe in SAFE_WORDS:
            check_content = check_content.replace(safe, "")

        if any(bad_root in check_content for bad_root in MUTE_WORDS):
            # --- 1. КАНАЛ ДЕБАТОВ (БЕЗ МУТОВ, ТОЛЬКО КНОПКИ) ---
            if message.channel.id == DEBATE_CHANNEL_ID:
                await message.channel.send(
                    f"⚠️ **Подозрение на мат!** <@&1501598779931885741> <@&1501599782047580302>",
                    view=DebateModView(message)
                )
                return

            # --- 2. ПРОГРЕССИЯ ДЛЯ ОБЫЧНЫХ ЧАТОВ ---
            try:
                await message.delete()
                
                async with bot.db_pool.acquire() as conn:
                    # Узнаем текущее кол-во нарушений (считаем записи в таблице warns)
                    # Каждое попадание в этот блок = +1 нарушение в историю
                    await conn.execute(
                        'INSERT INTO warns (user_id, moderator_id, reason) VALUES ($1, $2, $3)',
                        message.author.id, bot.user.id, f"Авто-мат: {message.content[:50]}"
                    )
                    count = await conn.fetchval('SELECT COUNT(*) FROM warns WHERE user_id = $1', message.author.id)

                welcome_chat = bot.get_channel(WELCOME_CHANNEL_ID)
                warn_log = bot.get_channel(WARN_LOGS_ID)
                ban_log = bot.get_channel(BAN_LOGS_ID)

                action_text = ""
                
                # ЛЕСТНИЦА НАКАЗАНИЙ (Твоя структура)
                if count == 1:
                    action_text = "получил **1-й варн** (сообщение удалено)."
                
                elif count == 2:
                    await message.author.timeout(datetime.timedelta(hours=1), reason="2-е нарушение (мат)")
                    action_text = "получил мут на **1 час** (2-е нарушение)."
                
                elif count == 3:
                    action_text = "получил **2-й варн** (3-е нарушение)."
                
                elif count == 4:
                    await message.author.timeout(datetime.timedelta(hours=12), reason="4-е нарушение (мат)")
                    action_text = "получил мут на **12 часов** (4-е нарушение)."
                
                elif count == 5:
                    action_text = "получил **3-й варн** (ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ!)."
                
                else: # 6-й мат и выше
                    await message.author.ban(reason="6-е нарушение (систематический мат)")
                    action_text = "был **ЗАБАНЕН** (6-е нарушение)."

                # Анонс в Велком-чат
                if welcome_chat:
                    await welcome_chat.send(f"⚠️ {message.author.mention} {action_text}")

                # Логирование в зависимости от типа наказания
                if count >= 6: # Лог Бана
                    if ban_log:
                        embed = discord.Embed(title="🔨 БАН (АВТО)", color=discord.Color.dark_red())
                        embed.add_field(name="Нарушитель", value=f"{message.author} ({message.author.id})")
                        embed.add_field(name="Причина", value="Систематический мат (6/6)")
                        await ban_log.send(embed=embed)
                else: # Лог Варна/Мута
                    if warn_log:
                        embed = discord.Embed(title="🚫 НАРУШЕНИЕ", color=discord.Color.orange())
                        embed.add_field(name="Юзер", value=f"{message.author}")
                        embed.add_field(name="Действие", value=action_text)
                        embed.add_field(name="Счетчик", value=f"{count}/6")
                        await warn_log.send(embed=embed)

                return

            except Exception as e:
                print(f"Ошибка в системе прогрессии: {e}")

    
    
    # =========================================         
    # ФИЛЬТР ССЫЛОК
    # =========================================

    if "http" in content and not is_admin:

        await message.delete()

        await message.channel.send(
            f"🚫 {message.author.mention}, ссылки запрещены.",
            delete_after=5
        )

        return


    # =========================================
    # ОБЛАЧНАЯ СТАТИСТИКА (SUPABASE)
    # =========================================
    if bot.db_pool:
        async with bot.db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO stats (user_id, msg_count) 
                VALUES ($1, 1)
                ON CONFLICT (user_id) 
                DO UPDATE SET msg_count = stats.msg_count + 1
            ''', message.author.id)

    # Не забываем про команды !
    await bot.process_commands(message)

    
    # =========================================
    # СТАТИСТИКА
    # =========================================

    async with aiosqlite.connect("stats.db") as db:

        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, msg_count) VALUES (?, 0)",
            (message.author.id,)
        )

        await db.execute(
            "UPDATE users SET msg_count = msg_count + 1 WHERE user_id = ?",
            (message.author.id,)
        )

        await db.commit()

    # =========================================
    # КОМАНДЫ
    # =========================================

    await bot.process_commands(message)
# --- БАЗА ДАННЫХ ---
async def init_db():
    # Твой старый sqlite для локальной статистики
    async with aiosqlite.connect("stats.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, msg_count INTEGER DEFAULT 0)")
        await db.commit()

# --- КОМАНДЫ ВАРНОВ (SUPABASE) ---

@bot.tree.command(name="check", description="Посмотреть варны пользователя")
@commands.has_permissions(administrator=True)
async def check(interaction: discord.Interaction, member: discord.Member):
    async with bot.db_pool.acquire() as conn:
        rows = await conn.fetch('SELECT reason, timestamp FROM warns WHERE user_id = $1 ORDER BY timestamp DESC', member.id)
    
    if not rows:
        return await interaction.response.send_message("Чист!", ephemeral=True)

    history = "\n".join([f"• `{r['timestamp'].strftime('%d.%m.%y')}`: {r['reason']}" for r in rows])
    await interaction.response.send_message(f"**История {member.display_name}:**\n{history}", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать варн пользователю")
@commands.has_permissions(administrator=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    async with bot.db_pool.acquire() as conn:
        # 1. Пишем в базу
        await conn.execute(
            'INSERT INTO warns (user_id, moderator_id, reason) VALUES ($1, $2, $3)',
            member.id, interaction.user.id, reason
        )
        count = await conn.fetchval('SELECT COUNT(*) FROM warns WHERE user_id = $1', member.id)

    # 2. Логируем в канал
    log_channel = bot.get_channel(WARN_LOGS_ID)
    if log_channel:
        embed = discord.Embed(
            title="⚠️ НОВЫЙ ВАРН", 
            color=discord.Color.from_rgb(255, 165, 0),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Нарушитель", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Модератор", value=f"{interaction.user.mention}", inline=True)
        embed.add_field(name="Причина", value=reason, inline=True)
        embed.add_field(name="Всего варнов", value=f"**{count}**", inline=False)
        await log_channel.send(embed=embed)

    await interaction.response.send_message(f"✅ Варн выдан {member.mention}. Всего: {count}", ephemeral=True)

@bot.tree.command(name="clearwarns", description="Полностью очистить историю варнов пользователя")
@commands.has_permissions(administrator=True)
async def clear_warns(interaction: discord.Interaction, member: discord.Member):
    async with bot.db_pool.acquire() as conn:
        await conn.execute('DELETE FROM warns WHERE user_id = $1', member.id)

    log_channel = bot.get_channel(WARN_LOGS_ID)
    if log_channel:
        embed = discord.Embed(
            title="♻️ ИСТОРИЯ ОЧИЩЕНА",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Пользователь", value=f"{member.mention}")
        embed.add_field(name="Модератор", value=interaction.user.mention)
        await log_channel.send(embed=embed)

    await interaction.response.send_message(f"✅ Все варны {member.display_name} удалены.", ephemeral=True)
    
@bot.tree.command(name="unwarn", description="Снять последний варн у пользователя")
@commands.has_permissions(administrator=True)
async def unwarn(interaction: discord.Interaction, member: discord.Member):
    async with bot.db_pool.acquire() as conn:
        last_warn_id = await conn.fetchval(
            'SELECT warn_id FROM warns WHERE user_id = $1 ORDER BY timestamp DESC LIMIT 1', 
            member.id
        )

        if not last_warn_id:
            return await interaction.response.send_message("У этого пользователя нет варнов.", ephemeral=True)

        await conn.execute('DELETE FROM warns WHERE warn_id = $1', last_warn_id)
        remaining = await conn.fetchval('SELECT COUNT(*) FROM warns WHERE user_id = $1', member.id)

    log_channel = bot.get_channel(WARN_LOGS_ID)
    if log_channel:
        embed = discord.Embed(
            title="➖ ВАРН СНЯТ",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Пользователь", value=f"{member.mention}")
        embed.add_field(name="Модератор", value=interaction.user.mention)
        embed.add_field(name="Осталось", value=str(remaining))
        await log_channel.send(embed=embed)

    await interaction.response.send_message(f"✅ Последний варн снят. Осталось: {remaining}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанить пользователя")
@commands.has_permissions(administrator=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    try:
        await member.ban(reason=reason)
        
        # Лог в канал банов
        ban_log = bot.get_channel(BAN_LOGS_ID)
        if ban_log:
            embed = discord.Embed(title="🔨 РУЧНОЙ БАН", color=discord.Color.red())
            embed.add_field(name="Нарушитель", value=f"{member.mention} ({member.id})")
            embed.add_field(name="Модератор", value=interaction.user.mention)
            embed.add_field(name="Причина", value=reason)
            await ban_log.send(embed=embed)

        await interaction.response.send_message(f"✅ Пользователь {member.display_name} успешно забанен.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при бане: {e}", ephemeral=True)


# --- ТИКЕТЫ ---
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Открыть тикет", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        existing_channel = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
        
        if existing_channel:
            return await interaction.response.send_message(f"У тебя уже есть тикет: {existing_channel.mention}", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await guild.create_text_channel(f"ticket-{user.name}", overwrites=overwrites)
        await interaction.response.send_message(f"Тикет создан: {channel.mention}", ephemeral=True)
        await channel.send(f"Привет {user.mention}! Опиши проблему. Админы скоро подойдут.")

# --- СОБЫТИЯ ---
bot.db_pool = None

async def init_supabase():
    # Берет ссылку из Environment на Render
    DATABASE_URL = os.getenv('DATABASE_URL')
    bot.db_pool = await asyncpg.create_pool(DATABASE_URL)
    print("💎 Supabase подключен!")

@bot.event
async def on_ready():
    await init_db() # Твой старый sqlite
    await init_supabase() # Новый supabase
    
    # Регистрируем все постоянные кнопки
    bot.add_view(TicketView())
    bot.add_view(DebateModView()) 

    try:
        await bot.tree.sync()
        print("🔄 Slash-команды синхронизированы")
    except Exception as e:
        print(f"Ошибка sync: {e}")

    print(f'✅ {bot.user} заступил на дежурство!')

# --- ЛОГИ (ИСПРАВЛЕНО ВРЕМЯ) ---
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    log_channel = discord.utils.get(message.guild.text_channels, name='logs')
    if log_channel:
        embed = discord.Embed(title="🗑 Удалено", color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="Автор", value=f"{message.author.mention}")
        embed.add_field(name="Текст", value=message.content or "Файл", inline=False)
        await log_channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    log_channel = discord.utils.get(before.guild.text_channels, name='logs')
    if log_channel:
        embed = discord.Embed(title="📝 Изменено", color=discord.Color.orange(), timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="Автор", value=before.author.mention)
        embed.add_field(name="Было", value=before.content, inline=False)
        embed.add_field(name="Стало", value=after.content, inline=False)
        await log_channel.send(embed=embed)

# Лог входа новых участников
@bot.event
async def on_member_join(member):
    # ID КАНАЛОВ
    WELCOME_CHANNEL_ID = 1501603960392253541  # Общий чат для приветствия
    CONFESSION_CHANNEL_ID = 1501617086278144031  # Чат выбора конфессии
    LOG_CHANNEL_NAME = 'logs'

    # 1. ПРИВЕТСТВИЕ В ОБЩЕМ ЧАТЕ
    welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if welcome_channel:
        # Формируем текст с кликабельной ссылкой на канал
        welcome_text = (
            f"Мир вам, {member.mention}! 🤝 "
            f"Добро пожаловать на наш христианский сервер. "
            f"Здесь мы вместе изучаем Слово Божье, делимся радостью и "
            f"поддерживаем друг друга в вере. Чувствуйте себя как дома! "
            f"Вы можете выбрать свою конфессию в <#{CONFESSION_CHANNEL_ID}>"
        )
        await welcome_channel.send(welcome_text)

    # 2. ТЕХНИЧЕСКИЙ ЛОГ ДЛЯ АДМИНОВ
    log_channel = discord.utils.get(member.guild.text_channels, name=LOG_CHANNEL_NAME)
    if log_channel:
        now = datetime.datetime.now(datetime.timezone.utc)
        account_age = (now - member.created_at).days
        
        embed = discord.Embed(
            title="📥 Новый участник", 
            color=discord.Color.green(), 
            description=f"{member.mention} зашел на сервер.",
            timestamp=now
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            
        embed.add_field(name="Аккаунту дней", value=account_age, inline=True)
        if account_age < 3:
            embed.add_field(name="⚠️ Внимание", value="Новый аккаунт!", inline=False)
            
        await log_channel.send(embed=embed)


# Лог выхода участников
@bot.event
async def on_member_remove(member):
    log_channel = discord.utils.get(member.guild.text_channels, name='logs')
    if log_channel:
        embed = discord.Embed(
            title="📤 Участник покинул сервер", 
            color=discord.Color.light_grey(), 
            description=f"**{member.name}**#{member.discriminator} (ID: {member.id}) ушел от нас.",
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            
        await log_channel.send(embed=embed)

# --- СИСТЕМА ЖАЛОБ (/report) ---

@bot.tree.command(name="report", description="Отправить жалобу на игрока (только для чата дебатов)")
@discord.app_commands.describe(нарушитель="На кого жалуемся?", причина="Что именно он нарушил?")
async def report(interaction: discord.Interaction, нарушитель: discord.Member, причина: str):
    # Твои ID каналов
    DEBATE_CHANNEL_ID = 1501863197701963786  # чат-дебатов
    REPORTS_LOG_ID = 1501935770280395014     # жалобы

    # 1. Проверяем канал
    if interaction.channel_id != DEBATE_CHANNEL_ID:
        return await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{DEBATE_CHANNEL_ID}>!", 
            ephemeral=True
        )

    # 2. Ищем канал для админов
    report_channel = bot.get_channel(REPORTS_LOG_ID)
    if not report_channel:
        return await interaction.response.send_message("❌ Ошибка: Канал для жалоб не найден.", ephemeral=True)

    # 3. Создаем карточку жалобы
    embed = discord.Embed(
        title="🚨 Новая жалоба", 
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="Отправитель", value=interaction.user.mention, inline=True)
    embed.add_field(name="Нарушитель", value=нарушитель.mention, inline=True)
    embed.add_field(name="Причина", value=причина, inline=False)
    embed.set_footer(text=f"ID автора: {interaction.user.id}")

    # Отправляем в канал #жалобы
    await report_channel.send(embed=embed)
    
    # Ответ пользователю (скрытый)
    await interaction.response.send_message("✅ Ваша жалоба отправлена администрации. Спасибо!", ephemeral=True)

# Команда для синхронизации слеш-команд
@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("✅ Команда `/report` синхронизирована и готова к работе!")



# --- КОМАНДЫ ---
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Понг! {round(bot.latency * 1000)}мс")

@bot.command()
async def top(ctx):
    async with aiosqlite.connect("stats.db") as db:
        async with db.execute("SELECT user_id, msg_count FROM users ORDER BY msg_count DESC LIMIT 10") as cursor:
            rows = await cursor.fetchall()
    
    if not rows: return await ctx.send("Статистика пуста.")
    
    embed = discord.Embed(title="🏆 Топ активных участников", color=discord.Color.gold())
    for i, (user_id, count) in enumerate(rows, 1):
        user = bot.get_user(user_id)
        name = user.name if user else f"ID: {user_id}"
        embed.add_field(name=f"{i}. {name}", value=f"Сообщений: {count}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_tickets(ctx):
    embed = discord.Embed(title="Поддержка", description="Нажми кнопку ниже, чтобы создать приватный чат с админами.")
    await ctx.send(embed=embed, view=TicketView())

# --- ЗАПУСК ---
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
