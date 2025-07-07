import os
import aiohttp
import interactions
import threading
from flask import Flask
from googleapiclient.discovery import build

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Bot is running."

bot = interactions.Client(token=DISCORD_TOKEN)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

async def fetch_popular_roblox_games(min_players=5000):
    url = "https://games.roproxy.com/v1/games/list?sortOrder=Asc&sortType=Popular&limit=20"
    games = []

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for game in data.get("data", []):
                name = game.get("name")
                playing = game.get("playing", 0)
                if name and playing >= min_players:
                    games.append((name, playing))
    return games[:5]

def search_youtube_script(game_name):
    query = f"{game_name} script"
    request = youtube.search().list(
        q=query,
        part="snippet",
        type="video",
        maxResults=1
    )
    response = request.execute()
    results = []
    for item in response.get("items", []):
        title = item["snippet"]["title"]
        video_id = item["id"]["videoId"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        results.append((title, url))
    return results

@interactions.slash_command(name="findscripts", description="Find Roblox games and script videos.")
async def findscripts(ctx: interactions.SlashContext):
    await ctx.send("🔍 Fetching popular Roblox games...")

    games = await fetch_popular_roblox_games()
    if not games:
        await ctx.send("❌ Failed to fetch game list.")
        return

    response = "🎮 **Popular Roblox Games + Script Videos:**\n\n"
    for name, players in games:
        results = search_youtube_script(name)
        if results:
            title, url = results[0]
            response += f"**{name}** ({players} players):\n▶️ [{title}]({url})\n\n"
        else:
            response += f"**{name}** ({players} players):\n⚠️ No script found.\n\n"

    await ctx.send(response)

def start_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    threading.Thread(target=start_flask).start()
    bot.start()
