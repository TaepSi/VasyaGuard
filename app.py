import discord
from discord.ext import commands
import datetime
import os
import aiosqlite
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

# Это корни слов. Так бот поймает и "пидор", и "пидорасина", и "заебался"
MUTE_WORDS = [
    'хуй', 'пизд', 'еба', 'ебл', 'бля', 'сук', 'гандон', 'пидор', 'пидар', 
    'хуе', 'охуе', 'заеб', 'муда', 'шлюх', 'курва', 'дроч', 'сучк', 'трах',
    'уеб', 'говн', 'гонд', 'член', 'даун', 'лох', 'дебил', 'урод'
]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Слова, которые бот должен игнорировать, даже если там есть плохой корень
SAFE_WORDS = [
    'дебаты', 'дебат', 'дебют', 'дебетор', 
    'благоговение', 'благоговеть', 'природа', 'урожай',
    'плохо', 'плохой', 'лохматый', 'колебаться', 'неупотребление',
    'страхование', 'страховка', 'застраховать', 'подстраховаться'
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
    # АВТО-МУТ ЗА МАТ
    # =========================================

    if any(word in content for word in MUTE_WORDS) and not is_admin:

        try:
            await message.delete()

            duration = datetime.timedelta(days=1)

            await message.author.timeout(
                duration,
                reason=f"Мат: {message.content[:100]}"
            )

            await message.channel.send(
                f"🤐 {message.author.mention} замучен на 24 часа.",
                delete_after=7
            )

            mute_channel = bot.get_channel(MUTE_LOGS_ID)

            if mute_channel:

                embed = discord.Embed(
                    title="🚫 АВТО-МУТ",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )

                embed.add_field(
                    name="Нарушитель",
                    value=f"{message.author} ({message.author.id})",
                    inline=False
                )

                embed.add_field(
                    name="Сообщение",
                    value=message.content,
                    inline=False
                )

                embed.add_field(
                    name="Срок",
                    value="24 часа",
                    inline=True
                )

                await mute_channel.send(embed=embed)

            return

        except Exception as e:
            print(f"Ошибка при авто-муте: {e}")

        # =========================================
    # АВТО-МУТ ЗА МАТ (С БЕЛЫМ СПИСКОМ)
    # =========================================
    
    # Создаем копию текста для проверки, чтобы не менять оригинал
    check_content = content 

    # 1. Убираем из проверки все безопасные слова
    for safe_word in SAFE_WORDS:
        check_content = check_content.replace(safe_word, "")

    # 2. Теперь проверяем оставшийся текст на наличие мата
    if any(word in check_content for word in MUTE_WORDS) and not is_admin:
        try:
            await message.delete()
            duration = datetime.timedelta(days=1)
            await message.author.timeout(duration, reason=f"Мат: {message.content[:100]}")
            
            await message.channel.send(
                f"🤐 {message.author.mention} замучен на 24 часа. (Следите за языком!)",
                delete_after=7
            )

            # ЛОГ В КАНАЛ МУТОВ
            mute_channel = bot.get_channel(MUTE_LOGS_ID)
            if mute_channel:
                embed = discord.Embed(
                    title="🚫 АВТО-МУТ",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Нарушитель", value=f"{message.author} ({message.author.id})")
                embed.add_field(name="Сообщение", value=message.content)
                embed.add_field(name="Срок", value="24 часа")
                await mute_channel.send(embed=embed)
            return

        except Exception as e:
            print(f"Ошибка при авто-муте: {e}")

    # 2. Удаляем из проверки все безопасные слова
    for safe in SAFE_WORDS:
        check_content = check_content.replace(safe, " ")

    # 3. Проверка на мат
    if any(word in check_content for word in MUTE_WORDS) and not is_admin:
        # Тут твой код удаления сообщения и мута на 24 часа...


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
    async with aiosqlite.connect("stats.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, msg_count INTEGER DEFAULT 0)")
        await db.commit()

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
@bot.event
async def on_ready():
    await init_db()
    bot.add_view(TicketView())

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
