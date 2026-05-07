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
BAD_WORDS = ['хер', 'сука', 'бля', 'блять', 'пидор', 'гандон']

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

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
        embed = discord.Embed(
            title="📥 Новый участник", 
            color=discord.Color.green(), 
            description=f"{member.mention} зашел на сервер.",
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        # Показываем аватарку новичка, если она есть
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            
        embed.add_field(name="ID аккаунта", value=member.id)
        embed.add_field(name="Дата регистрации", value=member.created_at.strftime("%d.%m.%Y"))
        
        await log_channel.send(embed=embed)


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
