import os
import aiohttp
import threading
from flask import Flask
from bs4 import BeautifulSoup
import interactions
from googleapiclient.discovery import build
import asyncio

# Environment variables from Render
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
SEARCHAPI_IO_KEY = os.environ.get("SEARCHAPI_IO_KEY")  # https://www.searchapi.io/
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")            # https://serpapi.com/
CAMIDEO_KEY = os.environ.get("CAMIDEO_KEY")            # https://camideo.com/
ROBLOX_MIN_PLAYERS = 5000

# Flask web service (to keep Render alive)
app = Flask(__name__)
@app.route("/")
def index():
    return "✅ Bot is running."

# YouTube API setup
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None

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

# --- Video Search APIs ---
async def search_youtube_script_youtube_api(game_name):
    if not youtube:
        return None
    try:
        query = f"{game_name} script"
        request = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=1
        )
        response = request.execute()
        for item in response.get("items", []):
            title = item["snippet"]["title"]
            video_id = item["id"]["videoId"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            return (title, url)
    except Exception:
        return None

async def search_youtube_script_searchapi(game_name):
    if not SEARCHAPI_IO_KEY:
        return None
    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": "youtube",
        "q": f"{game_name} script",
        "api_key": SEARCHAPI_IO_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                videos = data.get("videos", [])
                if videos:
                    v = videos[0]
                    return (v.get("title"), v.get("link"))
    except Exception:
        return None

async def search_youtube_script_serpapi(game_name):
    if not SERPAPI_KEY:
        return None
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "youtube",
        "search_query": f"{game_name} script",
        "api_key": SERPAPI_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                videos = data.get("video_results") or data.get("videos")
                if videos:
                    v = videos[0]
                    return (v.get("title"), v.get("link"))
    except Exception:
        return None

async def search_youtube_script_camideo(game_name):
    if not CAMIDEO_KEY:
        return None
    url = "http://api.camideo.com/"
    params = {
        "key": CAMIDEO_KEY,
        "q": f"{game_name} script",
        "source": "youtube",
        "page": 1,
        "response": "json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                videos = data.get("Camideo", {}).get("videos", [])
                if videos:
                    v = videos[0]
                    return (v.get("title"), v.get("link"))
    except Exception:
        return None

async def search_youtube_script_duckduckgo(game_name):
    # DuckDuckGo video search fallback (scrape, no API key)
    url = "https://duckduckgo.com/?q=" + f"{game_name} script youtube video".replace(" ", "+")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "youtube.com/watch" in href:
                        return (a.get_text(strip=True) or href, href)
    except Exception:
        return None

async def search_youtube_script(game_name):
    # Try all APIs in order, return first result
    for func in [
        search_youtube_script_youtube_api,
        search_youtube_script_searchapi,
        search_youtube_script_serpapi,
        search_youtube_script_camideo,
        search_youtube_script_duckduckgo
    ]:
        result = await func(game_name)
        if result:
            return result
    return None

# --- Discord Command with Live Progress ---
@interactions.slash_command(name="findscripts", description="Find Roblox games and YouTube scripts.")
async def findscripts(ctx: interactions.SlashContext):
    embed = interactions.Embed(
        title="🔍 Fetching popular Roblox games...",
        description="Please wait while I gather data.",
        color=0x00ff99
    )
    msg = await ctx.send(embeds=embed)
    games = await fetch_popular_roblox_games()
    if not games:
        await ctx.send("❌ Failed to fetch game list.")
        return
    embed.title = "🎮 Popular Roblox Games + Script Videos"
    embed.description = ""
    embed.fields = []
    for idx, (name, players) in enumerate(games):
        field_name = f"{idx+1}. {name} ({players} players)"
        embed.add_field(name=field_name, value="Searching...", inline=False)
    await msg.edit(embeds=embed)
    # Now search for each game and update embed live
    for idx, (name, players) in enumerate(games):
        embed.fields[idx].value = "Searching..."
        await msg.edit(embeds=embed)
        result = await search_youtube_script(name)
        if result:
            title, url = result
            embed.fields[idx].value = f"▶️ [{title}]({url})"
        else:
            embed.fields[idx].value = "⚠️ No script video found."
        await msg.edit(embeds=embed)
        await asyncio.sleep(0.5)  # To avoid rate limits
    embed.description = "Done!"
    await msg.edit(embeds=embed)

# Run bot and web server
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN is missing.")
    else:
        threading.Thread(target=run_flask).start()
        bot.start()
