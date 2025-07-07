import os
import aiohttp
import threading
from flask import Flask
from bs4 import BeautifulSoup
import interactions
from googleapiclient.discovery import build

# Environment variables from Render
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
ROBLOX_MIN_PLAYERS = 5000

# Flask web service (to keep Render alive)
app = Flask(__name__)
@app.route("/")
def index():
    return "✅ Bot is running."

# YouTube API setup
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# Discord Bot client
bot = interactions.Client(token=DISCORD_TOKEN)

# Scrape Rolimons Game Table for popular games
async def fetch_popular_roblox_games():
    url = "https://www.rolimons.com/gametable"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []

            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")
    games = []

    for row in soup.select("table#game-table > tbody > tr")[:10]:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        name = cols[1].get_text(strip=True)
        players_text = cols[2].get_text(strip=True).replace(",", "")
        try:
            players = int(players_text)
            if players >= ROBLOX_MIN_PLAYERS:
                games.append((name, players))
        except ValueError:
            continue

    return games

# Search YouTube for "<game name> script"
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

# Slash command for /findscripts
@interactions.slash_command(name="findscripts", description="Find Roblox games and YouTube scripts.")
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
            response += f"**{name}** ({players} players):\n⚠️ No script video found.\n\n"

    await ctx.send(response)

# Run bot and web server
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    if not DISCORD_TOKEN or not YOUTUBE_API_KEY:
        print("❌ DISCORD_TOKEN or YOUTUBE_API_KEY is missing.")
    else:
        threading.Thread(target=run_flask).start()
        bot.start()
