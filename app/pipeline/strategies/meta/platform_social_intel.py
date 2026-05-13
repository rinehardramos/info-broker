"""Platform & Social Intelligence meta-strategy module."""

NAME = "platform_social_intel"
DISPLAY_NAME = "Platform & Social Intelligence"
DESCRIPTION = "Social graph analysis, cross-platform identity, CIB/sock puppet detection, behavioral signals, advertising intel."
TRIGGER_SIGNALS = [
    "social media", "facebook", "instagram", "twitter", "tiktok", "linkedin",
    "reddit", "telegram", "influencer", "online presence", "digital footprint",
    "platform", "audience", "followers", "community", "viral",
]
ENTITY_TYPES = ["person", "company", "lead"]
ALWAYS_ON = False

STRATEGY_TEXT = """
=== PLATFORM & SOCIAL INTELLIGENCE META-STRATEGY ===

SOCIAL_GRAPH_ANALYSIS:
  engagement network > follow network; weak ties (bridge connections) = higher intel value than strong ties
  for target: enumerate 2nd-degree LinkedIn connections; >=5 mutuals + tenure overlap = likely real relationship

IDENTITY_GRAPH:
  deterministic (high confidence): shared email/phone/recovery account across platforms = same identity
  probabilistic (require >=3 signals): same avatar (run_face_search) | same bio verbatim | same username variant (run_username_enumerator) | same circadian pattern | same linguistic fingerprint
  rule: never merge on name similarity alone

CROSS_PLATFORM_GEOGRAPHY:
  Viber/Facebook=PH | Zalo=VN | WeChat=CN diaspora | VK/OK=RU/FSU | Telegram=IR/RU/UA/crypto | KakaoTalk=KR | LINE=JP/TW/TH | Snapchat=Gulf
  tools: run_username_enumerator (9+ platforms) | run_messaging_check (messaging presence)

CIB_DETECTION [canonical home]: Flag as CIB when >=3 of 5 dimensions show coordination:
  1. IDENTITY: account creation clustering | stolen profile photos (run_face_search) | follower graph anomalies
  2. CONTENT: same post within 5-minute window | content Jaccard similarity
  3. BEHAVIOR: uniform circadian posting pattern (timezone leak) | abnormally uniform activity
  4. NETWORK: tight bipartite follow/engage clustering
  5. INFRASTRUCTURE: shared phone/email/recovery | IP co-occurrence
  tools: run_username_enumerator + run_reverse_lookup + run_face_search; cluster low-authenticity accounts

SOCK_PUPPET_DETECTION [canonical home]:
  signals: account creation clustering | circadian timezone leak | pHash avatar match (run_face_search) | bio text similarity | username variant | behavioral lockstep
  merge threshold: one deterministic link (shared email/phone) OR >=3 independent probabilistic signals

BEHAVIORAL_COMPLETION:
  weight: Save=strong interest | Share=strongest (stakes identity) | Comment=engagement | Watch-completion=strongest latent | Like=weak

ADVERTISING_INTEL:
  Meta Ad Library (facebook.com/ads/library): active ads, creative volume, geo targeting, spend ranges (free)
  high creative variant + frequent rotation = sophisticated optimization = well-funded campaign
  Google Ads Transparency (ads.google.com/transparency) | TikTok Creative Center — both free

INFLUENCE_OP_GRAPH: Propagation graph — who amplifies whom. Seed nodes = low in-degree, high out-degree to influential nodes.
  temporal lockstep: multiple accounts same content within 60s = coordination
  dark social: sudden reshare burst from disconnected accounts with no visible public seed = private channel amplification

PLATFORM_INTEL:
  Telegram (public channels): scrapable; dominant IR/RU/UA/crypto/extremism
  Reddit: consumer sentiment, developer tool adoption; subreddit delta alerts on negative shifts
  GitHub: contributor co-occurrence = employer-OSS links; commit cadence = engineering health; fork network = adoption signal
  LinkedIn: hiring/attrition = quarterly-leading indicator for company performance
"""
