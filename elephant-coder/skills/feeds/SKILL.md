---
name: feeds
description: Manage RSS feeds — add, remove, list, start/stop the news briefing
---

Manage elephant-coder RSS news feeds for the current project.

## Usage

When invoked without arguments, show the current feed list and ask what the user wants to do.

When invoked with an argument, interpret it as a subcommand:
- `/ec:feeds list` — show all configured feeds
- `/ec:feeds add <url>` — add a new RSS feed URL
- `/ec:feeds remove <url or number>` — remove a feed by URL or list number
- `/ec:feeds start` — enable news briefing (runs on session start)
- `/ec:feeds stop` — disable news briefing

## Steps

### List feeds
1. Read current settings from `.claude/elephant-coder.local.md`
2. Display numbered list of all `rss_feeds` URLs
3. Show whether news briefing is enabled (check if `get_news_briefing()` is in session start)

### Add a feed
1. Validate the URL looks like an RSS/Atom feed
2. Read current `rss_feeds` from settings
3. Append the new URL
4. Call `update_settings()` to persist
5. Confirm: "Added feed: <url>"

### Remove a feed
1. If user gave a number, map it to the URL from the list
2. Read current `rss_feeds` from settings
3. Remove the matching URL
4. Call `update_settings()` to persist
5. Confirm: "Removed feed: <url>"

### Start/Stop
1. To stop: set `rss_feeds` to an empty list (or add a `rss_enabled: false` setting)
2. To start: restore default feeds or re-enable
3. Call `update_settings()` to persist
4. Confirm the change

## Notes
- Feed changes take effect on the next `get_news_briefing()` call
- Default feeds include HackerNews, ArsTechnica, arXiv, Reddit, CBC, etc.
- Use `rss_max_articles_per_feed` to control volume (default: 5)
