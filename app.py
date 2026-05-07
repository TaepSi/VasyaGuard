import discord
from discord.ext import commands
import datetime
import os
import aiosqlite
from flask import Flask
from threading import Thread

# --- БЛОК ОЖИВЛЯЛКИ (ОБЯЗАТЕЛЬНО ДЛЯ ХОСТИНГА) ---
app = Flask('')
@app.route('/')
def home(): return "VasyaGuard is online!"

def run_web():
    app.run(host='0.0.0.0', port=8080) # Koyeb любит 8080 или 8000

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- НАСТРОЙКИ БОТА ---
# На хостинге токен будет браться из секретов (Environment Variables)
TOKEN = os.getenv("DISCORD_TOKEN")

# Список матов
BAD_WORDS = ['хер', 'сука', 'бля', 'блять', 'пидор', 'гандон']

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} заступил на дежурство!')

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("stats.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, msg_count INTEGER DEFAULT 0)")
        await db.commit()

# --- ТИКЕТЫ (КНОПКИ) ---
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Открыть тикет", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        # Проверка, нет ли уже открытого тикета
        existing_channel = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
        if existing_channel:
            return await interaction.response.send_message(f"У тебя уже есть открытый тикет: {existing_channel.mention}", ephemeral=True)

        # Настройка прав: юзер видит, остальные (кроме админов) - нет
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await guild.create_text_channel(f"ticket-{user.name}", overwrites=overwrites)
        await interaction.response.send_message(f"Тикет создан: {channel.mention}", ephemeral=True)
        await channel.send(f"Привет {user.mention}! Опиши свою проблему. Админы скоро подойдут.")

# --- СОБЫТИЯ ---
@bot.event
async def on_ready():
    await init_db()
    bot.add_view(TicketView()) # Чтобы кнопки работали после перезагрузки
    print(f'🤖 {bot.user} заступил на дежурство!')

@bot.event
async def on_message(message):
    if message.author.bot: return

    # Запись статистики
    async with aiosqlite.connect("stats.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, msg_count) VALUES (?, 0)", (message.author.id,))
        await db.execute("UPDATE users SET msg_count = msg_count + 1 WHERE user_id = ?", (message.author.id,))
        await db.commit()

    # Фильтры (ссылки/мат)
    content = message.content.lower()
    if ("http" in content or any(w in content for w in BAD_WORDS)) and not message.author.guild_permissions.administrator:
        await message.delete()
        return

    await bot.process_commands(message)

# --- КОМАНДЫ ---
@bot.command()
async def top(ctx):
    async with aiosqlite.connect("stats.db") as db:
        async with db.execute("SELECT user_id, msg_count FROM users ORDER BY msg_count DESC LIMIT 10") as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        return await ctx.send("Статистика пока пуста.")

    embed = discord.Embed(title="🏆 Топ активных участников", color=discord.Color.gold())
    for i, (user_id, count) in enumerate(rows, 1):
        user = bot.get_user(user_id)
        name = user.name if user else f"ID: {user_id}"
        embed.add_field(name=f"{i}. {name}", value=f"Сообщений: {count}", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_tickets(ctx):
    embed = discord.Embed(title="Поддержка", description="Нажми на кнопку ниже, чтобы создать приватный канал для связи с администрацией.")
    await ctx.send(embed=embed, view=TicketView())


# Команды
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Понг! {round(bot.latency * 1000)}мс")

@bot.command()
@commands.has_permissions(administrator=True)
async def clear(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Удалено {amount} сообщений.", delete_after=5)

# Защита от мата и ссылок
@bot.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.lower()
    is_admin = message.author.guild_permissions.administrator

    if ("http" in content or any(w in content for w in BAD_WORDS)) and not is_admin:
        await message.delete()
        await message.channel.send(f"🚫 {message.author.mention}, тут такое нельзя!", delete_after=5)
        return
    await bot.process_commands(message)

# Логи (Убедись, что на сервере есть канал 'logs')
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    log_channel = discord.utils.get(message.guild.text_channels, name='logs')
    if log_channel:
        embed = discord.Embed(title="🗑 Удалено", color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.UTC))
        embed.add_field(name="Автор", value=message.author.mention)
        embed.add_field(name="Текст", value=message.content or "Файл", inline=False)
        await log_channel.send(embed=embed)

# --- ЗАПУСК ---
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
