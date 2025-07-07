import os
import aiohttp
import threading
from flask import Flask
from bs4 import BeautifulSoup
import discord
from discord.ext import commands
import asyncio
import uuid
from typing import List

# Environment variables
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
SEARCHAPI_IO_KEY = os.environ.get("SEARCHAPI_IO_KEY")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
CAMIDEO_KEY = os.environ.get("CAMIDEO_KEY")
ROBLOX_MIN_PLAYERS = 5000

# Flask web service (to keep Render alive)
app = Flask(__name__)
@app.route("/")
def index():
    return "✅ Bot is running."

# Discord Bot client
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Roblox Game Search Functions ---
def smart_match(game_name: str, keywords: List[str]) -> bool:
    name = game_name.lower()
    return all(any(kw in word for word in name.split()) or kw in name for kw in keywords)

async def fetch_roblox_games_rolimons():
    url = "https://www.rolimons.com/gametable"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], f"Rolimons returned status {resp.status}"
                html = await resp.text()
    except Exception as e:
        return [], f"Error fetching Rolimons: {e}"
    soup = BeautifulSoup(html, "html.parser")
    games = []
    table = soup.select_one("table#game-table > tbody")
    if not table:
        return [], "Could not find game table on Rolimons. The site structure may have changed."
    for row in table.find_all("tr")[:20]:
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
    return games, None

async def fetch_roblox_games_roproxy():
    url = "https://games.roproxy.com/v1/games/list?sortToken=&sortOrder=Asc&limit=20"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], f"roproxy returned status {resp.status}"
                data = await resp.json()
                games = []
                for g in data.get("data", []):
                    name = g.get("name")
                    players = g.get("playing", 0)
                    if name and players >= ROBLOX_MIN_PLAYERS:
                        games.append((name, players))
                return games, None
    except Exception as e:
        return [], f"Error fetching roproxy: {e}"

async def fetch_roblox_games_discover():
    url = "https://www.roblox.com/discover"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], f"roblox.com/discover returned status {resp.status}"
                html = await resp.text()
    except Exception as e:
        return [], f"Error fetching roblox.com/discover: {e}"
    soup = BeautifulSoup(html, "html.parser")
    games = []
    for div in soup.find_all("div", class_="game-card-container"):
        name_tag = div.find("span", class_="game-card-name")
        players_tag = div.find("span", class_="game-card-player-count")
        if name_tag and players_tag:
            name = name_tag.get_text(strip=True)
            players_text = players_tag.get_text(strip=True).replace(",", "")
            try:
                players = int(players_text)
                if players >= ROBLOX_MIN_PLAYERS:
                    games.append((name, players))
            except ValueError:
                continue
    return games, None

async def fetch_roblox_games_explore_api():
    session_id = str(uuid.uuid4())
    url = f"https://apis.roblox.com/explore-api/v1/get-sorts?sessionId={session_id}&device=computer&country=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], f"explore-api returned status {resp.status}"
                data = await resp.json()
                games = []
                for sort in data.get("sorts", []):
                    for entry in sort.get("entries", []):
                        name = entry.get("name")
                        players = entry.get("playing", 0)
                        if name and players >= ROBLOX_MIN_PLAYERS:
                            games.append((name, players))
                return games, None
    except Exception as e:
        return [], f"Error fetching explore-api: {e}"

async def fetch_roblox_games_search_api():
    session_id = str(uuid.uuid4())
    url = f"https://apis.roblox.com/search-api/omni-search?searchQuery=roblox&sessionId={session_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], f"search-api returned status {resp.status}"
                data = await resp.json()
                games = []
                for g in data.get("games", []):
                    name = g.get("name")
                    players = g.get("playing", 0)
                    if name and players >= ROBLOX_MIN_PLAYERS:
                        games.append((name, players))
                return games, None
    except Exception as e:
        return [], f"Error fetching search-api: {e}"

async def fetch_popular_roblox_games_smart(search: str, max_games: int):
    sources = []
    errors = []
    all_games = []
    seen = set()
    kw_list = [k.lower() for k in search.split() if k.strip()]
    for fetcher, label in [
        (fetch_roblox_games_rolimons, "Rolimons"),
        (fetch_roblox_games_roproxy, "roproxy"),
        (fetch_roblox_games_discover, "Roblox Discover"),
        (fetch_roblox_games_explore_api, "Explore API"),
        (fetch_roblox_games_search_api, "Search API")
    ]:
        games, error = await fetcher()
        if games:
            sources.append(label)
            for name, players in games:
                if name not in seen and (not kw_list or smart_match(name, kw_list)):
                    all_games.append((name, players))
                    seen.add(name)
        elif error:
            errors.append(f"{label}: {error}")
        if len(all_games) >= max_games:
            break
    if not all_games:
        return None, "\n".join(errors) or "No games found.", sources
    return all_games[:max_games], None, sources

# --- Video Search APIs ---
async def search_youtube_script_youtube_api(game_name):
    # Placeholder: You can implement YouTube Data API logic here if you want
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

async def search_youtube_script_all(game_name, max_videos):
    results = []
    for func in [
        search_youtube_script_youtube_api,
        search_youtube_script_searchapi,
        search_youtube_script_serpapi,
        search_youtube_script_camideo,
        search_youtube_script_duckduckgo
    ]:
        if len(results) >= max_videos:
            break
        result = await func(game_name)
        if result and result not in results:
            results.append(result)
    return results

# --- Hybrid Command for Discord.py ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.hybrid_command(name="findscripts", description="Find Roblox games and YouTube scripts by search phrase. v2")
async def findscripts(ctx, *, search: str, max_games: int = 10, max_videos: int = 1):
    """
    Usage: /findscripts <search> [max_games] [max_videos]
    """
    try:
        if not search:
            await ctx.send("❌ You must provide a search phrase. Example: /findscripts Grow a garden", ephemeral=True)
            return
        apis = []
        if SEARCHAPI_IO_KEY:
            apis.append("SearchApi.io")
        if SERPAPI_KEY:
            apis.append("SerpApi")
        if CAMIDEO_KEY:
            apis.append("Camideo")
        apis.append("DuckDuckGo (fallback)")
        api_list = ", ".join(apis)
        embed = discord.Embed(
            title=f"🔍 Searching for Roblox games with: {search}",
            description=f"**Using search APIs:** {api_list}\n**Max games:** {max_games}\n**Max videos per game:** {max_videos}\n\nPlease wait while I gather data.",
            color=0x00ff99
        )
        msg = await ctx.send(embed=embed)
        games, error, sources = await fetch_popular_roblox_games_smart(search, max_games)
        if not games:
            embed.title = "❌ Failed to fetch Roblox games"
            embed.description = f"{error or 'Unknown error.'}"
            await msg.edit(embed=embed)
            return
        embed.title = f"🎮 Roblox Games Matching: {search}"
        embed.description = f"**Game sources:** {', '.join(sources)}\n**Search APIs:** {api_list}\n**Max games:** {max_games}\n**Max videos per game:** {max_videos}"
        embed.clear_fields()
        for idx, (name, players) in enumerate(games):
            field_name = f"{idx+1}. {name} ({players} players)"
            embed.add_field(name=field_name, value="Searching...", inline=False)
        await msg.edit(embed=embed)
        for idx, (name, players) in enumerate(games):
            embed.set_field_at(idx, name=embed.fields[idx].name, value="Searching...", inline=False)
            await msg.edit(embed=embed)
            results = await search_youtube_script_all(f"{name} {search} script", max_videos)
            if results:
                value = "\n".join([f"▶️ [{title}]({url})" for title, url in results])
                embed.set_field_at(idx, name=embed.fields[idx].name, value=value, inline=False)
            else:
                embed.set_field_at(idx, name=embed.fields[idx].name, value="⚠️ No script video found.", inline=False)
            await msg.edit(embed=embed)
            await asyncio.sleep(0.5)
        embed.description = f"**Game sources:** {', '.join(sources)}\n**Search APIs:** {api_list}\n**Max games:** {max_games}\n**Max videos per game:** {max_videos}\n\nDone!"
        await msg.edit(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}", ephemeral=True)
        import traceback
        print(traceback.format_exc())

# Run bot and web server

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN is missing.")
    else:
        threading.Thread(target=run_flask).start()
        bot.run(DISCORD_TOKEN)
