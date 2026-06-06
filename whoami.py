#!/usr/bin/env python3

import sys
import json
import time
import hashlib
import argparse
import textwrap
from datetime import datetime, timezone
from collections import Counter

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests")
    sys.exit(1)

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai as openai_sdk
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from google import genai as google_genai
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.markdown import Markdown
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

HEADERS = {
    "User-Agent": "OSINT-Profiler/1.0 (self-research tool)"
}

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"

LLM_PROVIDERS = {
    "anthropic":   {"env_key": "ANTHROPIC_API_KEY",  "default_model": "claude-sonnet-4-20250514"},
    "openai":      {"env_key": "OPENAI_API_KEY",      "default_model": "gpt-4o"},
    "google":      {"env_key": "GOOGLE_API_KEY",      "default_model": "gemini-2.0-flash"},
    "groq":        {"env_key": "GROQ_API_KEY",        "default_model": "llama-3.3-70b-versatile", "base_url": "https://api.groq.com/openai/v1"},
    "lumo":        {"env_key": "LUMO_API_KEY",        "default_model": "lumo", "base_url": "https://lumo.proton.me/api/ai/v1"},
    "openrouter":  {"env_key": "OPENROUTER_API_KEY",  "default_model": "deepseek/deepseek-chat", "base_url": "https://openrouter.ai/api/v1"},
    "ollama":      {"env_key": None,                  "default_model": "llama3.2", "base_url": "http://localhost:11434"},
}


_console = None
_use_rich = False

def _get_console():
    global _console
    if _console is None:
        _console = Console(highlight=False) if HAS_RICH else None
    return _console

def enable_rich():
    global _use_rich
    _use_rich = HAS_RICH

def banner():
    if _use_rich:
        c = _get_console()
        c.print(Panel.fit(
            "[bold cyan]██╗    ██╗██╗  ██╗ ██████╗  █████╗ ███╗   ███╗██╗\n"
            "██║    ██║██║  ██║██╔═══██╗██╔══██╗████╗ ████║██║\n"
            "██║ █╗ ██║███████║██║   ██║███████║██╔████╔██║██║\n"
            "██║███╗██║██╔══██║██║   ██║██╔══██║██║╚██╔╝██║██║\n"
            "╚███╔███╔╝██║  ██║╚██████╔╝██║  ██║██║ ╚═╝ ██║██║\n"
            " ╚══╝╚══╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝",
            subtitle="[dim]Public Profile Aggregator + AI Profiler[/dim]",
            border_style="cyan",
        ))
    else:
        print(f"\n{CYAN}{BOLD}"
              "██╗    ██╗██╗  ██╗ ██████╗  █████╗ ███╗   ███╗██╗\n"
              "██║    ██║██║  ██║██╔═══██╗██╔══██╗████╗ ████║██║\n"
              "██║ █╗ ██║███████║██║   ██║███████║██╔████╔██║██║\n"
              "██║███╗██║██╔══██║██║   ██║██╔══██║██║╚██╔╝██║██║\n"
              "╚███╔███╔╝██║  ██║╚██████╔╝██║  ██║██║ ╚═╝ ██║██║\n"
              " ╚══╝╚══╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝"
              f"{RESET}\n{DIM}  Public Profile Aggregator + AI Profiler{RESET}\n")

def section(title):
    if _use_rich:
        c = _get_console()
        c.rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")
    else:
        print(f"\n{CYAN}{BOLD}{'─'*50}{RESET}")
        print(f"{CYAN}{BOLD}  {title}{RESET}")
        print(f"{CYAN}{BOLD}{'─'*50}{RESET}")

def ok(msg):
    if _use_rich:
        _get_console().print(f"  [bold green]✓[/bold green] {msg}")
    else:
        print(f"  {GREEN}✓{RESET} {msg}")

def warn(msg):
    if _use_rich:
        _get_console().print(f"  [bold yellow]⚠[/bold yellow] {msg}")
    else:
        print(f"  {YELLOW}⚠{RESET} {msg}")

def fail(msg):
    if _use_rich:
        _get_console().print(f"  [bold red]✗[/bold red] {msg}")
    else:
        print(f"  {RED}✗{RESET} {msg}")

def info(msg):
    if _use_rich:
        _get_console().print(f"  [dim]{msg}[/dim]")
    else:
        print(f"  {DIM}{msg}{RESET}")


def safe_get(url, params=None, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


def _reddit_auth(client_id=None, client_secret=None):
    """Get Reddit OAuth token using script app credentials."""
    from os import environ
    cid = client_id or environ.get("REDDIT_CLIENT_ID", "")
    cs = client_secret or environ.get("REDDIT_CLIENT_SECRET", "")
    if not cid or not cs:
        return None
    try:
        r = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(cid, cs),
            headers={"User-Agent": "OSINT-Profiler/1.0"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:
        pass
    return None


def _reddit_get(url, token=None, params=None, timeout=10):
    """Make authenticated Reddit API request."""
    headers = {"User-Agent": "OSINT-Profiler/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        if r.status_code == 200:
            return r
        return None
    except Exception:
        return None


def fetch_reddit(username, client_id=None, client_secret=None):
    data = {}
    section(f"Reddit — u/{username}")

    token = _reddit_auth(client_id, client_secret)

    r = _reddit_get(f"https://oauth.reddit.com/user/{username}/about.json", token=token) if token \
        else safe_get(f"https://www.reddit.com/user/{username}/about.json")

    if not r:
        if not token:
            fail("Reddit now requires OAuth. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars.")
        else:
            fail("Profile not found or private")
        return data

    about = r.json().get("data", {})
    data["platform"] = "reddit"
    data["username"] = username
    data["url"] = f"https://reddit.com/u/{username}"
    data["karma_post"] = about.get("link_karma", 0)
    data["karma_comment"] = about.get("comment_karma", 0)
    data["account_age_days"] = int((time.time() - about.get("created_utc", time.time())) / 86400)
    data["is_verified"] = about.get("verified", False)
    data["has_premium"] = about.get("is_gold", False)

    ok(f"Karma: {data['karma_post']} post / {data['karma_comment']} comment")
    ok(f"Account age: {data['account_age_days']} days")

    api_base = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    posts_r = _reddit_get(f"{api_base}/user/{username}/submitted.json", token=token, params={"limit": 100})
    comments_r = _reddit_get(f"{api_base}/user/{username}/comments.json", token=token, params={"limit": 100})

    subreddits = []
    post_titles = []
    comment_bodies = []
    post_hours = []
    post_scores = []

    if posts_r:
        for item in posts_r.json().get("data", {}).get("children", []):
            d = item.get("data", {})
            subreddits.append(d.get("subreddit", ""))
            post_titles.append(d.get("title", ""))
            post_scores.append(d.get("score", 0))
            ts = d.get("created_utc", 0)
            if ts:
                post_hours.append(datetime.fromtimestamp(ts, tz=timezone.utc).hour)

    if comments_r:
        for item in comments_r.json().get("data", {}).get("children", []):
            d = item.get("data", {})
            subreddits.append(d.get("subreddit", ""))
            comment_bodies.append(d.get("body", "")[:300])
            ts = d.get("created_utc", 0)
            if ts:
                post_hours.append(datetime.fromtimestamp(ts, tz=timezone.utc).hour)

    top_subs = Counter(subreddits).most_common(10)
    data["top_subreddits"] = [s for s, _ in top_subs]
    data["post_titles"] = post_titles[:20]
    data["comment_samples"] = comment_bodies[:15]
    data["activity_hours"] = post_hours
    data["avg_post_score"] = round(sum(post_scores) / len(post_scores), 1) if post_scores else 0

    ok(f"Top subreddits: {', '.join(data['top_subreddits'][:5])}")
    ok(f"Posts fetched: {len(post_titles)} | Comments: {len(comment_bodies)}")
    return data


def fetch_github(username):
    data = {}
    section(f"GitHub — {username}")

    r = safe_get(f"https://api.github.com/users/{username}")
    if not r:
        fail("User not found")
        return data

    u = r.json()
    data["platform"] = "github"
    data["username"] = username
    data["url"] = f"https://github.com/{username}"
    data["name"] = u.get("name", "")
    data["bio"] = u.get("bio", "")
    data["location"] = u.get("location", "")
    data["company"] = u.get("company", "")
    data["blog"] = u.get("blog", "")
    data["followers"] = u.get("followers", 0)
    data["following"] = u.get("following", 0)
    data["public_repos"] = u.get("public_repos", 0)
    data["public_gists"] = u.get("public_gists", 0)
    data["account_age_days"] = int((datetime.now(timezone.utc) - datetime.fromisoformat(u.get("created_at","2000-01-01T00:00:00Z").replace("Z","+00:00"))).days)
    data["hireable"] = u.get("hireable", False)
    data["twitter_username"] = u.get("twitter_username", "")

    ok(f"Name: {data['name'] or 'N/A'} | Location: {data['location'] or 'N/A'}")
    ok(f"Followers: {data['followers']} | Repos: {data['public_repos']}")

    repos_r = safe_get(f"https://api.github.com/users/{username}/repos", params={"per_page": 100, "sort": "updated"})
    languages = []
    topics_all = []
    repo_names = []
    stars = []

    if repos_r:
        for repo in repos_r.json():
            if repo.get("fork"):
                continue
            if repo.get("language"):
                languages.append(repo["language"])
            topics_all.extend(repo.get("topics", []))
            repo_names.append(repo.get("name", ""))
            stars.append(repo.get("stargazers_count", 0))

    data["top_languages"] = [l for l, _ in Counter(languages).most_common(8)]
    data["top_topics"] = [t for t, _ in Counter(topics_all).most_common(10)]
    data["top_repos"] = sorted(zip(repo_names, stars), key=lambda x: -x[1])[:10]
    data["total_stars"] = sum(stars)

    ok(f"Languages: {', '.join(data['top_languages'][:5])}")
    ok(f"Total stars: {data['total_stars']}")
    return data


def fetch_hackernews(username):
    data = {}
    section(f"Hacker News — {username}")

    r = safe_get(f"https://hacker-news.firebaseio.com/v0/user/{username}.json")
    if not r or not r.json():
        fail("User not found")
        return data

    u = r.json()
    data["platform"] = "hackernews"
    data["username"] = username
    data["url"] = f"https://news.ycombinator.com/user?id={username}"
    data["karma"] = u.get("karma", 0)
    data["about"] = u.get("about", "")
    data["account_age_days"] = int((time.time() - u.get("created", time.time())) / 86400)
    item_ids = u.get("submitted", [])[:50]
    data["submission_count"] = len(u.get("submitted", []))

    ok(f"Karma: {data['karma']} | Submissions: {data['submission_count']}")

    titles = []
    urls = []
    comment_texts = []
    for item_id in item_ids[:30]:
        ir = safe_get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
        if ir:
            item = ir.json()
            if item and item.get("type") == "story":
                if item.get("title"):
                    titles.append(item["title"])
                if item.get("url"):
                    urls.append(item["url"])
            elif item and item.get("type") == "comment":
                if item.get("text"):
                    comment_texts.append(item["text"][:300])

    data["story_titles"] = titles[:15]
    data["comment_samples"] = comment_texts[:10]
    ok(f"Stories fetched: {len(titles)} | Comments: {len(comment_texts)}")
    return data


def fetch_bluesky(handle):
    data = {}
    section(f"Bluesky — {handle}")

    r = safe_get("https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle", params={"handle": handle})
    if not r:
        fail("Handle not found")
        return data

    did = r.json().get("did", "")
    if not did:
        fail("Could not resolve DID")
        return data

    prof_r = safe_get("https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile", params={"actor": did})
    if not prof_r:
        fail("Profile fetch failed")
        return data

    p = prof_r.json()
    data["platform"] = "bluesky"
    data["handle"] = handle
    data["did"] = did
    data["url"] = f"https://bsky.app/profile/{handle}"
    data["display_name"] = p.get("displayName", "")
    data["description"] = p.get("description", "")
    data["followers"] = p.get("followersCount", 0)
    data["following"] = p.get("followsCount", 0)
    data["posts_count"] = p.get("postsCount", 0)

    ok(f"Name: {data['display_name'] or 'N/A'}")
    ok(f"Followers: {data['followers']} | Posts: {data['posts_count']}")

    feed_r = safe_get("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed", params={"actor": did, "limit": 50})
    post_texts = []
    hours = []
    if feed_r:
        for item in feed_r.json().get("feed", []):
            post = item.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "")
            if text:
                post_texts.append(text[:300])
            created = record.get("createdAt", "")
            if created:
                try:
                    hours.append(datetime.fromisoformat(created.replace("Z","+00:00")).hour)
                except Exception:
                    pass

    data["post_samples"] = post_texts[:20]
    data["activity_hours"] = hours
    ok(f"Posts fetched: {len(post_texts)}")
    return data


def fetch_mastodon(username, instance="mastodon.social"):
    data = {}
    section(f"Mastodon — {username}@{instance}")

    r = safe_get(f"https://{instance}/api/v1/accounts/lookup", params={"acct": username})
    if not r:
        fail(f"User not found on {instance}")
        return data

    u = r.json()
    account_id = u.get("id", "")
    data["platform"] = "mastodon"
    data["username"] = username
    data["instance"] = instance
    data["url"] = u.get("url", "")
    data["display_name"] = u.get("display_name", "")
    data["note"] = u.get("note", "")
    data["followers"] = u.get("followers_count", 0)
    data["following"] = u.get("following_count", 0)
    data["statuses_count"] = u.get("statuses_count", 0)
    data["created_at"] = u.get("created_at", "")

    fields = u.get("fields", [])
    data["fields"] = {f["name"]: f["value"] for f in fields}

    ok(f"Name: {data['display_name'] or 'N/A'}")
    ok(f"Followers: {data['followers']} | Toots: {data['statuses_count']}")

    if account_id:
        toots_r = safe_get(f"https://{instance}/api/v1/accounts/{account_id}/statuses", params={"limit": 40, "exclude_replies": "true"})
        toot_texts = []
        hours = []
        if toots_r:
            for toot in toots_r.json():
                content = toot.get("content", "")
                if content:
                    clean = content.replace("<p>","").replace("</p>"," ").replace("<br />","\n")
                    toot_texts.append(clean[:300])
                created = toot.get("created_at","")
                if created:
                    try:
                        hours.append(datetime.fromisoformat(created.replace("Z","+00:00")).hour)
                    except Exception:
                        pass
        data["toot_samples"] = toot_texts[:15]
        data["activity_hours"] = hours
        ok(f"Toots fetched: {len(toot_texts)}")
    return data


def fetch_gravatar(email):
    data = {}
    section(f"Gravatar — {email}")

    email_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
    r = safe_get(f"https://www.gravatar.com/{email_hash}.json")
    if not r:
        fail("No Gravatar profile found")
        return data

    try:
        entry = r.json().get("entry", [{}])[0]
    except Exception:
        fail("Could not parse Gravatar response")
        return data

    data["platform"] = "gravatar"
    data["email"] = email
    data["url"] = f"https://gravatar.com/{email_hash}"
    data["display_name"] = entry.get("displayName", "")
    data["about_me"] = entry.get("aboutMe", "")
    data["location"] = entry.get("currentLocation", "")
    data["job_title"] = entry.get("currentJobTitle", "")
    data["company"] = entry.get("company", "")

    urls = entry.get("urls", [])
    data["linked_urls"] = [u.get("value","") for u in urls]

    accounts = entry.get("accounts", [])
    data["linked_accounts"] = [a.get("shortname","") for a in accounts]

    ok(f"Name: {data['display_name'] or 'N/A'}")
    ok(f"Location: {data['location'] or 'N/A'}")
    if data["linked_accounts"]:
        ok(f"Linked: {', '.join(data['linked_accounts'])}")
    return data


def fetch_intelx(query, api_key=None, user_email=None):
    """Search Intelligence X for a query. Returns list of result dicts."""
    from os import environ
    data_list = []
    section(f"IntelX — {query}")

    key = api_key or environ.get("INTELX_API_KEY", "")
    user = user_email or environ.get("INTELX_USER", "")
    if not key or not user:
        fail("IntelX: set INTELX_API_KEY and INTELX_USER env vars")
        return data_list

    search_url = "https://free.intelx.io/intelligent/search"
    result_url = "https://free.intelx.io/intelligent/search/result"

    headers = {
        "User-Agent": "OSINT-Profiler/1.0",
        "x-key": key,
        "x-user": user,
        "Accept": "application/json",
    }

    body = {
        "term": query,
        "buckets": ["darknet.tor", "darknet.i2p", "pastes", "leaks.public.general", "dumpster", "leaks.private"],
        "lookuplevel": 0,
        "maxresults": 50,
        "timeout": 20,
        "sort": 2,
        "media": 0,
    }

    try:
        r = requests.post(search_url, json=body, headers=headers, timeout=25)
    except Exception as e:
        fail(f"IntelX search failed: {e}")
        return data_list

    if r.status_code == 401:
        fail("IntelX: invalid API key or user")
        return data_list
    if r.status_code == 402:
        fail("IntelX: no credits available")
        return data_list
    if r.status_code != 200:
        fail(f"IntelX: HTTP {r.status_code}")
        return data_list

    search_id = r.json().get("id") or r.json().get("uuid") or ""
    if not search_id:
        fail("IntelX: no search ID returned")
        return data_list

    info("Search submitted, polling for results...")
    for attempt in range(40):
        try:
            pr = requests.get(result_url, params={"id": search_id, "limit": 50, "offset": 0}, headers=headers, timeout=10)
            if pr.status_code == 204:
                time.sleep(1.5)
                continue
            if pr.status_code != 200:
                time.sleep(1.5)
                continue

            data = pr.json()
            status = str(data.get("status") or "").lower()
            records = data.get("records") or data.get("selectors") or []

            if status in ("query_complete", "no_results"):
                seen = set()
                for rec in records:
                    name = (rec.get("name") or rec.get("selector") or "").strip()
                    system_id = (rec.get("systemid") or "").strip()
                    dedup = system_id or name
                    if not dedup or dedup in seen:
                        continue
                    seen.add(dedup)
                    bucket = (rec.get("bucket") or "").strip()
                    date_str = (rec.get("date") or rec.get("added") or "").strip()
                    data_list.append({
                        "platform": "intelx",
                        "source": f"IntelX/{bucket}",
                        "title": f"IntelX — {bucket}: {name[:80]}",
                        "url": name,
                        "bucket": bucket,
                        "date": date_str,
                        "system_id": system_id,
                    })
                ok(f"IntelX: {len(data_list)} results")
                return data_list

            time.sleep(1.5)
        except Exception as e:
            warn(f"IntelX poll attempt {attempt + 1}: {e}")
            time.sleep(1.5)

    fail("IntelX: poll exhausted")
    return data_list


def fetch_ahmia(query):
    """Search Ahmia (Tor clearnet proxy). Returns list of result dicts."""
    data_list = []
    section(f"Dark Web (Ahmia) — {query}")

    try:
        r = requests.get("https://ahmia.fi/search/json/", params={"q": query}, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            results = r.json().get("results", [])
            for res in results:
                data_list.append({
                    "platform": "darkweb",
                    "source": "Ahmia",
                    "title": res.get("title", ""),
                    "url": res.get("link", ""),
                    "snippet": res.get("snippet", ""),
                })
            if data_list:
                ok(f"Ahmia: {len(data_list)} results")
            else:
                warn("Ahmia: no results")
            return data_list
    except Exception as e:
        warn(f"Ahmia JSON endpoint failed: {e}")

    try:
        from bs4 import BeautifulSoup
        r = requests.get("https://ahmia.fi/search/", params={"q": query}, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for result in soup.select("li.result"):
                link_el = result.select_one("a[href]")
                title_el = result.select_one("h4")
                snippet_el = result.select_one("p")
                if link_el:
                    data_list.append({
                        "platform": "darkweb",
                        "source": "Ahmia",
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "url": link_el.get("href", ""),
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })
            if data_list:
                ok(f"Ahmia: {len(data_list)} results (HTML parse)")
            else:
                warn("Ahmia: no results")
            return data_list
    except ImportError:
        warn("Ahmia HTML fallback needs: pip install beautifulsoup4")
    except Exception as e:
        warn(f"Ahmia HTML parse failed: {e}")

    warn("Ahmia search unavailable")
    return data_list


def fetch_telegram(username):
    data = {}
    section(f"Telegram — {username}")
    try:
        r = safe_get(f"https://t.me/{username}")
        if not r:
            fail("Telegram: no response")
            return data
        html = r.text
        from html import unescape
        import re

        # Non-existent user check: Telegram returns a page with generic "Telegram" title
        # Real profile pages have the username in the canonical URL or a profile photo
        not_found = bool(re.search(r'can\'t be reached|This username does not exist|Sorry, this user',
                                   html, re.I))
        is_generic = "og:title" in html and not bool(re.search(
            rf'/(?:@)?{re.escape(username)}', html, re.I))
        if not_found or is_generic:
            fail("Telegram: profile not found")
            return data

        name_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if name_m:
            data["display_name"] = unescape(name_m.group(1))
        bio_m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        if bio_m:
            data["bio"] = unescape(bio_m.group(1))
        photo_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if photo_m:
            data["photo_url"] = photo_m.group(1)
        member_m = re.search(r'(\d[\d\s]*) members?', html, re.I)
        if member_m:
            data["member_count"] = member_m.group(1).strip()
        if name_m or bio_m:
            data["platform"] = "telegram"
            data["username"] = username
            data["url"] = f"https://t.me/{username}"
            ok(f"Name: {data.get('display_name', 'unknown')}")
            return data
        fail("Telegram: profile not found")
    except Exception as e:
        fail(f"Telegram: {e}")
    return data


def fetch_youtube(username, api_key=None):
    data = {}
    section(f"YouTube — {username}")
    from os import environ
    key = api_key or environ.get("YOUTUBE_API_KEY", "")
    if key:
        try:
            r = safe_get("https://www.googleapis.com/youtube/v3/channels",
                         params={"part": "snippet,statistics",
                                 "forHandle": f"@{username}",
                                 "key": key})
            if r and r.json().get("items"):
                c = r.json()["items"][0]
                s = c.get("snippet", {})
                st = c.get("statistics", {})
                data["platform"] = "youtube"
                data["username"] = username
                data["url"] = f"https://youtube.com/@{username}"
                data["display_name"] = s.get("title", "")
                data["description"] = s.get("description", "")
                data["subscribers"] = st.get("subscriberCount", "0")
                data["video_count"] = st.get("videoCount", "0")
                data["view_count"] = st.get("viewCount", "0")
                ok(f"{data['display_name']} — {data['subscribers']} subscribers")
                return data
        except Exception as e:
            warn(f"YouTube API: {e}")
    else:
        info("No YOUTUBE_API_KEY set — falling back to web scrape")
    try:
        r = safe_get(f"https://www.youtube.com/@{username}/about")
        if not r:
            fail("YouTube: profile not found")
            return data
        import re
        from html import unescape
        html = r.text

        name_m = re.search(r'<title>([^<]+)</title>', html)
        if name_m:
            data["display_name"] = unescape(name_m.group(1)).replace(" - YouTube", "")
        sub_m = re.search(r'([\d.]+[KMB]?)\s*subscriber', html, re.I)
        if sub_m:
            data["subscribers"] = sub_m.group(1)
        desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
        if desc_m:
            data["description"] = unescape(desc_m.group(1))

        # Reject if page is a YouTube error, consent, or non-channel page
        title_lc = data.get("display_name", "").lower()
        is_channel = bool(name_m) and (
            "subscriber" in html.lower() or
            ("youtube" not in title_lc and "weiter" not in title_lc)
        )
        if not is_channel or "This channel doesn't exist" in html or "Not Found" in html:
            fail("YouTube: channel not found")
            return data
        data["platform"] = "youtube"
        data["username"] = username
        data["url"] = f"https://youtube.com/@{username}"
        ok(f"{data.get('display_name', username)} found via scrape")
        return data
    except Exception as e:
        fail(f"YouTube: {e}")
    return data


def fetch_twitter(username, bearer_token=None):
    data = {}
    section(f"Twitter/X — {username}")
    from os import environ
    token = bearer_token or environ.get("TWITTER_BEARER_TOKEN", "")
    if not token:
        fail("Twitter/X: set TWITTER_BEARER_TOKEN env var")
        return data
    try:
        r = safe_get(f"https://api.twitter.com/2/users/by/username/{username}",
                     headers={"Authorization": f"Bearer {token}"},
                     params={"user.fields": "public_metrics,description,created_at,profile_image_url,verified,location"})
        if not r:
            fail("Twitter/X: no response")
            return data
        j = r.json()
        if "errors" in j:
            fail(f"Twitter/X: {j['errors'][0].get('message', 'unknown error')}")
            return data
        u = j.get("data", {})
        data["platform"] = "twitter"
        data["username"] = username
        data["url"] = f"https://twitter.com/{username}"
        data["display_name"] = u.get("name", "")
        data["description"] = u.get("description", "")
        data["followers"] = u.get("public_metrics", {}).get("followers_count", 0)
        data["following"] = u.get("public_metrics", {}).get("following_count", 0)
        data["tweet_count"] = u.get("public_metrics", {}).get("tweet_count", 0)
        data["verified"] = u.get("verified", False)
        data["location"] = u.get("location", "")
        data["avatar_url"] = u.get("profile_image_url", "")
        data["account_age_days"] = 0
        created = u.get("created_at", "")
        if created:
            try:
                from datetime import datetime
                created_dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ")
                data["account_age_days"] = (datetime.utcnow() - created_dt).days
            except Exception:
                pass
        ok(f"@{username} — {data['followers']} followers")
        return data
    except Exception as e:
        fail(f"Twitter/X: {e}")
    return data


def fetch_instagram(username):
    data = {}
    section(f"Instagram — {username}")
    warn("Instagram scraping is fragile and may break at any time")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(f"https://www.instagram.com/{username}/", headers=headers, timeout=15)
        if r.status_code != 200:
            fail(f"Instagram: HTTP {r.status_code}")
            return data
        import re
        from html import unescape
        html = r.text
        json_m = re.search(r'<script type="application/ld\+json">([^<]+)</script>', html)
        if json_m:
            import json as _json
            try:
                ld = _json.loads(json_m.group(1))
                data["display_name"] = ld.get("name", "")
                data["description"] = ld.get("description", "")
                data["url"] = ld.get("url", f"https://instagram.com/{username}")
                data["image_url"] = ld.get("image", "")
            except Exception:
                pass
        name_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if name_m:
            data["display_name"] = unescape(name_m.group(1))
        desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        if desc_m:
            desc = unescape(desc_m.group(1))
            data["description"] = desc
            subs = re.search(r'([\d.]+[KMB]?)\s*Follow', desc, re.I)
            if subs:
                data["followers"] = subs.group(1)
            posts = re.search(r'([\d,]+)\s*Posts', desc, re.I)
            if posts:
                data["post_count"] = posts.group(1)
        data["platform"] = "instagram"
        data["username"] = username
        data.setdefault("url", f"https://instagram.com/{username}")
        if data.get("display_name"):
            ok(f"{data['display_name']} found")
            return data
        fail("Instagram: profile not found (may be blocked)")
    except Exception as e:
        fail(f"Instagram: {e}")
    return data


def fetch_threads(username):
    data = {}
    section(f"Threads — {username}")
    warn("Threads scraping is based on public JSON endpoint and may break")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        r = requests.get(f"https://www.threads.net/@{username}", headers=headers, timeout=15)
        if r.status_code != 200:
            fail(f"Threads: HTTP {r.status_code}")
            return data
        html = r.text
        import re
        from html import unescape
        json_m = re.search(r'<script type="application/json"[^>]*data-script>[^<]*__NEXT_DATA__[^<]*</script>', html)
        if not json_m:
            json_m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', html)
        if not json_m:
            name_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            if name_m:
                data["display_name"] = unescape(name_m.group(1))
            if desc_m:
                data["bio"] = unescape(desc_m.group(1))
        data["platform"] = "threads"
        data["username"] = username
        data["url"] = f"https://threads.net/@{username}"
        if data.get("display_name") or data.get("bio"):
            ok(f"Found: {data.get('display_name', username)}")
            return data
        fail("Threads: profile not found")
    except Exception as e:
        fail(f"Threads: {e}")
    return data


def fetch_pixelfed(username, instance="pixelfed.social"):
    data = {}
    section(f"Pixelfed — {username}@{instance}")
    r = safe_get(f"https://{instance}/api/v1/accounts/lookup",
                 params={"acct": username})
    if not r:
        fail("Pixelfed: no response")
        return data
    j = r.json()
    if j.get("error") or not j.get("id"):
        fail(f"Pixelfed: user not found on {instance}")
        return data
    data["platform"] = "pixelfed"
    data["username"] = f"{username}@{instance}"
    data["url"] = f"https://{instance}/{username}"
    data["display_name"] = j.get("display_name", "")
    data["bio"] = j.get("note", "")
    data["followers"] = j.get("followers_count", 0)
    data["following"] = j.get("following_count", 0)
    data["posts"] = j.get("statuses_count", 0)
    ok(f"{data['display_name'] or username} — {data['followers']} followers")
    return data


def fetch_peertube(username, instance="peertube.tv"):
    data = {}
    section(f"PeerTube — {username}@{instance}")
    r = safe_get(f"https://{instance}/api/v1/accounts?search={username}")
    if not r:
        fail("PeerTube: no response")
        return data
    accounts = r.json().get("data", [])
    for acct in accounts:
        if acct.get("name", "").lower() == username.lower():
            data["platform"] = "peertube"
            data["username"] = f"{username}@{instance}"
            data["url"] = f"https://{instance}/accounts/{username}"
            data["display_name"] = acct.get("displayName", "")
            data["bio"] = acct.get("description", "")
            data["followers"] = acct.get("followersCount", 0)
            data["videos"] = acct.get("videosCount", 0)
            data["created"] = acct.get("createdAt", "")
            ok(f"{data['display_name'] or username} — {data['followers']} followers")
            return data
    fail(f"PeerTube: user not found on {instance}")
    return data


def fetch_lemmy(username, instance="lemmy.world"):
    data = {}
    section(f"Lemmy — {username}@{instance}")
    r = safe_get(f"https://{instance}/api/v3/user",
                 params={"username": username})
    if not r:
        fail("Lemmy: no response")
        return data
    j = r.json()
    uv = j.get("user_view", {})
    u = uv.get("person", {})
    if not u or not u.get("id"):
        fail(f"Lemmy: user not found on {instance}")
        return data
    counts = uv.get("counts", {})
    data["platform"] = "lemmy"
    data["username"] = f"{username}@{instance}"
    data["url"] = f"https://{instance}/u/{username}"
    data["display_name"] = u.get("display_name", "") or u.get("name", "")
    data["bio"] = u.get("bio", "")
    data["banner"] = u.get("banner", "")
    data["avatar"] = u.get("avatar", "")
    data["posts"] = counts.get("post_count", 0)
    data["comments"] = counts.get("comment_count", 0)
    data["post_score"] = counts.get("post_score", 0)
    data["comment_score"] = counts.get("comment_score", 0)
    ok(f"{data['display_name']} — {data['posts']} posts, {data['comments']} comments")
    return data


def fetch_devto(username):
    data = {}
    section(f"Dev.to — {username}")
    r = safe_get(f"https://dev.to/api/users/by_username?url={username}")
    if not r or not r.json():
        fail("Dev.to: user not found")
        return data
    u = r.json()
    data["platform"] = "devto"
    data["username"] = username
    data["url"] = f"https://dev.to/{username}"
    data["display_name"] = u.get("name", "")
    data["bio"] = u.get("summary", "") or u.get("bio", "")
    data["location"] = u.get("location", "")
    data["github_username"] = u.get("github_username", "")
    data["twitter_username"] = u.get("twitter_username", "")
    data["website"] = u.get("website_url", "")
    data["articles"] = u.get("articles_count", 0)
    data["followers"] = u.get("followers_count", 0)
    data["following"] = u.get("following_count", 0)
    ok(f"{data['display_name']} — {data['articles']} articles")
    return data


def fetch_medium(username):
    data = {}
    section(f"Medium — {username}")
    r = safe_get(f"https://medium.com/@{username}?format=json")
    if not r:
        fail("Medium: no response")
        return data
    import re
    html = r.text
    # Strip )]}while(1);</x>  JSON security prefix
    json_text = re.sub(r'^\)\]\}while\s*\(1\);\s*</?\w+>\s*', '', html).strip()
    import json as _json
    try:
        j = _json.loads(json_text)
    except Exception:
        fail("Medium: could not parse profile JSON")
        return data
    payload = j.get("payload", {})
    u = payload.get("user", payload.get("collection", {}))
    if not u or not u.get("userId"):
        fail("Medium: user not found")
        return data
    data["platform"] = "medium"
    data["username"] = username
    data["url"] = f"https://medium.com/@{username}"
    data["display_name"] = u.get("name", "") or u.get("displayName", "")
    data["bio"] = u.get("bio", "") or u.get("description", "")
    data["image_url"] = u.get("image", {}).get("originalUrl", "") if isinstance(u.get("image"), dict) else ""
    data["twitter"] = u.get("twitterScreenName", "")
    ok(f"{data['display_name'] or username}")
    return data


def fetch_pinterest(username):
    data = {}
    section(f"Pinterest — {username}")
    warn("Pinterest scraping is fragile and may break")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    r = requests.get(f"https://www.pinterest.com/{username}/", headers=headers, timeout=15)
    if r.status_code != 200:
        fail(f"Pinterest: HTTP {r.status_code}")
        return data
    html = r.text
    import re
    from html import unescape
    name_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if name_m:
        data["display_name"] = unescape(name_m.group(1))
    desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
    if desc_m:
        data["bio"] = unescape(desc_m.group(1))
    img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if img_m:
        data["image_url"] = img_m.group(1)
    if not name_m and "Pinterest" in html[:500]:
        fail("Pinterest: profile not found")
        return data
    data["platform"] = "pinterest"
    data["username"] = username
    data["url"] = f"https://pinterest.com/{username}"
    data["followers"] = 0
    fol_m = re.search(r'([\d,.]+[KMB]?)\s*followers?', html, re.I)
    if fol_m:
        data["followers"] = fol_m.group(1)
    ok(f"{data.get('display_name', username)}")
    return data


def compute_activity_pattern(hours_list):
    if not hours_list:
        return "unknown"
    avg = sum(hours_list) / len(hours_list)
    if 5 <= avg < 12:
        return "morning person (UTC)"
    elif 12 <= avg < 18:
        return "afternoon active (UTC)"
    elif 18 <= avg < 23:
        return "evening active (UTC)"
    else:
        return "night owl (UTC)"


def _build_aggregated_text(all_data, intelx_data, darkweb_data):
    """Build aggregated text summary from all collected data for LLM."""
    summary_parts = []

    for d in all_data:
        if not d:
            continue
        platform = d.get("platform", "unknown")
        summary_parts.append(f"\n=== {platform.upper()} ===")

        if platform == "reddit":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Karma: {d.get('karma_post')} post, {d.get('karma_comment')} comment")
            summary_parts.append(f"Account age: {d.get('account_age_days')} days")
            summary_parts.append(f"Top subreddits: {', '.join(d.get('top_subreddits', []))}")
            summary_parts.append(f"Activity pattern: {compute_activity_pattern(d.get('activity_hours', []))}")
            titles = d.get("post_titles", [])
            if titles:
                summary_parts.append(f"Sample post titles: {' | '.join(titles[:8])}")
            comments = d.get("comment_samples", [])
            if comments:
                summary_parts.append(f"Sample comments: {' | '.join(comments[:5])}")

        elif platform == "github":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('name')}")
            summary_parts.append(f"Bio: {d.get('bio')}")
            summary_parts.append(f"Location: {d.get('location')}")
            summary_parts.append(f"Company: {d.get('company')}")
            summary_parts.append(f"Followers: {d.get('followers')} | Repos: {d.get('public_repos')}")
            summary_parts.append(f"Top languages: {', '.join(d.get('top_languages', []))}")
            summary_parts.append(f"Top topics: {', '.join(d.get('top_topics', []))}")
            repos = d.get("top_repos", [])
            if repos:
                summary_parts.append(f"Top repos: {', '.join([r[0] for r in repos[:5]])}")

        elif platform == "hackernews":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Karma: {d.get('karma')} | Submissions: {d.get('submission_count')}")
            summary_parts.append(f"About: {d.get('about')}")
            titles = d.get("story_titles", [])
            if titles:
                summary_parts.append(f"Submitted stories: {' | '.join(titles[:8])}")
            comments = d.get("comment_samples", [])
            if comments:
                summary_parts.append(f"Sample comments: {' | '.join(comments[:4])}")

        elif platform == "bluesky":
            summary_parts.append(f"Handle: {d.get('handle')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('description')}")
            summary_parts.append(f"Followers: {d.get('followers')} | Posts: {d.get('posts_count')}")
            summary_parts.append(f"Activity: {compute_activity_pattern(d.get('activity_hours', []))}")
            posts = d.get("post_samples", [])
            if posts:
                summary_parts.append(f"Sample posts: {' | '.join(posts[:8])}")

        elif platform == "mastodon":
            summary_parts.append(f"Username: {d.get('username')}@{d.get('instance')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('note')}")
            summary_parts.append(f"Followers: {d.get('followers')}")
            fields = d.get("fields", {})
            if fields:
                summary_parts.append(f"Profile fields: {fields}")
            toots = d.get("toot_samples", [])
            if toots:
                summary_parts.append(f"Sample toots: {' | '.join(toots[:5])}")

        elif platform == "gravatar":
            summary_parts.append(f"Email: {d.get('email')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"About: {d.get('about_me')}")
            summary_parts.append(f"Location: {d.get('location')}")
            summary_parts.append(f"Job: {d.get('job_title')} at {d.get('company')}")
            summary_parts.append(f"Linked accounts: {', '.join(d.get('linked_accounts', []))}")

        elif platform == "telegram":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio')}")

        elif platform == "youtube":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Subscribers: {d.get('subscribers')} | Videos: {d.get('video_count')} | Views: {d.get('view_count')}")
            summary_parts.append(f"Description: {d.get('description', '')[:200]}")

        elif platform == "twitter":
            summary_parts.append(f"Username: @{d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Followers: {d.get('followers')} | Following: {d.get('following')} | Tweets: {d.get('tweet_count')}")
            summary_parts.append(f"Location: {d.get('location')}")
            summary_parts.append(f"Verified: {d.get('verified')}")
            summary_parts.append(f"Description: {d.get('description', '')[:200]}")

        elif platform == "instagram":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('description', '')[:200]}")
            summary_parts.append(f"Followers: {d.get('followers')} | Posts: {d.get('post_count')}")

        elif platform == "threads":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")

        elif platform == "pixelfed":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")
            summary_parts.append(f"Followers: {d.get('followers')} | Posts: {d.get('posts')}")

        elif platform == "peertube":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")
            summary_parts.append(f"Followers: {d.get('followers')} | Videos: {d.get('videos')}")

        elif platform == "lemmy":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")
            summary_parts.append(f"Posts: {d.get('posts')} | Comments: {d.get('comments')}")

        elif platform == "devto":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")
            summary_parts.append(f"Articles: {d.get('articles')} | Followers: {d.get('followers')}")

        elif platform == "medium":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")
            summary_parts.append(f"Twitter: {d.get('twitter', 'N/A')}")

        elif platform == "pinterest":
            summary_parts.append(f"Username: {d.get('username')}")
            summary_parts.append(f"Name: {d.get('display_name')}")
            summary_parts.append(f"Bio: {d.get('bio', '')[:200]}")
            summary_parts.append(f"Followers: {d.get('followers')}")

    if intelx_data:
        summary_parts.append(f"\n=== INTELX ({len(intelx_data)} results) ===")
        for r in intelx_data[:10]:
            summary_parts.append(f"Source: {r.get('source')} | URL: {r.get('url')} | Date: {r.get('date', 'N/A')}")

    if darkweb_data:
        summary_parts.append(f"\n=== DARK WEB ({len(darkweb_data)} results) ===")
        for r in darkweb_data[:10]:
            summary_parts.append(f"Title: {r.get('title')} | URL: {r.get('url')}")

    return "\n".join(summary_parts)


def _call_llm(provider, model, api_key, prompt, max_tokens=2000):
    """Send a prompt to the specified LLM provider and return the response text."""
    provider = provider.lower()

    if provider == "anthropic":
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package not installed (pip install anthropic)")
        from os import environ
        key = api_key or environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        client = Anthropic(api_key=key)
        message = client.messages.create(
            model=model or "claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    elif provider == "openai":
        if not HAS_OPENAI:
            raise ImportError("openai package not installed (pip install openai)")
        from os import environ
        key = api_key or environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        client = openai_sdk.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model or "gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    elif provider == "google":
        if not HAS_GOOGLE:
            raise ImportError("google-genai package not installed (pip install google-genai)")
        from os import environ
        key = api_key or environ.get("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError("GOOGLE_API_KEY not set")
        client = google_genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model or "gemini-2.0-flash",
            contents=prompt,
            config={"max_output_tokens": max_tokens},
        )
        return resp.text

    elif provider in ("groq", "lumo", "openrouter"):
        if not HAS_OPENAI:
            raise ImportError("openai package not installed (pip install openai)")

        provider_config = LLM_PROVIDERS[provider]
        env_var = provider_config["env_key"]
        base_url = provider_config["base_url"]
        default_model = provider_config["default_model"]

        from os import environ
        key = api_key or environ.get(env_var, "")
        if not key:
            raise ValueError(f"{env_var} not set")

        model_name = model or default_model
        client = openai_sdk.OpenAI(api_key=key, base_url=base_url)
        extra = {}
        if provider == "lumo":
            extra["stream"] = False
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            **extra,
        )
        return resp.choices[0].message.content or ""

    elif provider == "ollama":
        base_url = LLM_PROVIDERS["ollama"]["base_url"]
        model_name = model or "llama3.2"
        try:
            r = requests.post(
                f"{base_url}/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens}},
                timeout=120,
            )
            if r.status_code == 200:
                return r.json().get("response", "")
            raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Ollama not reachable at {base_url}")

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def generate_ai_profile(all_data, intelx_data=None, darkweb_data=None,
                        llm_provider="anthropic", llm_model=None, llm_key=None):
    section("AI Profile Generation")

    aggregated = _build_aggregated_text(all_data, intelx_data or [], darkweb_data or [])
    if not aggregated.strip():
        fail("No data collected, skipping AI profile.")
        return

    prompt = f"""You are analyzing publicly available social media and intelligence data to build a personality and interest profile.
Based on the data below, write a structured profile covering:

1. TECHNICAL SKILLS & EXPERTISE (if any)
2. TOPICS OF INTEREST & PASSIONS
3. COMMUNICATION STYLE & PERSONALITY TRAITS
4. ONLINE BEHAVIOR PATTERNS (activity times, engagement style)
5. LIKELY PROFESSION OR BACKGROUND
6. COMMUNITY INVOLVEMENT
7. SUMMARY (3-4 sentences describing this person's digital identity)

Be analytical and evidence-based. Reference specific data points. Be respectful.

--- DATA ---
{aggregated}
"""

    provider_display = llm_provider.upper() if llm_provider else "AI"
    info(f"Sending to {provider_display} for analysis...")

    try:
        profile_text = _call_llm(llm_provider, llm_model, llm_key, prompt)
        if _use_rich:
            c = _get_console()
            c.print(Panel(Markdown(profile_text), title=f"{provider_display} Generated Profile",
                          border_style="white", title_align="left"))
        else:
            print(f"\n{BOLD}{WHITE}{'═'*60}{RESET}")
            print(f"{BOLD}{WHITE}  {provider_display} GENERATED PROFILE{RESET}")
            print(f"{BOLD}{WHITE}{'═'*60}{RESET}")
            for line in profile_text.split("\n"):
                if line.strip() and line.strip()[0].isdigit() and ". " in line[:4]:
                    print(f"\n{YELLOW}{BOLD}{line}{RESET}")
                else:
                    print(f"  {line}")
            print(f"{BOLD}{WHITE}{'═'*60}{RESET}\n")
    except Exception as e:
        fail(f"AI profile generation failed: {e}")


def save_json(all_data, username):
    filename = f"osint_{username}_{int(time.time())}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    ok(f"Raw data saved to: {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(
        description="OSINT Public Profile Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python osint_profiler.py --reddit torvalds
          python osint_profiler.py --github torvalds --hackernews tptacek
          python osint_profiler.py --bluesky alice.bsky.social --ai
          python osint_profiler.py --email user@example.com --ai
          python osint_profiler.py --mastodon Gargron --mastodon-instance mastodon.social --ai
          python osint_profiler.py --telegram josephmornin
          python osint_profiler.py --youtube @mkbhd --ai
          python osint_profiler.py --twitter elonmusk --ai
          python osint_profiler.py --instagram zuck --ai
          python osint_profiler.py --threads zuck --ai
          python osint_profiler.py --github torvalds --reddit spez --ai --save
  python osint_profiler.py --github torvalds --intelx --ai --llm openai
  python osint_profiler.py --email user@example.com --darkweb --ai --llm groq
  python osint_profiler.py --intelx johndoe          # IntelX only, inline query
  python osint_profiler.py --darkweb "target user"   # dark web only, inline query
          python osint_profiler.py --github torvalds --intelx --darkweb --ai --llm google
  python osint_profiler.py --scan johndoe                  # scan all platforms
  python osint_profiler.py --scan johndoe --ai --save      # scan all + AI profile + save
        """)
    )

    parser.add_argument("--reddit",    metavar="USERNAME",  help="Reddit username")
    parser.add_argument("--reddit-client-id", metavar="ID",  help="Reddit OAuth client ID (or set REDDIT_CLIENT_ID env var)")
    parser.add_argument("--reddit-client-secret", metavar="SECRET", help="Reddit OAuth client secret (or set REDDIT_CLIENT_SECRET env var)")
    parser.add_argument("--github",    metavar="USERNAME",  help="GitHub username")
    parser.add_argument("--hackernews",metavar="USERNAME",  help="Hacker News username")
    parser.add_argument("--bluesky",   metavar="HANDLE",    help="Bluesky handle (e.g. alice.bsky.social)")
    parser.add_argument("--mastodon",  metavar="USERNAME",  help="Mastodon username (without @)")
    parser.add_argument("--mastodon-instance", metavar="INSTANCE", default="mastodon.social", help="Mastodon instance (default: mastodon.social)")
    parser.add_argument("--email",     metavar="EMAIL",     help="Email address for Gravatar lookup")
    parser.add_argument("--telegram",  metavar="USERNAME",  help="Telegram username")
    parser.add_argument("--youtube",   metavar="USERNAME",  help="YouTube channel handle (e.g. @channelname)")
    parser.add_argument("--youtube-api-key", metavar="KEY", help="YouTube Data API key (or set YOUTUBE_API_KEY env var)")
    parser.add_argument("--twitter",   metavar="USERNAME",  help="Twitter/X username")
    parser.add_argument("--twitter-bearer-token", metavar="TOKEN", help="Twitter/X Bearer token (or set TWITTER_BEARER_TOKEN env var)")
    parser.add_argument("--instagram", metavar="USERNAME",
                         help="Instagram username (⚠ web scraping, breaks often)")
    parser.add_argument("--threads",   metavar="USERNAME",
                         help="Threads username (⚠ web scraping, breaks often)")
    parser.add_argument("--pixelfed",  metavar="USERNAME",
                         help="Pixelfed username (Fediverse)")
    parser.add_argument("--pixelfed-instance", metavar="INSTANCE", default="pixelfed.social",
                         help="Pixelfed instance (default: pixelfed.social)")
    parser.add_argument("--peertube",  metavar="USERNAME",
                         help="PeerTube username (Fediverse)")
    parser.add_argument("--peertube-instance", metavar="INSTANCE", default="peertube.tv",
                         help="PeerTube instance (default: peertube.tv)")
    parser.add_argument("--lemmy",     metavar="USERNAME",
                         help="Lemmy username (Fediverse)")
    parser.add_argument("--lemmy-instance", metavar="INSTANCE", default="lemmy.world",
                         help="Lemmy instance (default: lemmy.world)")
    parser.add_argument("--devto",     metavar="USERNAME",  help="Dev.to username")
    parser.add_argument("--medium",    metavar="USERNAME",  help="Medium username (@username)")
    parser.add_argument("--pinterest", metavar="USERNAME",
                         help="Pinterest username (⚠ web scraping, breaks often)")
    parser.add_argument("--intelx",    nargs="?", const=True, default=False, metavar="QUERY",
                                       help="Search IntelX. Optionally specify a query (defaults to first provided username/email)")
    parser.add_argument("--darkweb",   nargs="?", const=True, default=False, metavar="QUERY",
                                       help="Search dark web (Ahmia). Optionally specify a query (defaults to first provided username/email)")
    parser.add_argument("--ai",        action="store_true", help="Generate AI profile from collected data")
    parser.add_argument("--llm",       metavar="PROVIDER",  choices=list(LLM_PROVIDERS.keys()),
                                       default="anthropic", help="LLM provider for AI profile generation")
    parser.add_argument("--llm-model", metavar="MODEL",     help="LLM model override")
    parser.add_argument("--llm-key",   metavar="KEY",       help="LLM API key override (or set env var)")
    parser.add_argument("--save",      action="store_true", help="Save raw JSON data to file")
    parser.add_argument("--no-color",  action="store_true", help="Disable colored output")
    parser.add_argument("--scan",     metavar="USERNAME_OR_EMAIL",
                                       help="Scan a single identity across all available platforms")
    parser.add_argument("--rich",      action="store_true", default=HAS_RICH,
                                       help="Use rich formatted output (default: auto)" if HAS_RICH else
                                            "Use rich formatted output (install `rich` package)")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.no_color:
        args.rich = False
    if args.rich:
        enable_rich()

    # --scan auto-fills all platform args
    if args.scan:
        for plat_attr in ("reddit", "github", "hackernews", "bluesky", "mastodon",
                          "email", "telegram", "youtube", "twitter", "instagram", "threads",
                          "pixelfed", "peertube", "lemmy", "devto", "medium", "pinterest"):
            if not getattr(args, plat_attr, None):
                setattr(args, plat_attr, args.scan)
        info(f"Scan mode: checking all platforms for '{args.scan}'")

    banner()

    all_data = []

    if args.reddit:
        d = fetch_reddit(args.reddit, client_id=args.reddit_client_id, client_secret=args.reddit_client_secret)
        if d:
            all_data.append(d)

    if args.github:
        d = fetch_github(args.github)
        if d:
            all_data.append(d)

    if args.hackernews:
        d = fetch_hackernews(args.hackernews)
        if d:
            all_data.append(d)

    if args.bluesky:
        d = fetch_bluesky(args.bluesky)
        if d:
            all_data.append(d)

    if args.mastodon:
        d = fetch_mastodon(args.mastodon, args.mastodon_instance)
        if d:
            all_data.append(d)

    if args.email:
        d = fetch_gravatar(args.email)
        if d:
            all_data.append(d)

    if args.telegram:
        d = fetch_telegram(args.telegram)
        if d:
            all_data.append(d)

    if args.youtube:
        d = fetch_youtube(args.youtube, api_key=args.youtube_api_key)
        if d:
            all_data.append(d)

    if args.twitter:
        d = fetch_twitter(args.twitter, bearer_token=args.twitter_bearer_token)
        if d:
            all_data.append(d)

    if args.instagram:
        d = fetch_instagram(args.instagram)
        if d:
            all_data.append(d)

    if args.threads:
        d = fetch_threads(args.threads)
        if d:
            all_data.append(d)

    if args.pixelfed:
        d = fetch_pixelfed(args.pixelfed, instance=args.pixelfed_instance)
        if d:
            all_data.append(d)

    if args.peertube:
        d = fetch_peertube(args.peertube, instance=args.peertube_instance)
        if d:
            all_data.append(d)

    if args.lemmy:
        d = fetch_lemmy(args.lemmy, instance=args.lemmy_instance)
        if d:
            all_data.append(d)

    if args.devto:
        d = fetch_devto(args.devto)
        if d:
            all_data.append(d)

    if args.medium:
        d = fetch_medium(args.medium)
        if d:
            all_data.append(d)

    if args.pinterest:
        d = fetch_pinterest(args.pinterest)
        if d:
            all_data.append(d)

    # Derive the primary identity from the first provided social-media field
    identity = (args.email or args.reddit or args.github or args.hackernews
                or args.bluesky or args.mastodon or args.telegram
                or args.youtube or args.twitter or args.instagram or args.threads
                or args.pixelfed or args.peertube or args.lemmy
                or args.devto or args.medium or args.pinterest or "")

    intelx_data = []
    if args.intelx:
        iq = args.intelx if isinstance(args.intelx, str) else identity
        if iq:
            intelx_data = fetch_intelx(iq)
            if intelx_data:
                all_data.append({"platform": "intelx", "results": intelx_data, "query": iq})

    darkweb_data = []
    if args.darkweb:
        dq = args.darkweb if isinstance(args.darkweb, str) else identity
        if dq:
            darkweb_data = fetch_ahmia(dq)
            if darkweb_data:
                all_data.append({"platform": "darkweb", "results": darkweb_data, "query": dq})

    if not all_data:
        section("Result")
        fail("No data could be collected. Check usernames and try again.")
        sys.exit(1)

    identifier = (args.reddit or args.github or args.hackernews or args.bluesky
                  or args.mastodon or args.email or args.telegram
                  or args.youtube or args.twitter or args.instagram or args.threads
                  or args.pixelfed or args.peertube or args.lemmy
                  or args.devto or args.medium or args.pinterest or "profile")

    if args.save:
        save_json(all_data, identifier.replace("@","_").replace(".","_"))

    if args.ai:
        generate_ai_profile(
            all_data,
            intelx_data=intelx_data,
            darkweb_data=darkweb_data,
            llm_provider=args.llm,
            llm_model=args.llm_model,
            llm_key=args.llm_key,
        )
    else:
        section("Done")
        if _use_rich:
            t = Table(title=f"Collected {len(all_data)} platform(s)", box=box.ROUNDED)
            t.add_column("Platform", style="cyan")
            t.add_column("Key Data", style="white")
            for d in all_data:
                plat = d.get("platform", "?")
                if plat == "intelx":
                    v = f"{len(d.get('results', []))} results"
                elif plat == "darkweb":
                    v = f"{len(d.get('results', []))} results"
                elif plat == "reddit":
                    v = f"Karma {d.get('karma_post', 0)}/{d.get('karma_comment', 0)}"
                elif plat == "github":
                    v = f"{d.get('followers', 0)} followers"
                elif plat == "hackernews":
                    v = f"Karma {d.get('karma', 0)}"
                elif plat == "bluesky":
                    v = f"{d.get('followers', 0)} followers"
                elif plat == "mastodon":
                    v = f"{d.get('followers', 0)} followers"
                elif plat == "gravatar":
                    v = d.get("display_name", d.get("email", ""))
                elif plat == "telegram":
                    v = d.get("display_name", d.get("username", ""))
                elif plat == "twitter":
                    v = f"{d.get('followers', 0)} followers"
                elif plat == "youtube":
                    v = f"{d.get('subscribers', 0)} subscribers"
                elif plat == "instagram":
                    v = f"{d.get('display_name', d.get('username', ''))}"
                elif plat == "threads":
                    v = d.get("display_name", d.get("username", ""))
                elif plat == "pixelfed":
                    v = f"{d.get('followers', 0)} followers"
                elif plat == "peertube":
                    v = f"{d.get('followers', 0)} followers"
                elif plat == "lemmy":
                    v = f"{d.get('posts', 0)} posts"
                elif plat == "devto":
                    v = f"{d.get('articles', 0)} articles"
                elif plat == "medium":
                    v = d.get("display_name", d.get("username", ""))
                elif plat == "pinterest":
                    v = d.get("display_name", d.get("username", ""))
                else:
                    v = "ok"
                t.add_row(plat, str(v)[:60])
            _get_console().print(t)
        else:
            ok(f"Collected data from {len(all_data)} platform(s).")
        info("Add --ai flag to generate an AI personality profile.")
        info(f"  Use --llm (choices: {', '.join(LLM_PROVIDERS.keys())}) to select provider (default: anthropic).")
        info("Add --save flag to export raw JSON.")


if __name__ == "__main__":
    main()
