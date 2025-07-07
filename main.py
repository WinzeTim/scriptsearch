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
import re  # Add this import for regex parsing
import difflib  # For fuzzy matching
from datetime import datetime, timedelta
# Helper for advanced fuzzy matching and scoring
from difflib import SequenceMatcher

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
            for attempt in range(3):  # Retry logic
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            print(f"[Rolimons] HTTP status: {resp.status}")
                            await asyncio.sleep(1)
                            continue
                        html = await resp.text()
                        break
                except Exception as e:
                    print(f"[Rolimons] Attempt {attempt+1} failed: {e}")
                    await asyncio.sleep(1)
            else:
                return [], "Rolimons: Failed after 3 attempts."
    except Exception as e:
        print(f"[Rolimons] Error fetching: {e}")
        return [], f"Error fetching Rolimons: {e}"
    # Parse the JS variable game_details
    match = re.search(r"var game_details = (\{.*?\});", html, re.DOTALL)
    if not match:
        print("[Rolimons] Could not find game_details JS variable.")
        return [], "Could not find game_details on Rolimons. The site structure may have changed."
    try:
        import json
        # The JS object uses double quotes, so it's valid JSON
        game_details = json.loads(match.group(1))
    except Exception as e:
        print(f"[Rolimons] Error parsing game_details: {e}")
        return [], f"Error parsing game_details: {e}"
    games = []
    for game_id, entry in game_details.items():
        try:
            name = entry[0]
            players = entry[3]
            if players >= ROBLOX_MIN_PLAYERS:
                games.append((name, players, game_id))
        except Exception as e:
            print(f"[Rolimons] Error parsing entry: {e}")
            continue
    return games, None

async def fetch_roblox_games_roproxy():
    url = "https://games.roproxy.com/v1/games/list?sortToken=&sortOrder=Asc&limit=20"
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        print(f"[roproxy] HTTP status: {resp.status}")
                        await asyncio.sleep(1)
                        continue
                    data = await resp.json()
                    games = []
                    for g in data.get("data", []):
                        name = g.get("name")
                        players = g.get("playing", 0)
                        game_id = str(g.get("id")) if g.get("id") else None
                        if name and players >= ROBLOX_MIN_PLAYERS and game_id:
                            games.append((name, players, game_id))
                    return games, None
        except Exception as e:
            print(f"[roproxy] Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    return [], "roproxy: Failed after 3 attempts or network error."

async def fetch_roblox_games_discover():
    url = "https://www.roblox.com/discover"
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        print(f"[roblox.com/discover] HTTP status: {resp.status}")
                        await asyncio.sleep(1)
                        continue
                    html = await resp.text()
                    break
        except Exception as e:
            print(f"[roblox.com/discover] Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    else:
        return [], "roblox.com/discover: Failed after 3 attempts."
    soup = BeautifulSoup(html, "html.parser")
    games = []
    for div in soup.find_all("div", class_="game-card-container"):
        name_tag = div.find("span", class_="game-card-name")
        players_tag = div.find("span", class_="game-card-player-count")
        link_tag = div.find("a", href=True)
        if name_tag and players_tag and link_tag:
            name = name_tag.get_text(strip=True)
            players_text = players_tag.get_text(strip=True).replace(",", "")
            href = link_tag["href"]
            # Try to extract game id from URL
            match = re.search(r"/games/(\d+)", href)
            game_id = match.group(1) if match else None
            try:
                players = int(players_text)
                if players >= ROBLOX_MIN_PLAYERS and game_id:
                    games.append((name, players, game_id))
            except ValueError:
                continue
    return games, None

async def fetch_roblox_games_explore_api():
    session_id = str(uuid.uuid4())
    url = f"https://apis.roblox.com/explore-api/v1/get-sorts?sessionId={session_id}&device=computer&country=all"
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        print(f"[explore-api] HTTP status: {resp.status}")
                        await asyncio.sleep(1)
                        continue
                    data = await resp.json()
                    games = []
                    for sort in data.get("sorts", []):
                        for entry in sort.get("entries", []):
                            name = entry.get("name")
                            players = entry.get("playing", 0)
                            game_id = str(entry.get("id")) if entry.get("id") else None
                            if name and players >= ROBLOX_MIN_PLAYERS and game_id:
                                games.append((name, players, game_id))
                    return games, None
        except Exception as e:
            print(f"[explore-api] Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    return [], "explore-api: Failed after 3 attempts or network error."

async def fetch_roblox_games_search_api():
    session_id = str(uuid.uuid4())
    url = f"https://apis.roblox.com/search-api/omni-search?searchQuery=roblox&sessionId={session_id}"
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        print(f"[search-api] HTTP status: {resp.status}")
                        await asyncio.sleep(1)
                        continue
                    data = await resp.json()
                    games = []
                    for g in data.get("games", []):
                        name = g.get("name")
                        players = g.get("playing", 0)
                        game_id = str(g.get("id")) if g.get("id") else None
                        if name and players >= ROBLOX_MIN_PLAYERS and game_id:
                            games.append((name, players, game_id))
                    return games, None
        except Exception as e:
            print(f"[search-api] Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    return [], "search-api: Failed after 3 attempts or network error."

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
            for name, players, game_id in games:
                if name not in seen and (not kw_list or smart_match(name, kw_list)):
                    all_games.append((name, players, game_id))
                    seen.add(name)
        elif error:
            errors.append(f"{label}: {error}")
        if len(all_games) >= max_games:
            break
    if not all_games:
        return None, "\n".join(errors) or "No games found.", sources
    return all_games[:max_games], None, sources

# --- Video Search APIs ---
def smart_video_score(title, desc, tags, search_words, published=None):
    # Score based on keyword match, fuzzy match, recency, and penalize clickbait
    score = 0.0
    text = f"{title} {desc} {tags}".lower()
    # Keyword match
    for word in search_words:
        if word in text:
            score += 1.0
    # Fuzzy match
    for word in search_words:
        for field in [title, desc, tags]:
            score += SequenceMatcher(None, word, field).ratio()
    # Recency bonus (if published date available)
    if published:
        try:
            pub_date = datetime.strptime(published[:10], "%Y-%m-%d")
            if pub_date > datetime.now() - timedelta(days=180):
                score += 1.5  # Bonus for last 6 months
            elif pub_date > datetime.now() - timedelta(days=365):
                score += 0.5  # Bonus for last year
        except Exception:
            pass
    # Penalize clickbait/unwanted words
    for bad in ["scam", "fake", "virus", "robux generator", "free robux"]:
        if bad in text:
            score -= 2.0
    return score

async def search_youtube_script_searchapi(game_name, search_words=None):
    if not SEARCHAPI_IO_KEY:
        return None
    url = "https://www.searchapi.io/api/v1/search"
    # Expanded query variations
    queries = [
        f"{game_name} script",
        f"script for {game_name}",
        f"{game_name} hack script",
        f"{game_name} exploit",
        f"{game_name} pastebin",
        f"{game_name} working script",
        f"{game_name} gui",
        f"{game_name} auto farm",
        f"{game_name} loadstring",
        f"{game_name} op script",
        f"{game_name} injector",
        f"{game_name} undetected script",
        f"{game_name} no key script",
        f"{game_name} 2024 script",
        f"{game_name} latest script"
    ]
    all_results = []
    try:
        async with aiohttp.ClientSession() as session:
            for q in queries:
                params = {
                    "engine": "youtube",
                    "q": q,
                    "api_key": SEARCHAPI_IO_KEY
                }
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    videos = data.get("videos", [])[:15]  # Check top 15
                    for v in videos:
                        title = v.get("title", "").lower()
                        desc = v.get("description", "").lower() if v.get("description") else ""
                        tags = ' '.join(v.get("keywords", [])).lower() if v.get("keywords") else ""
                        published = v.get("published", "")
                        # Must have 'script' in title, desc, or tags
                        if "script" not in title and "script" not in desc and "script" not in tags:
                            continue
                        score = smart_video_score(title, desc, tags, search_words or [], published)
                        all_results.append((score, v.get("title"), v.get("link")))
        if not all_results:
            return None
        all_results.sort(reverse=True)
        # Return the best result
        return (all_results[0][1], all_results[0][2])
    except Exception:
        return None

# Apply similar smart logic to other sources
async def search_youtube_script_serpapi(game_name, search_words=None):
    if not SERPAPI_KEY:
        return None
    url = "https://serpapi.com/search.json"
    queries = [
        f"{game_name} script",
        f"script for {game_name}",
        f"{game_name} hack script",
        f"{game_name} exploit",
        f"{game_name} pastebin",
        f"{game_name} working script",
        f"{game_name} gui",
        f"{game_name} auto farm",
        f"{game_name} loadstring",
        f"{game_name} op script",
        f"{game_name} injector",
        f"{game_name} undetected script",
        f"{game_name} no key script",
        f"{game_name} 2024 script",
        f"{game_name} latest script"
    ]
    all_results = []
    try:
        async with aiohttp.ClientSession() as session:
            for q in queries:
                params = {
                    "engine": "youtube",
                    "search_query": q,
                    "api_key": SERPAPI_KEY
                }
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    videos = data.get("video_results") or data.get("videos") or []
                    for v in videos[:15]:
                        title = v.get("title", "").lower()
                        desc = v.get("description", "").lower() if v.get("description") else ""
                        tags = ''
                        published = v.get("published", "")
                        if "script" not in title and "script" not in desc:
                            continue
                        score = smart_video_score(title, desc, tags, search_words or [], published)
                        all_results.append((score, v.get("title"), v.get("link")))
        if not all_results:
            return None
        all_results.sort(reverse=True)
        return (all_results[0][1], all_results[0][2])
    except Exception:
        return None

async def search_youtube_script_camideo(game_name, search_words=None):
    if not CAMIDEO_KEY:
        return None
    url = "http://api.camideo.com/"
    queries = [
        f"{game_name} script",
        f"script for {game_name}",
        f"{game_name} hack script",
        f"{game_name} exploit",
        f"{game_name} pastebin",
        f"{game_name} working script",
        f"{game_name} gui",
        f"{game_name} auto farm",
        f"{game_name} loadstring",
        f"{game_name} op script",
        f"{game_name} injector",
        f"{game_name} undetected script",
        f"{game_name} no key script",
        f"{game_name} 2024 script",
        f"{game_name} latest script"
    ]
    all_results = []
    try:
        async with aiohttp.ClientSession() as session:
            for q in queries:
                params = {
                    "key": CAMIDEO_KEY,
                    "q": q,
                    "source": "youtube",
                    "page": 1,
                    "response": "json"
                }
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    videos = data.get("Camideo", {}).get("videos", [])
                    for v in videos[:15]:
                        title = v.get("title", "").lower()
                        desc = v.get("description", "").lower() if v.get("description") else ""
                        tags = ''
                        published = v.get("published", "")
                        if "script" not in title and "script" not in desc:
                            continue
                        score = smart_video_score(title, desc, tags, search_words or [], published)
                        all_results.append((score, v.get("title"), v.get("link")))
        if not all_results:
            return None
        all_results.sort(reverse=True)
        return (all_results[0][1], all_results[0][2])
    except Exception:
        return None

async def search_youtube_script_duckduckgo(game_name, search_words=None):
    queries = [
        f"{game_name} script youtube video",
        f"script for {game_name} youtube video",
        f"{game_name} hack script youtube video",
        f"{game_name} exploit youtube video",
        f"{game_name} pastebin youtube video",
        f"{game_name} working script youtube video"
    ]
    all_results = []
    try:
        async with aiohttp.ClientSession() as session:
            for q in queries:
                url = "https://duckduckgo.com/?q=" + q.replace(" ", "+")
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "youtube.com/watch" in href:
                            text = a.get_text(strip=True).lower()
                            if "script" not in text:
                                continue
                            score = smart_video_score(text, '', '', search_words or [])
                            all_results.append((score, a.get_text(strip=True) or href, href))
        if not all_results:
            return None
        all_results.sort(reverse=True)
        return (all_results[0][1], all_results[0][2])
    except Exception:
        return None

async def search_youtube_script_youtube_api(game_name, search_words=None):
    # Placeholder: You can implement YouTube Data API logic here if you want
    return None

async def fallback_web_search(game_name, search_words=None):
    # Try Google and Reddit for script links/videos
    queries = [
        f'site:youtube.com {game_name} script',
        f'site:pastebin.com {game_name} script',
        f'site:reddit.com {game_name} script',
        f'{game_name} script roblox',
        f'{game_name} script v3rmillion',
    ]
    all_results = []
    try:
        async with aiohttp.ClientSession() as session:
            for q in queries:
                # Google search
                google_url = f'https://www.google.com/search?q={q.replace(" ", "+")}'
                headers = {'User-Agent': 'Mozilla/5.0'}
                async with session.get(google_url, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if 'youtube.com/watch' in href or 'pastebin.com/' in href:
                            text = a.get_text(strip=True).lower()
                            if 'script' not in text:
                                continue
                            score = smart_video_score(text, '', '', search_words or [])
                            all_results.append((score, a.get_text(strip=True) or href, href))
                # Reddit search
                reddit_url = f'https://www.reddit.com/search/?q={q.replace(" ", "+")}'
                async with session.get(reddit_url, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if 'youtube.com/watch' in href or 'pastebin.com/' in href:
                            text = a.get_text(strip=True).lower()
                            if 'script' not in text:
                                continue
                            score = smart_video_score(text, '', '', search_words or [])
                            all_results.append((score, a.get_text(strip=True) or href, href))
        if not all_results:
            return None
        all_results.sort(reverse=True)
        return (all_results[0][1], all_results[0][2])
    except Exception:
        return None

async def search_youtube_script_all(game_name, max_videos):
    # Extract search words from game_name (excluding 'script')
    search_words = [w.lower() for w in game_name.replace('script', '').split() if w.strip()]
    results = []
    seen_links = set()
    all_candidates = []
    for func in [
        search_youtube_script_youtube_api,
        search_youtube_script_searchapi,
        search_youtube_script_serpapi,
        search_youtube_script_camideo,
        search_youtube_script_duckduckgo
    ]:
        candidates = []
        for _ in range(max_videos):
            result = await func(game_name + ' script', search_words)
            if result and result[1] not in seen_links:
                candidates.append(result)
                seen_links.add(result[1])
        all_candidates.extend(candidates)
    # If no results, try fallback web search
    if not all_candidates:
        fallback = await fallback_web_search(game_name, search_words)
        if fallback:
            all_candidates.append(fallback)
    return all_candidates[:max_videos]

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
        for idx, (name, players, game_id) in enumerate(games):
            game_url = f"https://www.roblox.com/games/{game_id}"
            field_name = f"{idx+1}. [{name}]({game_url}) ({players} players)"
            embed.add_field(name=field_name, value="Searching...", inline=False)
        await msg.edit(embed=embed)
        for idx, (name, players, game_id) in enumerate(games):
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
