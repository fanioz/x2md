# Research: How existing Apify Store X/Twitter post-scraper Actors handle input, media, threads, and pricing
**Date:** 2026-09-21
**Method:** Public Apify Store API (`/v2/acts/{id}` and `/v2/acts/{id}/builds/{buildId}`) queried without an APIFY token. `search_actors.js` was used to discover relevant actors. No actor runs were performed; findings come from actor metadata, READMEs, and input schemas.
**Scope:** Actors that scrape individual X/Twitter posts, threads, replies, or related media. Profile/search actors are included only where they are the closest comparable.
## At-a-glance summary
| Actor | Key inputs | Thread support | Media handling (output) | Pricing |
| --- | --- | --- | --- | --- |
| `apidojo/tweet-scraper` | `startUrls`, `twitterHandles`, `conversationIds`, `maxItems`, `onlyVideo`, `placeObjectId` | yes (`conversationIds`, `minimumReplies`) | input `onlyImage`; input `onlyVideo`; output `media` | PAY_PER_EVENT $0.0004/item (BRONZE) |
| `apidojo/twitter-scraper-lite` | `maxItems`, `twitterHandles`, `startUrls` | mentioned in docs | output `media` | PAY_PER_EVENT $0.0004/item (BRONZE) |
| `apidojo/twitter-replies-scraper` | `startUrls`, `tweetIds`, `maxItems` | mentioned in docs | output `media` | PAY_PER_EVENT dataset-item |
| `danek/twitter-scraper` | `username`, `query`, `post_id`, `lookup_post_ids`, `max_posts` | no explicit fields | — | PAY_PER_EVENT $0.00028/item (BRONZE) |
| `xquik/x-tweet-scraper` | `startUrls`, `twitterHandles`, `profileUrls`, `tweetIds`, `listIds`, `mode`, `maxItems`, `maxItemsPerTarget`... | yes (`conversation_id`, `conversationIds`, `threadTweetIds`, `min_replies`, `-min_replies`, `filter:replies`) | input `profileUrls`; input `media`; input `filter:native_video`; input `filter:consumer_video`; input `filter:pro_video`; input `respectProfileSubpages`; input `filter:media`; input `filter:images`; input `filter:videos`; output `media`; output `mediaUrls`; output `imageUrls`; output `videoUrls`; mentions mp4; video variants | PAY_PER_EVENT $0.00015/item (BRONZE) |
| `scraping_solutions/twitter-x-scraper-post-timeline-search-replies` |  | mentioned in docs | — | PAY_PER_EVENT $0.00095/item (BRONZE) |
| `pratikdani/twitter-posts-scraper` | `url` | no explicit fields | — | PAY_PER_EVENT $0.02/item (BRONZE) |
| `clappi/x-twitter-post-scraper` | `postUrls` | no explicit fields | output `media` | PAY_PER_EVENT $0.0033/item (GOLD) |
| `calm_builder/twitter-posts-scraper` | `postUrls`, `flattenOutput` | no explicit fields | input `includeAuthorProfile`; output `media`; video variants | PAY_PER_EVENT $0.00083/item (BRONZE) |
| `scraper_one/x-profile-posts-scraper` | `profileUrls` | mentioned in docs | input `profileUrls`; output `media` | PAY_PER_EVENT $0.0004/item (BRONZE) |
| `automation-lab/twitter-scraper` | `mode`, `usernames`, `tweetUrls`, `searchMode`, `maxResults` | mentioned in docs | output `mediaUrls` | PAY_PER_EVENT $0.0027/item (BRONZE) |
| `xtdata/twitter-x-scraper` | `startUrls`, `twitterHandles`, `maxItems`, `onlyVideo` | mentioned in docs | input `onlyImage`; input `onlyVideo` | PAY_PER_EVENT $0.0008/item (BRONZE) |
## Per-actor findings

### apidojo/tweet-scraper
- **Title:** Tweet Scraper V2 - X / Twitter Scraper
- **Apify URL:** https://apify.com/apidojo/tweet-scraper
- **Popularity:** 164314003 runs, 101052 users, 3.9040025889572973 rating (181 reviews)
- **Pricing:** PAY_PER_EVENT $0.0004/item (BRONZE)

**Input schema highlights:**
- `startUrls` (`array`): Twitter (X) URLs. Paste the URLs and get the results immediately. Tweet, Profile, Search or List URLs are supported.
- `searchTerms` (`array`): Search terms you want to search from Twitter (X). You can refer to https://github.com/igorbrigadir/twitter-advanced-search.
- `twitterHandles` (`array`): Twitter handles that you want to search on Twitter (X)
- `conversationIds` (`array`): Conversation IDs that you want to search on Twitter (X)
- `maxItems` (`integer`): Maximum number of items that you want as output.
- `sort` (`string`): Sorts search results. If you are getting low results, try Top instead of Latest. Latest + Top runs both simultaneously to maximize results but may return some duplicate tweets.
- `tweetLanguage` (`string`): Restricts tweets to the given language, given by an ISO 639-1 code.
- `onlyVerifiedUsers` (`boolean`): If selected, only returns tweets by users who are verified.
- `onlyTwitterBlue` (`boolean`): If selected, only returns tweets by users who are Twitter Blue subscribers.
- `onlyImage` (`boolean`): If selected, only returns tweets that contain images.
- `onlyVideo` (`boolean`): If selected, only returns tweets that contain videos.
- `onlyQuote` (`boolean`): If selected, only returns tweets that are quotes.
- `author` (`string`): Returns tweets sent by the given user. It should be a Twitter (X) Handle.
- `inReplyTo` (`string`): Returns tweets that are replies to the given user. It should be a Twitter (X) Handle.
- `mentioning` (`string`): Returns tweets mentioning the given user. It should be a Twitter (X) Handle.
- `geotaggedNear` (`string`): Returns tweets sent near the given location.
- `withinRadius` (`string`): Returns tweets sent within the given radius of the given location.
- `geocode` (`string`): Returns tweets sent by users located within a given radius of the given latitude/longitude.
- `placeObjectId` (`string`): Returns tweets tagged with the given place.
- `minimumRetweets` (`integer`): Returns tweets with at least the given number of retweets.
- `minimumFavorites` (`integer`): Returns tweets with at least the given number of favorites.
- `minimumReplies` (`integer`): Returns tweets with at least the given number of replies.
- `start` (`string`): Returns tweets sent after the given date.
- `end` (`string`): Returns tweets sent before the given date.
- `includeSearchTerms` (`boolean`): If selected, a field will be added to each tweets about the search term that was used to find it.
- `customMapFunction` (`string`): Function that takes each of the objects as argument and returns data that will be mapped by the function itself. This function is not intended for filtering, please don't use it for filtering purposes or you will get banned automatically.

**Media handling:**
- input `onlyImage`; input `onlyVideo`; output `media`

**Thread/conversation support:** yes (`conversationIds`, `minimumReplies`)

### apidojo/twitter-scraper-lite
- **Title:** Twitter (X.com) Scraper Unlimited: No Limits
- **Apify URL:** https://apify.com/apidojo/twitter-scraper-lite
- **Popularity:** 18806786 runs, 33892 users, 4.059752081225268 rating (81 reviews)
- **Pricing:** PAY_PER_EVENT $0.0004/item (BRONZE)

**Input schema highlights:**
- `searchTerms` (`array`): If you add search terms, the scraper will find and extract tweets that mention those terms. Alternatively, see further down to scrape by Twitter URL.
- `sort` (`string`): Sorts search results. If you are getting low results, try Top instead of Latest. Latest + Top runs both simultaneously to maximize results but may return some duplicate tweets.
- `maxItems` (`integer`): This value lets you set the maximum number of tweets to retrieve. Twitter has a default limit of around 800 tweets per query. Check the README for workarounds.
- `start` (`string`): Scrape tweets starting from this date
- `end` (`string`): Scrape tweets until this date
- `twitterHandles` (`array`): You can add the twitter handles of specific profiles you want to scrape. This is a shortcut so that you don't have to add full username URLs like https://twitter.com/apify
- `startUrls` (`array`): This lets you tell the scraper where to start. You can enter Twitter URLs one by one. You can also link to or upload a text file with a list of URLs
- `includeSearchTerms` (`boolean`): If selected, a field will be added to each tweets about the search term that was used to find it.

**Media handling:**
- output `media`

**Thread/conversation support:** mentioned in docs

### apidojo/twitter-replies-scraper
- **Title:** Fast Twitter (X) Replies Scraper API
- **Apify URL:** https://apify.com/apidojo/twitter-replies-scraper
- **Popularity:** 10936 runs, 145 users, 0 rating (0 reviews)
- **Pricing:** PAY_PER_EVENT dataset-item

**Input schema highlights:**
- `startUrls` (`array`): Twitter (X) URLs. Required if tweetIds is empty.
- `tweetIds` (`array`): Tweet IDs that you want to get replies on Twitter (X). Required if startUrls is empty.
- `useSearch` (`boolean`): Determines whether reply fetching should use the search-based flow instead of the default replies flow.
- `maxItems` (`integer`): Maximum number of items that you want as output.
- `customMapFunction` (`string`): Function that takes each of the objects as argument and returns data that will be mapped by the function itself.

**Media handling:**
- output `media`

**Thread/conversation support:** mentioned in docs

### danek/twitter-scraper
- **Title:** Twitter Scraper
- **Apify URL:** https://apify.com/danek/twitter-scraper
- **Popularity:** 52699513 runs, 7930 users, 4.9754952893871485 rating (15 reviews)
- **Pricing:** PAY_PER_EVENT $0.00028/item (BRONZE)

**Input schema highlights:**
- `username` (`string`): Twitter username (those with @) to scrape
- `query` (`string`): Query to search
- `search_type` (`string`): Type of search
- `country` (`string`): Country to check trends.
- `post_id` (`string`): Post id to scrape response
- `lookup_post_ids` (`array`): Post ids to scrape details
- `max_posts` (`integer`): Number of posts to scrape. For free users is set to 20

**Media handling:**
- —

**Thread/conversation support:** no explicit fields

### xquik/x-tweet-scraper
- **Title:** X Tweet Scraper | $0.00015/Tweet | Pay-Per-Result
- **Apify URL:** https://apify.com/xquik/x-tweet-scraper
- **Popularity:** 3928643 runs, 4120 users, 4.548815409398021 rating (14 reviews)
- **Pricing:** PAY_PER_EVENT $0.00015/item (BRONZE)

**Input schema highlights:**
- `startUrls` (`array`): Add Tweet, profile, search, or List URLs as strings or {"url":"..."} objects. Profile URLs may use /with_replies, /media, or best-effort /likes. Tweet URL batches recheck unresolved IDs once after partial responses. Example: ["https://x.com/elonmusk", "https://x.com/search?q=AI"]
- `twitterContent` (`string`): Search query using X advanced search syntax. Supports keywords, hashtags, exact phrases, boolean operators, and date or unix-time windows. The Actor verifies each returned tweet against requested time bounds. Example: web scraping OR #datascience
- `searchTerms` (`array`): Run multiple searches in one Actor run. Max Items applies across the run. Compatible account date windows share one bounded retrieval. Recent windows combine the profile timeline with author search. Historical windows use exact search. The Actor verifies raw date and unix-time operators before adding results. Example: from:elonmusk AI, #bitcoin lang:en
- `twitterHandles` (`array`): X usernames for profile timelines and author search. Profile Tweets matches the Posts tab on X: posts, reposts & the author's replies to their own posts. Add Exclude replies under Tweet type filters for original posts only. Profile With Replies keeps target-authored posts and replies. Add usernames with or without @. Example: elonmusk, @nasa
- `profileUrls` (`array`): Alias for Start URLs. Add profile URL strings or {"url":"..."} objects. Auto-route and profile modes combine the profile timeline with author search.
- `tweetIds` (`array`): Tweet IDs to look up directly. Other sources in the same input run too, and Max Items applies across the run. Process up to 10,000 tweet IDs per run. Chunks of 100 run concurrently. Partial responses recheck unresolved IDs once. Example: 1846987139428634858
- `listIds` (`array`): X list IDs to scrape through the dedicated list route. This is usually much faster than pasting list URLs into Start URLs or using the List ID search filter below. Example: 1748648376080666720
- `mode` (`string`): Auto-route selects a route from the input. Choose a mode to force one route. Profile Tweets combines the timeline with author search & matches the Posts tab on X: posts, reposts & the author's replies to their own posts. Profile With Replies keeps target-authored posts and replies. Tweet modes without Tweet IDs use Search when query input is present.
- `maxItems` (`integer`): Optional result cap across the whole run. Leave empty to use your Apify max total charge as the result limit when set. Without a spend cap, Xquik uses its built-in default. The Apify pricing box shows the current per-result price before the run starts. Diagnostic rows count toward this cap. The form starts at 1,000. A run can return 100,000 rows & more, so raise it for a full export.
- `maxItemsPerTarget` (`integer`): Optional cap for each target in multi-target modes.
- `queryType` (`string`): Latest returns newest first. Top is relevance-ranked and not exhaustive. Latest + Top runs both passes concurrently, deduplicates before billing, and backfills unused capacity from either pass. Account timelines ignore this setting.
- `content` (`object`): Build content filters without writing X search syntax.
- `users` (`object`): Optional structured author, reply, mention, and list filters.
- `time` (`object`): Optional structured time filters.
- `engagement` (`object`): Optional structured engagement filters.
- `media` (`object`): Optional structured media filters.
- `lang` (`string`): Filter tweets by language using a 2-letter ISO 639-1 code. The Actor verifies returned tweets and continues paging past mismatches.
- `tweetTypes` (`object`): Optional tweet type filters. Include only one type, or exclude replies, reposts or quote tweets.
- `geo` (`object`): Optional structured location filters.
- `cards` (`object`): Optional structured card filters.
- `sources` (`object`): Optional structured source filters.
- `conversation_id` (`string`): Only include tweets belonging to this conversation thread. Use the first tweet's ID in the thread.
- `conversationIds` (`array`): Alias for one or more conversation_id searches.
- `quoted_tweet_id` (`string`): Only include tweets that quote this specific tweet ID.
- `quoted_user_id` (`string`): Only include tweets that quote any tweet from this user ID.
- `filter:has_engagement` (`boolean`): Only include tweets with at least one like, retweet, or reply.
- `include:nativeretweets` (`boolean`): Include native retweets in results (excluded by default).
- `filter:twimg` (`boolean`): Only include tweets containing twimg.com images.
- `filter:native_video` (`boolean`): Only include tweets with natively uploaded video.
- `filter:vine` (`boolean`): Only include tweets with Vine videos.
- `filter:consumer_video` (`boolean`): Only include tweets with consumer-uploaded video.
- `filter:pro_video` (`boolean`): Only include tweets with professionally produced video.
- `filter:spaces` (`boolean`): Only include tweets containing a Spaces link.
- `filter:mentions` (`boolean`): Only include tweets containing @mentions.
- `filter:hashtags` (`boolean`): Only include tweets containing hashtags.
- `outputVariant` (`string`): Legacy preserves compatibility. Rich adds normalized public fields. Raw snapshot also adds a sanitized source snapshot. Compact and Full are Legacy aliases.
- `fieldStyle` (`string`): Controls top-level and nested field names for rich and raw results, including reply diagnostics. Use camelCase for JavaScript and TypeScript. Use snake_case for Python, SQL, CSV, and warehouses. Legacy output ignores this setting. Raw snapshots keep source names. Dataset views select columns only. They do not rename data.
- `outputPreset` (`string`): Nested preserves the current object shape. Flat + nested also adds CSV-friendly author and media URL fields.
- `includeSearchTerms` (`boolean`): Attach the first matching search term as `searchTerm` on each unique Tweet. Use it to identify which query produced each deduplicated result.
- `respectProfileSubpages` (`boolean`): Honor profile subpage paths such as /with_replies, /media, and /likes when routing profile URLs. /with_replies returns target-authored posts and replies. The Actor excludes conversation context from other authors.
- `articleTweetIds` (`array`): Tweet IDs to read with mode article.
- `replyTweetIds` (`array`): Tweet IDs whose direct replies to collect. The Actor combines 5 authenticated views, 3 ranking modes, every forward cursor module, labeled hidden-content branches, Top time partitions, and search. Nested replies never count as direct. Incomplete targets add a detailed diagnostic when capacity remains. Real replies always take priority.
- `quoteTweetIds` (`array`): Tweet IDs to read with mode quotes.
- `threadTweetIds` (`array`): Tweet IDs to read with mode thread.
- `retweeterTweetIds` (`array`): Tweet IDs to read with mode retweeters.
- `favoriterTweetIds` (`array`): Tweet IDs to read with mode favoriters. X may only expose liking users for eligible or owner-visible posts. If no users are available, the actor returns one diagnostic row.
- `from` (`string`): Only include tweets sent by this username (without the @ symbol). Example: elonmusk
- `to` (`string`): Only include tweets that are replies to this username (without @). Example: OpenAI
- `@` (`string`): Only include tweets that mention this username (without @). Example: Google
- `since` (`string`): Only include verified tweets on or after this date. Format: YYYY-MM-DD_HH:MM:SS_UTC. Example: 2026-01-01_00:00:00_UTC
- `until` (`string`): Only include verified tweets before this date. Same format as Since Date. Example: 2026-04-01_00:00:00_UTC
- `since_time` (`string`): Only include verified tweets on or after this unix timestamp (seconds). Example: 1704067200
- `until_time` (`string`): Only include verified tweets before this unix timestamp (seconds). Example: 1711929600
- `within_time` (`string`): Only include tweets from the last N time units. Example: 1d (1 day), 12h (12 hours), 30m (30 minutes), 60s (60 seconds)
- `since_id` (`string`): Only include tweets with an ID greater than (posted after) this tweet ID.
- `max_id` (`string`): Only include tweets with an ID less than (posted before) this tweet ID.
- `min_faves` (`integer`): Only include tweets with at least this many likes. Set to 0 to disable.
- `-min_faves` (`integer`): Only include tweets with at most this many likes. Set to 0 to disable.
- `min_retweets` (`integer`): Only include tweets with at least this many retweets. Set to 0 to disable.
- `-min_retweets` (`integer`): Only include tweets with at most this many retweets. Set to 0 to disable.
- `min_replies` (`integer`): Only include tweets with at least this many replies. Set to 0 to disable.
- `-min_replies` (`integer`): Only include tweets with at most this many replies. Set to 0 to disable.
- `filter:blue_verified` (`boolean`): Only include tweets from X Premium (Blue) verified accounts.
- `filter:nativeretweets` (`boolean`): Only include native retweets.
- `filter:replies` (`boolean`): Only include reply tweets.
- `filter:quote` (`boolean`): Only include quote tweets.
- `filter:media` (`boolean`): Apply X's media search operator. Results usually include attached media, but X can also match media-like card content.
- `filter:images` (`boolean`): Apply X's image search operator. Results usually include image media. X can also match card or link image content.
- `filter:videos` (`boolean`): Apply X's video search operator. Results usually include native video media.
- `filter:links` (`boolean`): Only include tweets containing external links.
- `filter:news` (`boolean`): Only include tweets containing news article links.
- `filter:safe` (`boolean`): Only include tweets marked as safe (excludes sensitive content).
- `near` (`string`): Only include tweets geotagged near this place. Example: San Francisco
- `within` (`string`): Radius for the Near Place filter. Format: integer + unit (km or mi), no spaces. Example: 10km, 25mi
- `geocode` (`string`): Filter by exact coordinates in lat,long,radius format. Use no spaces. Give the radius in km or mi. Example: 37.7749,-122.4194,10km
- `list` (`string`): Filter search results to Tweets from members of this X List. Use List IDs unless you need to combine this filter with other search operators.
- `url` (`string`): Only include tweets containing this URL or domain. Example: github.com
- `card_name` (`string`): Filter by poll or card type. Common values: poll2choice_text_only, poll3choice_text_only, poll4choice_text_only, poll2choice_image, poll3choice_image, poll4choice_image.
- `includeRaw` (`boolean`): API alias for Output Variant raw.
- `includeArticles` (`boolean`): Deprecated compatibility input. Article data is already included when X provides it.
- `includeUnavailableFields` (`boolean`): Deprecated compatibility input. Safe availability fields are already included when X provides them.
- `includeOriginalTweet` (`boolean`): Deprecated compatibility input. Fetch source tweets separately with Tweet IDs.

**Media handling:**
- input `profileUrls`; input `media`; input `filter:native_video`; input `filter:consumer_video`; input `filter:pro_video`; input `respectProfileSubpages`; input `filter:media`; input `filter:images`; input `filter:videos`; output `media`; output `mediaUrls`; output `imageUrls`; output `videoUrls`; mentions mp4; video variants

**Thread/conversation support:** yes (`conversation_id`, `conversationIds`, `threadTweetIds`, `min_replies`, `-min_replies`, `filter:replies`)

### scraping_solutions/twitter-x-scraper-post-timeline-search-replies
- **Title:** Twitter (X) Scraper post (timeline / # / search / replies)
- **Apify URL:** https://apify.com/scraping_solutions/twitter-x-scraper-post-timeline-search-replies
- **Popularity:** 4318 runs, 547 users, 0 rating (0 reviews)
- **Pricing:** PAY_PER_EVENT $0.00095/item (BRONZE)

**Input schema highlights:**
- `TypeScraper` (`string`): choose type scraper
- `Input_Search` (`array`): Add a list of Posts/usernames/hashtags/tweet_id You can add them one per line.
- `filter` (`string`): Query Type, support Latest,Top,Photos,Videos
- `resultsLimit` (`integer`): number of engagers for scraping, 1-200 are the allowed values

**Media handling:**
- —

**Thread/conversation support:** mentioned in docs

### pratikdani/twitter-posts-scraper
- **Title:** Twitter Posts Scraper
- **Apify URL:** https://apify.com/pratikdani/twitter-posts-scraper
- **Popularity:** 438357 runs, 846 users, 1 rating (3 reviews)
- **Pricing:** PAY_PER_EVENT $0.02/item (BRONZE)

**Input schema highlights:**
- `url` (`string`): URL of the Twitter post to scrape

**Media handling:**
- —

**Thread/conversation support:** no explicit fields

### clappi/x-twitter-post-scraper
- **Title:** X / Twitter Post Scraper
- **Apify URL:** https://apify.com/clappi/x-twitter-post-scraper
- **Popularity:** 6686 runs, 104 users, 0 rating (0 reviews)
- **Pricing:** PAY_PER_EVENT $0.0033/item (GOLD)

**Input schema highlights:**
- `postUrls` (`array`): List of X (Twitter) post URLs to scrape.
- `proxyConfiguration` (`object`): Optional proxy settings.

**Media handling:**
- output `media`

**Thread/conversation support:** no explicit fields

### calm_builder/twitter-posts-scraper
- **Title:** X / Twitter Post Scraper
- **Apify URL:** https://apify.com/calm_builder/twitter-posts-scraper
- **Popularity:** 1935 runs, 54 users, 0 rating (0 reviews)
- **Pricing:** PAY_PER_EVENT $0.00083/item (BRONZE)

**Input schema highlights:**
- `postUrls` (`array`): Add one or more public X post links to scrape. Supported formats include x.com and twitter.com status URLs (for example, https://x.com/username/status/1234567890).
- `flattenOutput` (`boolean`): When enabled, each result is a clean, user-friendly post record with normalized fields (text, media, metrics, author, and context). When disabled, each result is a readable detailed record with extra tweet and media fields (reply metadata, grouped media with video variants, link card details, and expanded author profile data).
- `includeAuthorProfile` (`boolean`): When enabled, the Actor fetches public profile details for each post author (such as bio, follower counts, verification status, avatar, and profile links) and attaches them to the corresponding post result. Each unique author handle is fetched at most once per run, even if multiple input URLs belong to the same account.

**Media handling:**
- input `includeAuthorProfile`; output `media`; video variants

**Thread/conversation support:** no explicit fields

### scraper_one/x-profile-posts-scraper
- **Title:** X (Twitter) Profile Posts Scraper
- **Apify URL:** https://apify.com/scraper_one/x-profile-posts-scraper
- **Popularity:** 330297 runs, 2858 users, 4.344082316026647 rating (8 reviews)
- **Pricing:** PAY_PER_EVENT $0.0004/item (BRONZE)

**Input schema highlights:**
- `profileUrls` (`array`): List of profile URLs to process. Note: Free-plan users can process up to 5 profile URLs per run.
- `resultsLimit` (`integer`): Maximum number of posts to retrieve per profile URL. If not set, only a few of the first posts will be returned. Note: Free-plan users can retrieve up to 100 posts per profile URL.
- `skipPinnedPosts` (`boolean`): If true, the pinned posts will be skipped

**Media handling:**
- input `profileUrls`; output `media`

**Thread/conversation support:** mentioned in docs

### automation-lab/twitter-scraper
- **Title:** Twitter/X Scraper: Tweets, Profiles & Search
- **Apify URL:** https://apify.com/automation-lab/twitter-scraper
- **Popularity:** 47087 runs, 1319 users, 4.999999999999999 rating (3 reviews)
- **Pricing:** PAY_PER_EVENT $0.0027/item (BRONZE)

**Input schema highlights:**
- `mode` (`string`): Select what to scrape from Twitter/X.
- `usernames` (`array`): Enter Twitter/X usernames for profile, user-tweets, followers, or following modes. @ is optional; examples: elonmusk or @elonmusk.
- `tweetUrls` (`array`): Enter tweet URLs (https://x.com/user/status/123 or https://twitter.com/user/status/123) or numeric tweet IDs.
- `searchTerms` (`array`): Enter search terms or Twitter advanced search queries. Supports operators like from:user, since:2024-01-01, min_faves:100, filter:media, lang:en.
- `searchMode` (`string`): Sort search results by relevance (Top) or chronologically (Latest).
- `maxResults` (`integer`): Maximum number of results to return per query/username in user-tweets, search, followers, and following modes.
- `twitterCookie` (`string`): Required for search, followers, and following modes; recommended for tweets-by-URL. Paste cookies in this format: auth_token=YOUR_TOKEN; ct0=YOUR_CT0. Get them from browser DevTools → Application → Cookies → x.com.

**Media handling:**
- output `mediaUrls`

**Thread/conversation support:** mentioned in docs

### xtdata/twitter-x-scraper
- **Title:** X.com Twitter API Scraper
- **Apify URL:** https://apify.com/xtdata/twitter-x-scraper
- **Popularity:** 263348 runs, 3045 users, 4.26431385843754 rating (3 reviews)
- **Pricing:** PAY_PER_EVENT $0.0008/item (BRONZE)

**Input schema highlights:**
- `startUrls` (`array`): Twitter (X) URLs. Paste the URLs and get the results immediately. Tweet, Profile, Search or List URLs are supported.
- `searchTerms` (`array`): Search terms you want to search from Twitter (X). You can refer to https://github.com/igorbrigadir/twitter-advanced-search.
- `twitterHandles` (`array`): Twitter handles (username) that you want to search on Twitter (X)
- `maxItems` (`integer`): Maximum number of items that you want as output.
- `sort` (`string`): Sorts search results by the given option. If you are getting low results, try Top instead of Latest. Latest + Top runs both simultaneously to maximize results but may return some duplicate tweets.
- `tweetLanguage` (`string`): Restricts tweets to the given language, given by an ISO 639-1 code.
- `onlyVerifiedUsers` (`boolean`): If selected, only returns tweets by users who are verified.
- `onlyTwitterBlue` (`boolean`): If selected, only returns tweets by users who are Twitter Blue subscribers.
- `onlyImage` (`boolean`): If selected, only returns tweets that contain images.
- `onlyVideo` (`boolean`): If selected, only returns tweets that contain videos.
- `onlyQuote` (`boolean`): If selected, only returns tweets that are quotes.
- `start` (`string`): Returns tweets sent after the given date. Does not apply to startUrls or twitterHandles. If you want to filter by date, the best way is to use Twitter queries.
- `end` (`string`): Returns tweets sent before the given date. Does not apply to startUrls or twitterHandles. If you want to filter by date, the best way is to use Twitter queries.
- `includeSearchTerms` (`boolean`): If selected, a field will be added to each tweets about the search term that was used to find it.
- `customMapFunction` (`string`): Function that takes each of the objects as argument and returns data that will be mapped by the function itself. This function is not intended for filtering, please don't use it for filtering purposes or you will get banned automatically.

**Media handling:**
- input `onlyImage`; input `onlyVideo`

**Thread/conversation support:** mentioned in docs

---
## Gaps the x2md Actor fills, and conventions to match
### What competitors do (conventions buyers expect)
1. **Input format:** Almost all actors accept `startUrls` with one or more X/Twitter post URLs. Some also accept bare `tweetIds`/`conversationIds` or `twitterHandles`. Batch sizes are controlled by `maxItems`/`maxResults`/`resultsLimit`.
2. **Per-item output:** A JSON row per post with `id`/`tweet_id`, `url`, `text`/`fullText`, `created_at`, engagement counts, `author`, and a `media` array. Flattened variants (xquik) also provide `mediaUrls`, `imageUrls`, and `videoUrls`.
3. **Media handling:** Competitors overwhelmingly return **public media URLs only** (e.g. `pbs.twimg.com` image URLs or thumbnail URLs for videos). None of the surveyed actors upload original-resolution images or video/GIF source files into the Apify dataset/key-value store as downloadable files. Video support is typically a thumbnail or a list of URLs; only `calm_builder/twitter-posts-scraper` advertises 'video variants' when flattening is disabled. xquik offers a *separate* 'X Media Downloader' actor for users who need the actual files.
4. **Threads:** Thread/conversation enumeration is usually a side effect of accepting a `startUrls` post URL or a `conversationIds`/`tweetIds` list; some actors (danek, clappi, pratikdani) are strictly single-post or search oriented and do not enumerate self-threads.
5. **Pricing/limits:** Pricing is almost always **pay-per-result** (PAY_PER_EVENT / PRICE_PER_DATASET_ITEM) with a free tier and tiered volume discounts. Limits are expressed as `maxItems` per run.
### Gaps x2md can own
1. **Markdown document as first-class output:** All surveyed actors emit structured JSON rows. None emit a ready-to-use Markdown document with YAML front matter, rendered body, and media references.
2. **Self-thread enumeration via fxtwitter:** Most competitors rely on the same public endpoints; self-thread support is incidental or profile/search-based. x2md's fxtwitter-backed self-thread enumeration can be exposed as a distinct, reliable mode.
3. **Original-resolution images + mp4 source files:** The biggest functional gap. Competitors return media URLs; x2md can upload the actual original-resolution images and video/GIF mp4 sources to the Apify dataset or key-value store, optionally as a ZIP, matching the existing web-app behavior.
4. **Article support:** None of the surveyed post-scraper actors mention rendering X Articles; x2md already handles long-form Articles.
5. **No auth / no Twitter account required:** Shared with the no-auth competitors, but worth calling out.
### Conventions to match so buyers can compare directly
- **Input:** Accept a list of X/Twitter post URLs (and optionally bare numeric IDs) under `startUrls`/`urls`, with a `maxItems`/`maxResults` cap and an optional `includeMediaFiles`/`downloadMedia` boolean.
- **Output row:** Provide standard per-post JSON fields (`id`, `url`, `text`, `author`, `createdAt`, engagement, `media`). Add `markdown` and `markdownFile` fields for the rendered document.
- **Media output naming:** If uploading files, use deterministic filenames (`<handle>_<postid>_p<index>.<ext>`) and include both individual file URLs and a ZIP archive, mirroring x2md's current web app.
- **Pricing:** Adopt pay-per-result pricing, priced per converted post/thread/Article, with a clear free tier.
- **Thread mode:** Expose `enumerateThreads` or `mode: 'thread'` so buyers can directly compare thread depth and completeness.
## Uncertain / unverified
- Findings were inferred from actor metadata and READMEs; no live runs were performed to confirm video/GIF variant selection, thumbnail URLs, alt text, or exact media file resolution.
- The exact video source URL quality/selection logic for competitors could not be confirmed without live runs.
- Some actors (e.g., xquik) point to a separate 'Media Downloader' actor; that actor was not surveyed in depth.
- Apify platform limits (free tier compute units, run duration, dataset size) were not checked; only actor-level pricing was extracted.