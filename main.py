import discord
import aiohttp
import os
import threading
from flask import Flask
from googleapiclient.discovery import build

# ====== ENVIRONMENT VARIABLES ======
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
YOUTUBE_MAX_RESULTS = 1
ROBLOX_MIN_PLAYERS = 5000

# ====== FLASK WEB SERVER (REQUIRED FOR RENDER FREE TIER) ======
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Roblox Script Bot is running."

# ====== DISCORD BOT SETUP ======
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# ====== FETCH POPULAR GAMES FROM ROPROXY ======
async def fetch_popular_roblox_games(min_players=ROBLOX_MIN_PLAYERS):
    url = "https://games.roproxy.com/v1/games/list?sortOrder=Asc&sortType=Popular&limit=20"
    games = []

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print("❌ Failed to fetch from RoProxy")
                return games
            data = await resp.json()
            for game in data.get("data", []):
                name = game.get("name")
                playing = game.get("playing", 0)
                if name and playing >= min_players:
                    games.append((name, playing))
    return games[:5]

# ====== SEARCH YOUTUBE FOR SCRIPT VIDEOS ======
def search_youtube_script(game_name):
    query = f"{game_name} script"
    request = youtube.search().list(
        q=query,
        part="snippet",
        type="video",
        maxResults=YOUTUBE_MAX_RESULTS
    )
    response = request.execute()
    results = []
    for item in response.get("items", []):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        results.append((title, url))
    return results

# ====== DISCORD COMMAND ======
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.lower().startswith("!findscripts"):
        await message.channel.send("🔍 Fetching popular Roblox games...")

        games = await fetch_popular_roblox_games()
        if not games:
            await message.channel.send("❌ Could not fetch games. Try again later.")
            return

        result_text = "🎮 **Top Roblox Games with Script Videos:**\n\n"
        for name, players in games:
            yt_results = search_youtube_script(name)
            if yt_results:
                title, url = yt_results[0]
                result_text += f"**{name}** ({players} players):\n▶️ [{title}]({url})\n\n"
            else:
                result_text += f"**{name}** ({players} players):\n⚠️ No video found.\n\n"

        await message.channel.send(result_text)

# ====== RUN BOTH WEB SERVER + DISCORD BOT ======
def run_discord_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    if DISCORD_TOKEN and YOUTUBE_API_KEY:
        threading.Thread(target=run_discord_bot).start()
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    else:
        print("❌ DISCORD_TOKEN or YOUTUBE_API_KEY not set.")
