import discord
from discord.ext import commands
import datetime
import os
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
