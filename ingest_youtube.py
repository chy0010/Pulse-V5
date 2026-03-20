import os
import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

DB_PATH = "marketpulse_v5.db"
CACHE_PATH = "channel_cache.json"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

TIER1_HANDLES = [
    "@GoodWorkMB", "@morning-brew", "@techteller927", "@mkbhd", "@guistetelle",
    "@alexlorenlee", "@miso-tech", "@firooza", "@AaravNarula", "@VarunMayya",
    "@nikhil.kamath", "@TomBilyeu", "@DwarkeshPatel", "@JeffSu", "@iqjayfeng",
    "@mreflow", "@AaronJack", "@harkirat1", "@IvyFung", "@martinzeman89",
    "@RuntimeBRT", "@principlesbyraydalio", "@SimplilearnOfficial",
    "@IBMTechnology", "@Vox", "@ALifeEngineered", "@FactasticFeed", "@worldaffairsEng",
    "@USAFacts_Official", "@LeisRealTalk", "@robmulla", "@NewMachina", "@TLDRbusiness",
    # Added
    "@TinaHuang1", "@HowMoneyWorks", "@HeresyFinancial", "@johnnyharris",
    "@TheDiaryOfACEO", "@TheNewYorker", "@HooverInstitution", "@EconomicsExplained",
    "@Deeplearningai", "@Micro-Econ-YT", "@PBoyle", "@eoglobal",
    "@claude", "@ConfluentDeveloper", "@TechAltar", "@CNET",
    "@SAMTIME", "@JiangKnowledgeCapsule", "@SimonClark", "@peterdiamandis",
    "@OutofSpecReviews", "@RealEngineering", "@ThinkSchool",
    # Added batch 2
    "@RachelHow", "@WarnerBros", "@KinoCheck.com", "@marvel", "@60minutes",
    "@NikhilKamathClips", "@veritasium", "@RottenTomatoesTRAILERS",
    "@PhilippLackner", "@LexClips",
]

TIER2_HANDLES = [
    "@CNBC", "@CNBCi", "@CNBCtelevision", "@WSJNews", "@markets",
    "@Bloomberg-News", "@business", "@BloombergNewEconomy", "@FoxBusiness",
    "@FinancialTimes", "@YahooFinance", "@BusinessToday", "@Groww", "@moneycontrol",
]

TIER1_COMMENTS = 40
TIER2_COMMENTS = 20
TIER1_LOOKBACK_HOURS = 48
TIER2_LOOKBACK_HOURS = 24
REPLY_THRESHOLD = 3
MAX_REPLIES = 10
API_DELAY = 0.2


def get_youtube():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_channel_info(youtube, handle, cache):
    if handle in cache:
        return cache[handle]

    try:
        resp = youtube.channels().list(
            part="id,snippet,contentDetails",
            forHandle=handle.lstrip("@")
        ).execute()
        time.sleep(API_DELAY)

        items = resp.get("items", [])
        if not items:
            print(f"  Channel not found: {handle}")
            return None

        item = items[0]
        info = {
            "channel_id": item["id"],
            "channel_name": item["snippet"]["title"],
            "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
        }
        cache[handle] = info
        save_cache(cache)
        return info
    except Exception as e:
        print(f"  Error fetching channel {handle}: {e}")
        return None


def get_recent_videos(youtube, uploads_playlist_id, cutoff_dt):
    videos = []
    page_token = None

    while True:
        kwargs = {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        try:
            resp = youtube.playlistItems().list(**kwargs).execute()
            time.sleep(API_DELAY)
        except Exception as e:
            print(f"    Error fetching playlist: {e}")
            break

        for item in resp.get("items", []):
            snippet = item["snippet"]
            published_str = snippet.get("publishedAt", "")
            if not published_str:
                continue

            published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            if published_dt < cutoff_dt:
                return videos

            video_id = snippet.get("resourceId", {}).get("videoId")
            if video_id:
                videos.append({
                    "video_id": video_id,
                    "video_title": snippet.get("title", ""),
                    "published_at": published_str,
                })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return videos


def insert_video(conn, video_id, channel_handle, channel_name, video_title, published_at, source_tier):
    try:
        conn.execute("""
            INSERT OR IGNORE INTO videos
                (video_id, channel_handle, channel_name, video_title, published_at, source_tier)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (video_id, channel_handle, channel_name, video_title, published_at, source_tier))
        conn.commit()
        return conn.execute(
            "SELECT changes()"
        ).fetchone()[0] > 0
    except Exception as e:
        print(f"    DB error inserting video: {e}")
        return False


def fetch_comments(youtube, video_id, max_results):
    comments = []
    try:
        resp = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=min(max_results, 100),
            textFormat="plainText",
        ).execute()
        time.sleep(API_DELAY)

        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "comment_id": item["id"],
                "text": top.get("textDisplay", ""),
                "author": top.get("authorDisplayName", ""),
                "like_count": top.get("likeCount", 0),
                "reply_count": item["snippet"].get("totalReplyCount", 0),
                "published_at": top.get("publishedAt", ""),
                "is_reply": 0,
                "parent_comment_id": None,
            })
    except Exception as e:
        err_str = str(e)
        if "commentsDisabled" in err_str or "disabled comments" in err_str.lower():
            pass  # skip silently
        else:
            print(f"    Error fetching comments for {video_id}: {e}")

    return comments


def fetch_replies(youtube, parent_comment_id):
    replies = []
    try:
        resp = youtube.comments().list(
            part="snippet",
            parentId=parent_comment_id,
            maxResults=MAX_REPLIES,
            textFormat="plainText",
        ).execute()
        time.sleep(API_DELAY)

        for item in resp.get("items", []):
            s = item["snippet"]
            replies.append({
                "comment_id": item["id"],
                "text": s.get("textDisplay", ""),
                "author": s.get("authorDisplayName", ""),
                "like_count": s.get("likeCount", 0),
                "reply_count": 0,
                "published_at": s.get("publishedAt", ""),
                "is_reply": 1,
                "parent_comment_id": parent_comment_id,
            })
    except Exception as e:
        print(f"    Error fetching replies for {parent_comment_id}: {e}")

    return replies


def insert_comments(conn, video_id, comments):
    for c in comments:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO comments
                    (video_id, comment_id, text, author, like_count, reply_count,
                     is_reply, parent_comment_id, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_id, c["comment_id"], c["text"], c["author"],
                c["like_count"], c["reply_count"], c["is_reply"],
                c["parent_comment_id"], c["published_at"],
            ))
        except Exception as e:
            print(f"    DB error inserting comment: {e}")
    conn.commit()


def process_channel(youtube, conn, handle, tier, cache):
    max_comments = TIER1_COMMENTS if tier == "tier1" else TIER2_COMMENTS
    lookback = TIER1_LOOKBACK_HOURS if tier == "tier1" else TIER2_LOOKBACK_HOURS
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=lookback)

    print(f"\n[{tier}] {handle}")

    info = get_channel_info(youtube, handle, cache)
    if not info:
        return

    videos = get_recent_videos(youtube, info["uploads_playlist_id"], cutoff_dt)
    print(f"  {len(videos)} new video(s) in last {lookback}h")

    for video in videos:
        vid = video["video_id"]

        is_new = insert_video(
            conn, vid, handle, info["channel_name"],
            video["video_title"], video["published_at"], tier
        )
        if not is_new:
            print(f"  Already processed: {vid}")
            continue

        print(f"  Processing: {video['video_title'][:60]}")

        comments = fetch_comments(youtube, vid, max_comments)
        print(f"    {len(comments)} comments")

        reply_parents = [c for c in comments if c["reply_count"] >= REPLY_THRESHOLD]
        for parent in reply_parents:
            replies = fetch_replies(youtube, parent["comment_id"])
            comments.extend(replies)
            print(f"    +{len(replies)} replies for comment {parent['comment_id'][:20]}...")

        insert_comments(conn, vid, comments)


def main():
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY not set in .env")

    youtube = get_youtube()
    conn = sqlite3.connect(DB_PATH)
    cache = load_cache()

    print("=== MarketPulse v5 — YouTube Ingestion ===")
    print(f"Lookback: Tier1={TIER1_LOOKBACK_HOURS}h Tier2={TIER2_LOOKBACK_HOURS}h | Tier1: {TIER1_COMMENTS} comments | Tier2: {TIER2_COMMENTS} comments")

    for handle in TIER1_HANDLES:
        process_channel(youtube, conn, handle, "tier1", cache)

    for handle in TIER2_HANDLES:
        process_channel(youtube, conn, handle, "tier2", cache)

    conn.close()

    total_videos = sqlite3.connect(DB_PATH).execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    total_comments = sqlite3.connect(DB_PATH).execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    print(f"\n=== Done ===")
    print(f"Total videos in DB: {total_videos}")
    print(f"Total comments in DB: {total_comments}")


if __name__ == "__main__":
    main()
