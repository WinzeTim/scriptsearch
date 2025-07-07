import os
import aiohttp
import threading
from flask import Flask
from bs4 import BeautifulSoup
import interactions
from googleapiclient.discovery import build
import asyncio
import uuid
from typing import List

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

async def fetch_popular_roblox_games():
    sources = []
    errors = []
    all_games = []
    seen = set()
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
                if name not in seen:
                    all_games.append((name, players))
                    seen.add(name)
        elif error:
            errors.append(f"{label}: {error}")
        if len(all_games) >= 10:
            break
    if not all_games:
        return None, "\n".join(errors) or "No games found.", sources
    return all_games[:10], None, sources

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

def smart_match(game_name: str, keywords: List[str]) -> bool:
    name = game_name.lower()
    return all(any(kw in word for word in name.split()) or kw in name for kw in keywords)

async def fetch_popular_roblox_games_smart(search: str, max_games: int):
    # Use all sources, combine, deduplicate, and filter by smart keyword match
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

async def search_youtube_script_all(game_name, max_videos):
    # Try all APIs in order, return up to max_videos results
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

# --- Discord Command with Live Progress ---
@interactions.slash_command(
    name="findscripts",
    description="Find Roblox games and YouTube scripts by search phrase."
)
# NOTE: For some versions of interactions.py, you must register options manually for them to show in Discord's UI.
async def findscripts(ctx: interactions.SlashContext):
    search = ctx.kwargs.get("search")
    max_games = ctx.kwargs.get("max_games", 10)
    max_videos = ctx.kwargs.get("max_videos", 1)
    apis = []
    if youtube:
        apis.append("YouTube Data API")
    if SEARCHAPI_IO_KEY:
        apis.append("SearchApi.io")
    if SERPAPI_KEY:
        apis.append("SerpApi")
    if CAMIDEO_KEY:
        apis.append("Camideo")
    apis.append("DuckDuckGo (fallback)")
    api_list = ", ".join(apis)
    embed = interactions.Embed(
        title=f"🔍 Searching for Roblox games with: {search}",
        description=f"**Using search APIs:** {api_list}\n**Max games:** {max_games}\n**Max videos per game:** {max_videos}\n\nPlease wait while I gather data.",
        color=0x00ff99
    )
    msg = await ctx.send(embeds=embed)
    # Use search.split() for keywords
    games, error, sources = await fetch_popular_roblox_games_smart(search, max_games)
    if not games:
        embed.title = "❌ Failed to fetch Roblox games"
        embed.description = f"{error or 'Unknown error.'}"
        await msg.edit(embeds=embed)
        return
    embed.title = f"🎮 Roblox Games Matching: {search}"
    embed.description = f"**Game sources:** {', '.join(sources)}\n**Search APIs:** {api_list}\n**Max games:** {max_games}\n**Max videos per game:** {max_videos}"
    embed.fields = []
    for idx, (name, players) in enumerate(games):
        field_name = f"{idx+1}. {name} ({players} players)"
        embed.add_field(name=field_name, value="Searching...", inline=False)
    await msg.edit(embeds=embed)
    for idx, (name, players) in enumerate(games):
        embed.fields[idx].value = "Searching..."
        await msg.edit(embeds=embed)
        results = await search_youtube_script_all(f"{name} {search} script", max_videos)
        if results:
            value = "\n".join([f"▶️ [{title}]({url})" for title, url in results])
            embed.fields[idx].value = value
        else:
            embed.fields[idx].value = "⚠️ No script video found."
        await msg.edit(embeds=embed)
        await asyncio.sleep(0.5)
    embed.description = f"**Game sources:** {', '.join(sources)}\n**Search APIs:** {api_list}\n**Max games:** {max_games}\n**Max videos per game:** {max_videos}\n\nDone!"
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
