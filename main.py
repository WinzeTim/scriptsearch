import os
import discord
import aiohttp
import threading
from flask import Flask
from googleapiclient.discovery import build

# Environment variables (set in Render dashboard)
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
YOUTUBE_MAX_RESULTS = 1
ROBLOX_MIN_PLAYERS = 5000

# Flask web server (keeps Render web service alive)
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Roblox Script Bot is alive."

# Discord client setup (no audio/voice)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# YouTube API setup
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# Fetch popular Roblox games from RoProxy
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

# Search YouTube for "<game name> script"
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

# Discord events
@client.event
async def on_ready():
    print(f"🤖 Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.lower().startswith("!findscripts"):
        await message.channel.send("🔍 Finding popular Roblox games...")

        games = await fetch_popular_roblox_games()
        if not games:
            await message.channel.send("❌ Couldn't fetch game data.")
            return

        response = "🎮 **Popular Roblox Games + Script Videos:**\n\n"
        for name, players in games:
            yt_results = search_youtube_script(name)
            if yt_results:
                title, url = yt_results[0]
                response += f"**{name}** ({players} players):\n▶️ [{title}]({url})\n\n"
            else:
                response += f"**{name}** ({players} players):\n⚠️ No script video found.\n\n"

        await message.channel.send(response)

# Run both Flask and Discord client
def run_discord():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    if not DISCORD_TOKEN or not YOUTUBE_API_KEY:
        print("❌ Environment variables not set.")
    else:
        threading.Thread(target=run_discord).start()
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
