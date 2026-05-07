import discord
from discord.ext import commands
import datetime
import os
import aiosqlite
from flask import Flask
from threading import Thread

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

# Для совместимости со старым кодом (если где-то осталось название BAD_WORDS)
BAD_WORDS = MUTE_WORDS 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    content = message.content.lower()
    is_admin = message.author.guild_permissions.administrator

    # --- АВТО-МУТ ЗА МАТ ---
    if any(word in content for word in MUTE_WORDS) and not is_admin:
        try:
            await message.delete()
            duration = datetime.timedelta(days=1)
            await message.author.timeout(duration, reason=f"Мат: {message.content[:100]}")
            await message.channel.send(f"🤐 {message.author.mention} замучен на 24 часа. Следите за речью!", delete_after=7)
            
            mute_channel = bot.get_channel(MUTE_LOGS_ID)
            if mute_channel:
                embed = discord.Embed(title="🚫 АВТО-МУТ", color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                embed.add_field(name="Нарушитель", value=f"{message.author} ({message.author.id})", inline=False)
                embed.add_field(name="Сообщение", value=message.content, inline=False)
                embed.add_field(name="Срок", value="24 часа", inline=True)
                await mute_channel.send(embed=embed)
            return 
        except Exception as e:
            print(f"Ошибка при авто-муте: {e}")

    # --- ОБЫЧНЫЙ ФИЛЬТР ССЫЛОК ---
    if "http" in content and not is_admin:
        await message.delete()
        return

    # --- СТАТИСТИКА ---
    async with aiosqlite.connect("stats.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, msg_count) VALUES (?, 0)", (message.author.id,))
        await db.execute("UPDATE users SET msg_count = msg_count + 1 WHERE user_id = ?", (message.author.id,))
        await db.commit()

    await bot.process_commands(message)

@bot.event
async def on_member_update(before, after):
    if before.timed_out_until != after.timed_out_until:
        mute_channel = bot.get_channel(MUTE_LOGS_ID)
        if mute_channel and after.timed_out_until is not None:
            reason = "Причина не указана"
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id:
                    reason = entry.reason or "Причина не указана"
                    break

            embed = discord.Embed(title="🔨 Выдан тайм-аут", color=discord.Color.orange(), timestamp=datetime.datetime.now(datetime.timezone.utc))
            embed.add_field(name="Пользователь", value=after.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="До окончания", value=f"<t:{int(after.timed_out_until.timestamp())}:R>", inline=True)
            await mute_channel.send(embed=embed)


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
    print(f'✅ {bot.user} заступил на дежурство!')

@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. Статистика
    async with aiosqlite.connect("stats.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, msg_count) VALUES (?, 0)", (message.author.id,))
        await db.execute("UPDATE users SET msg_count = msg_count + 1 WHERE user_id = ?", (message.author.id,))
        await db.commit()

    # 2. Фильтр мата и ссылок
    content = message.content.lower()
    is_admin = message.author.guild_permissions.administrator
    if ("http" in content or any(w in content for w in BAD_WORDS)) and not is_admin:
        await message.delete()
        await message.channel.send(f"🚫 {message.author.mention}, тут такое нельзя!", delete_after=5)
        return

    await bot.process_commands(message)

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
    log_channel = discord.utils.get(member.guild.text_channels, name='logs')
    if log_channel:
        # Считаем, сколько дней назад создан аккаунт
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
            
        embed.add_field(name="ID аккаунта", value=member.id, inline=True)
        embed.add_field(name="Возраст аккаунта", value=f"{account_age} дней", inline=True)
        
        # Если аккаунт совсем свежий (меньше 3 дней), выделим это
        if account_age < 3:
            embed.add_field(name="⚠️ Внимание", value="Очень подозрительный (новый) аккаунт!", inline=False)
            
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
