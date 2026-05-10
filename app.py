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
from profanity_check import predict

# --- БЛОК ОЖИВЛЯЛКИ (ИСПРАВЛЕН ПОРТ) ---
app = Flask('')
@app.route('/')
def home(): return "VasyaGuard is online!"

def run_web():
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
WELCOME_CHAT_ID = 1501603960392253541

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================================
# АНТИСПАМ
# =========================================
user_messages = defaultdict(list)

SPAM_LIMIT = 5
SPAM_TIME = 4
SPAM_TIMEOUT = 10

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
    # АВТОРЕГИСТРАЦИЯ И СТАТИСТИКА В SUPABASE
    # =========================================
    if bot.db_pool:
        async with bot.db_pool.acquire() as conn:
            # Регистрируем юзера, если его нет в таблице users
            await conn.execute('INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING', message.author.id)
            
            # Считаем сообщения за сегодня
            await conn.execute('''
                INSERT INTO daily_message_counts (user_id, message_date, msg_count)
                VALUES ($1, CURRENT_DATE, 1)
                ON CONFLICT (user_id, message_date)
                DO UPDATE SET msg_count = daily_message_counts.msg_count + 1
            ''', message.author.id)

    # =========================================
    # АНТИСПАМ
    # =========================================
    now = time.time()
    user_messages[message.author.id].append(now)
    user_messages[message.author.id] = [
        t for t in user_messages[message.author.id]
        if now - t <= SPAM_TIME
    ]

    if len(user_messages[message.author.id]) >= SPAM_LIMIT and not is_admin:
        try:
            duration = datetime.timedelta(minutes=SPAM_TIMEOUT)
            await message.author.timeout(duration, reason="Антиспам")
            await message.channel.send(f"🚫 {message.author.mention} получил мут за спам.", delete_after=5)

            mute_channel = bot.get_channel(MUTE_LOGS_ID)
            if mute_channel:
                embed = discord.Embed(
                    title="🚫 АНТИСПАМ",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Пользователь", value=f"{message.author} ({message.author.id})", inline=False)
                embed.add_field(name="Наказание", value=f"{SPAM_TIMEOUT} минут тайм-аут", inline=False)
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
            await message.author.timeout(duration, reason="Массовые упоминания")
            await message.channel.send(f"🚫 {message.author.mention} получил мут за массовые упоминания.", delete_after=5)

            mute_channel = bot.get_channel(MUTE_LOGS_ID)
            if mute_channel:
                embed = discord.Embed(
                    title="🚫 МАСС УПОМИНАНИЯ",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Пользователь", value=f"{message.author} ({message.author.id})", inline=False)
                embed.add_field(name="Упоминаний", value=str(len(message.mentions)), inline=False)
                embed.add_field(name="Наказание", value=f"{MENTION_TIMEOUT} минут тайм-аут", inline=False)
                await mute_channel.send(embed=embed)

            return
        except Exception as e:
            print(f"Ошибка анти-масс-пинга: {e}")

    # =========================================
    # УМНАЯ МОДЕРАЦИЯ (6 СТУПЕНЕЙ) - НОВАЯ ВЕРСИЯ
    # =========================================
    if not is_admin:
        # predict вернет [1], если мат, и [0], если чисто
        is_dirty = predict([message.content])[0]

        if is_dirty == 1:
            try:
                await message.delete()
            except:
                pass

            if message.channel.id == DEBATE_CHANNEL_ID:
                await message.channel.send(
                    f"⚠️ **Подозрение на мат в дебатах!** <@&{ADMIN_ROLE_ID}> <@&{MOD_ROLE_ID}>",
                    view=DebateModView(message)
                )
                return

            async with bot.db_pool.acquire() as conn:
                await conn.execute(
                    'INSERT INTO warns (user_id, moderator_id, reason) VALUES ($1, $2, $3)',
                    message.author.id, bot.user.id, f"Мат: {message.content[:50]}"
                )
                count = await conn.fetchval('SELECT COUNT(*) FROM warns WHERE user_id = $1', message.author.id)

            welcome_chat = bot.get_channel(WELCOME_CHAT_ID)
            warn_log = bot.get_channel(WARN_LOGS_ID)
            ban_log = bot.get_channel(BAN_LOGS_ID)

            action_text = ""
            
            if count == 1:
                action_text = "получил **1-й варн** (сообщение удалено)."
            elif count == 2:
                await message.author.timeout(datetime.timedelta(hours=1), reason="2-й мат (1ч мут)")
                action_text = "получил мут на **1 час** (2-е нарушение)."
            elif count == 3:
                action_text = "получил **2-й варн** (3-е нарушение)."
            elif count == 4:
                await message.author.timeout(datetime.timedelta(hours=12), reason="4-й мат (12ч мут)")
                action_text = "получил мут на **12 часов** (4-е нарушение)."
            elif count == 5:
                action_text = "получил **3-й варн** (ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ!)."
            else:
                try:
                    await message.author.ban(reason="Систематический мат (6/6)")
                    action_text = "был **ЗАБАНЕН** за рецидив мата (6-е нарушение)."
                except Exception as e:
                    action_text = f"должен быть забанен, но у бота нет прав! Ошибка: {e}"

            if welcome_chat:
                await welcome_chat.send(f"⚠️ {message.author.mention}, ты {action_text}")

            if count >= 6:
                if ban_log:
                    emb = discord.Embed(title="🔨 АВТО-БАН", color=discord.Color.dark_red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                    emb.add_field(name="Нарушитель", value=f"{message.author.mention}")
                    emb.add_field(name="Причина", value="6-й мат (автоматически)")
                    await ban_log.send(embed=emb)
            else:
                if warn_log:
                    emb = discord.Embed(title="🚫 АВТО-МОДЕРАЦИЯ", color=discord.Color.orange(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                    emb.add_field(name="Юзер", value=f"{message.author.mention}")
                    emb.add_field(name="Итог", value=action_text)
                    emb.add_field(name="Счетчик", value=f"{count}/6")
                    await warn_log.send(embed=emb)
            return

    # =========================================         
    # ФИЛЬТР ССЫЛОК
    # =========================================
    if "http" in content and not is_admin:
        await message.delete()
        await message.channel.send(f"🚫 {message.author.mention}, ссылки запрещены.", delete_after=5)
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

    # =========================================
    # ОБРАБОТКА КОМАНД
    # =========================================
    await bot.process_commands(message)


# --- БАЗА ДАННЫХ ---
async def init_db():
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
        await conn.execute(
            'INSERT INTO warns (user_id, moderator_id, reason) VALUES ($1, $2, $3)',
            member.id, interaction.user.id, reason
        )
        count = await conn.fetchval('SELECT COUNT(*) FROM warns WHERE user_id = $1', member.id)

    log_channel = bot.get_channel(WARN_LOGS_ID)
    if log_channel:
        embed = discord.Embed(
            title="⚠️ РУЧНОЙ ВАРН", 
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Нарушитель", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Модератор", value=f"{interaction.user.mention}", inline=True)
        embed.add_field(name="Причина", value=reason, inline=True)
        embed.add_field(name="Всего варнов", value=str(count), inline=False)
        await log_channel.send(embed=embed)

    public_chat = bot.get_channel(WELCOME_CHAT_ID)
    if public_chat:
        await public_chat.send(
            f"⚠️ {member.mention} получил варн от модератора.\n"
            f"**Причина:** {reason}\n"
            f"**Всего варнов:** {count}"
        )

    await interaction.response.send_message(f"✅ Варн выдан {member.display_name}. Всего: {count}", ephemeral=True)

@bot.tree.command(name="clearwarns", description="Полностью очистить историю варнов пользователя")
@commands.has_permissions(administrator=True)
async def clear_warns(interaction: discord.Interaction, member: discord.Member):
    async with bot.db_pool.acquire() as conn:
        await conn.execute('DELETE FROM warns WHERE user_id = $1', member.id)

    log_channel = bot.get_channel(WARN_LOGS_ID)
    if log_channel:
        embed = discord.Embed(title="♻️ ИСТОРИЯ ОЧИЩЕНА", color=discord.Color.green())
        embed.add_field(name="Пользователь", value=f"{member.mention}")
        embed.add_field(name="Модератор", value=interaction.user.mention)
        await log_channel.send(embed=embed)

    public_chat = bot.get_channel(WELCOME_CHAT_ID)
    if public_chat:
        await public_chat.send(f"✨ Модератор аннулировал все варны пользователя {member.mention}. Чистый лист!")

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
        embed = discord.Embed(title="➖ ВАРН СНЯТ", color=discord.Color.blue(), timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="С кого", value=f"{member.mention}")
        embed.add_field(name="Кто снял", value=interaction.user.mention)
        embed.add_field(name="Осталось варнов", value=str(remaining))
        await log_channel.send(embed=embed)

    public_chat = bot.get_channel(WELCOME_CHAT_ID)
    if public_chat:
        await public_chat.send(
            f"😇 Модератор снял варн с {member.mention}.\n"
            f"**Осталось варнов:** {remaining}"
        )

    await interaction.response.send_message(f"✅ Последний варн снят. У {member.display_name} осталось **{remaining}**.", ephemeral=True)

@bot.tree.command(name="ban", description="Забанить пользователя")
@commands.has_permissions(administrator=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    try:
        await member.ban(reason=reason)
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
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав для закрытия тикета!", ephemeral=True)

        async with bot.db_pool.acquire() as conn:
            await conn.execute('DELETE FROM tickets WHERE channel_id = $1', interaction.channel_id)

        await interaction.response.send_message("✅ База очищена. Канал будет удален через пару секунд...")
        import asyncio
        await asyncio.sleep(2)
        try:
            await interaction.channel.delete(reason=f"Тикет закрыт модератором {interaction.user}")
        except discord.Forbidden:
            await interaction.channel.send("❌ Ошибка: У бота нет прав на удаление каналов! Проверьте настройки ролей.")
        except Exception as e:
            print(f"Ошибка при удалении тикета: {e}")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Открыть тикет", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        async with bot.db_pool.acquire() as conn:
            ticket_data = await conn.fetchrow('SELECT channel_id FROM tickets WHERE user_id = $1 AND status = $2', user.id, 'open')
        
        if ticket_data:
            channel = bot.get_channel(ticket_data['channel_id'])
            if channel:
                return await interaction.response.send_message(f"У тебя уже есть тикет: {channel.mention}", ephemeral=True)
            else:
                async with bot.db_pool.acquire() as conn:
                    await conn.execute('DELETE FROM tickets WHERE channel_id = $1', ticket_data['channel_id'])

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await guild.create_text_channel(f"ticket-{user.name}", overwrites=overwrites)

        async with bot.db_pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO tickets (channel_id, user_id, status) VALUES ($1, $2, $3)',
                channel.id, user.id, 'open'
            )

        await interaction.response.send_message(f"Тикет создан: {channel.mention}", ephemeral=True)
        view = CloseTicketView()
        await channel.send(f"Привет {user.mention}! Опиши проблему. Чтобы закрыть тикет, нажми кнопку ниже.", view=view)


# --- СОБЫТИЯ ---
bot.db_pool = None

async def init_supabase():
    DATABASE_URL = os.getenv('DATABASE_URL')
    bot.db_pool = await asyncpg.create_pool(DATABASE_URL)
    print("💎 Supabase подключен!")

@bot.event
async def on_ready():
    await init_db()
    await init_supabase()
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
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
    WELCOME_CHANNEL_ID = 1501603960392253541
    CONFESSION_CHANNEL_ID = 1501617086278144031
    LOG_CHANNEL_NAME = 'logs'

    welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if welcome_channel:
        welcome_text = (
            f"Мир вам, {member.mention}! 🤝 "
            f"Добро пожаловать на наш христианский сервер. "
            f"Здесь мы вместе изучаем Слово Божье, делимся радостью и "
            f"поддерживаем друг друга в вере. Чувствуйте себя как дома! "
            f"Вы можете выбрать свою конфессию в <#{CONFESSION_CHANNEL_ID}>"
        )
        await welcome_channel.send(welcome_text)

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
    DEBATE_CHANNEL_ID = 1501863197701963786
    REPORTS_LOG_ID = 1501935770280395014

    if interaction.channel_id != DEBATE_CHANNEL_ID:
        return await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{DEBATE_CHANNEL_ID}>!", 
            ephemeral=True
        )

    report_channel = bot.get_channel(REPORTS_LOG_ID)
    if not report_channel:
        return await interaction.response.send_message("❌ Ошибка: Канал для жалоб не найден.", ephemeral=True)

    embed = discord.Embed(
        title="🚨 Новая жалоба", 
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="Отправитель", value=interaction.user.mention, inline=True)
    embed.add_field(name="Нарушитель", value=нарушитель.mention, inline=True)
    embed.add_field(name="Причина", value=причина, inline=False)
    embed.set_footer(text=f"ID автора: {interaction.user.id}")

    await report_channel.send(embed=embed)
    
    await interaction.response.send_message("✅ Ваша жалоба отправлена администрации. Спасибо!", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("✅ Команда `/report` синхронизирована и готова к работе!")

# --- КОМАНДЫ ---
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Понг! {round(bot.latency * 1000)}мс")

@bot.command(name="top")
async def top(ctx):
    async with bot.db_pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT user_id, msg_count 
            FROM stats 
            ORDER BY msg_count DESC 
            LIMIT 10
        ''')
    
    if not rows:
        return await ctx.send("Статистика в облаке пока пуста.")
    
    embed = discord.Embed(
        title="🏆 Топ активных участников", 
        color=discord.Color.gold(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    description = ""
    for i, row in enumerate(rows, 1):
        member = ctx.guild.get_member(row['user_id'])
        name = member.display_name if member else f"Юзер {row['user_id']}"
        description += f"**{i}.** {name} — `{row['msg_count']}` сообщ.\n"
    
    embed.description = description
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_tickets(ctx):
    embed = discord.Embed(title="Поддержка", description="Нажми кнопку ниже, чтобы создать приватный чат с админами.")
    await ctx.send(embed=embed, view=TicketView())

# =========================================
# КОМАНДА !ктоя
# =========================================
@bot.command(name="ктоя")
async def who_am_i(ctx):
    user = ctx.author
    guild = ctx.guild

    async with bot.db_pool.acquire() as conn:
        # 1. Инфа о человеке
        user_data = await conn.fetchrow('SELECT status, registered_at FROM users WHERE user_id = $1', user.id)
        if not user_data:
            await conn.execute('INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING', user.id)
            user_data = await conn.fetchrow('SELECT status, registered_at FROM users WHERE user_id = $1', user.id)

        # 2. Описание
        desc_data = await conn.fetchrow('SELECT description FROM user_descriptions WHERE user_id = $1', user.id)

        # 3. Награды
        awards = await conn.fetch('SELECT award_name FROM user_awards WHERE user_id = $1', user.id)

        # 4. Статистика общая
        total_msgs = await conn.fetchval('SELECT msg_count FROM stats WHERE user_id = $1', user.id)
        total_msgs = total_msgs or 0

        # 5. Статистика за сегодня
        today_msgs = await conn.fetchval(
            'SELECT msg_count FROM daily_message_counts WHERE user_id = $1 AND message_date = CURRENT_DATE',
            user.id
        )
        today_msgs = today_msgs or 0

        # 6. Варны
        warn_count = await conn.fetchval('SELECT COUNT(*) FROM warns WHERE user_id = $1', user.id)
        warn_count = warn_count or 0

    # Собираем embed
    days_on_server = (datetime.datetime.now(datetime.timezone.utc) - user.joined_at).days if user.joined_at else "?"
    roles = ", ".join([role.mention for role in user.roles if role.name != "@everyone"]) or "Нет ролей"

    embed = discord.Embed(
        title=f"📋 Профиль: {user.display_name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else user.default_avatar.url)
    
    embed.add_field(name="🏷 Ник", value=user.name, inline=True)
    embed.add_field(name="📅 На сервере", value=f"{days_on_server} дн.", inline=True)
    embed.add_field(name="🛡 Роли", value=roles, inline=False)
    
    status_text = user_data['status'] or "Не установлен"
    embed.add_field(name="📝 Статус", value=status_text, inline=False)
    
    desc_text = desc_data['description'] if desc_data and desc_data['description'] else "Описание отсутствует"
    embed.add_field(name="📖 Описание", value=desc_text, inline=False)
    
    awards_text = ", ".join([a['award_name'] for a in awards]) if awards else "Нет наград"
    embed.add_field(name="🏆 Награды", value=awards_text, inline=False)
    
    embed.add_field(name="💬 Сообщений всего", value=str(total_msgs), inline=True)
    embed.add_field(name="📆 Сообщений сегодня", value=str(today_msgs), inline=True)
    embed.add_field(name="⚠️ Варнов", value=str(warn_count), inline=True)

    await ctx.send(embed=embed)

# =========================================
# КОМАНДА !статус
# =========================================
@bot.command(name="статус")
async def set_status(ctx, *, text=None):
    if text is None:
        await ctx.send("❌ Используй: `!статус твой текст`")
        return
    
    async with bot.db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, status) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET status = $2, last_updated = NOW()
        ''', ctx.author.id, text)
    
    await ctx.send(f"✅ Статус обновлён!")

# =========================================
# КОМАНДА !описание
# =========================================
@bot.command(name="описание")
async def set_description(ctx, *, text=None):
    if text is None:
        await ctx.send("❌ Используй: `!описание твой текст` (или `!описание стереть`)")
        return

    user_id = ctx.author.id

    if text.strip().lower() in ["стереть", "удалить", "очистить"]:
        async with bot.db_pool.acquire() as conn:
            await conn.execute('DELETE FROM user_descriptions WHERE user_id = $1', user_id)
        await ctx.send("🗑 Описание удалено.")
        return

    async with bot.db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO user_descriptions (user_id, description) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET description = $2, updated_at = NOW()
        ''', user_id, text)

    await ctx.send("✅ Описание сохранено!")

# =========================================
# КОМАНДА !награда (только для админов)
# =========================================
@bot.command(name="награда")
@commands.has_permissions(administrator=True)
async def give_award(ctx, member: discord.Member, *, award_name: str):
    async with bot.db_pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO user_awards (user_id, award_name, awarded_by) VALUES ($1, $2, $3)',
            member.id, award_name, ctx.author.id
        )
    
    await ctx.send(f"🏆 Награда **{award_name}** выдана пользователю {member.mention}!")

# --- ЗАПУСК ---
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
