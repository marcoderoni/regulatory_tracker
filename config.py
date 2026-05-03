"""
config.py — Central configuration.
Loads from .env and defines all sources, scraping targets, and feature flags.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Resend (email) ────────────────────────────────────────────────────────────
RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM      = os.getenv("EMAIL_FROM", "regulatory@yourdomain.com")
EMAIL_TO        = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]

# ── Slack ─────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL  = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_DIGEST_URL   = os.getenv("SLACK_DIGEST_URL", "")

# ── Notion ────────────────────────────────────────────────────────────────────
NOTION_API_KEY   = os.getenv("NOTION_API_KEY", "")
NOTION_DB_ID     = os.getenv("NOTION_DB_ID", "")

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Tracker behaviour ─────────────────────────────────────────────────────────
DB_PATH            = Path(os.getenv("DB_PATH", "tracker.db"))
LOOKBACK_DAYS      = int(os.getenv("LOOKBACK_DAYS", 7))
MIN_RELEVANCE      = int(os.getenv("MIN_RELEVANCE", 3))
INSTANT_ALERT_MIN  = int(os.getenv("INSTANT_ALERT_MIN", 8))
DAILY_RUN_TIME     = os.getenv("DAILY_RUN_TIME", "07:30")
WEEKLY_REPORT_DAY  = os.getenv("WEEKLY_REPORT_DAY", "friday")

# ── Topic focus ───────────────────────────────────────────────────────────────
TOPIC_FOCUS = ["AI Act", "DORA", "Data Act", "NIS2"]

# ── Keyword filter ────────────────────────────────────────────────────────────
KEYWORD_FILTER: list[str] = [
    "AI Act", "artificial intelligence act", "AI Office", "GPAI",
    "general purpose AI", "prohibited AI", "high-risk AI", "AI system",
    "conformity assessment", "notified body",
    "DORA", "digital operational resilience", "ICT risk", "ICT incident",
    "threat-led penetration", "TLPT", "critical ICT",
    "Data Act", "data sharing", "data access", "switching provider",
    "IoT data", "smart contract", "data intermediary",
    "NIS2", "NIS 2", "network and information security", "incident notification",
    "essential entities", "important entities", "CSIRT",
    "GDPR", "data protection", "personal data", "DPA", "supervisory authority",
    "data breach", "data transfer", "SCCs", "adequacy",
    "enforcement", "fine", "penalty", "consultation", "guidelines",
    "regulatory technical standard", "RTS", "ITS", "delegated regulation",
]

# ── Regulation taxonomy ───────────────────────────────────────────────────────
REGULATIONS = [
    "GDPR", "AI Act", "DORA", "NIS2", "ePrivacy", "Data Act",
    "Cyber Resilience Act", "FIDA", "PSD3 / PSR", "AML Package",
    "Digital Markets Act", "Digital Services Act", "Other",
]

# ── RSS Sources ───────────────────────────────────────────────────────────────
SOURCES = [
    dict(name="EUR-Lex — OJ L (binding legislation)",
         rss_url="https://eur-lex.europa.eu/RSSBYTYPE/OJ_L.xml",
         category="EU Legislation", jurisdiction="EU", tags_hint=[]),
    dict(name="EUR-Lex — OJ C (opinions, communications)",
         rss_url="https://eur-lex.europa.eu/RSSBYTYPE/OJ_C.xml",
         category="EU Legislation", jurisdiction="EU", tags_hint=[]),
    dict(name="EU Digital Strategy — AI Office",
         rss_url="https://digital-strategy.ec.europa.eu/en/news/rss.xml",
         category="AI Regulation", jurisdiction="EU", tags_hint=["AI Act"]),
    dict(name="European Parliament — Top Stories",
         rss_url="https://www.europarl.europa.eu/rss/doc/top-stories/en.xml",
         category="AI Regulation", jurisdiction="EU", tags_hint=["AI Act"]),
    dict(name="EDPB",
         rss_url="https://www.edpb.europa.eu/news/news_en?_format=rss",
         category="Data Protection", jurisdiction="EU", tags_hint=["GDPR", "ePrivacy"]),
    dict(name="AP — Autoriteit Persoonsgegevens (NL)",
         rss_url="https://autoriteitpersoonsgegevens.nl/nl/rss.xml",
         category="Data Protection", jurisdiction="NL", tags_hint=["GDPR"]),
    dict(name="Garante Privacy (IT)",
         rss_url="https://www.garanteprivacy.it/rss",
         category="Data Protection", jurisdiction="IT", tags_hint=["GDPR"]),
    dict(name="CNIL (FR)",
         rss_url="https://www.cnil.fr/fr/rss.xml",
         category="Data Protection", jurisdiction="FR", tags_hint=["GDPR", "ePrivacy"]),
    dict(name="ICO (UK)",
         rss_url="https://ico.org.uk/about-the-ico/media-centre/rss-feed/",
         category="Data Protection", jurisdiction="UK", tags_hint=["GDPR"]),
    dict(name="BfDI (DE)",
         rss_url="https://www.bfdi.bund.de/SiteGlobals/Frontend/Bfdi/RSS/Presse_rss.xml",
         category="Data Protection", jurisdiction="DE", tags_hint=["GDPR"]),
    dict(name="EBA",
         rss_url="https://www.eba.europa.eu/rss/press-releases",
         category="Financial Regulation", jurisdiction="EU",
         tags_hint=["DORA", "PSD3 / PSR", "AML Package"]),
    dict(name="ESMA",
         rss_url="https://www.esma.europa.eu/press-news/esma-news?rss=true",
         category="Financial Regulation", jurisdiction="EU", tags_hint=["DORA"]),
    dict(name="ECB Banking Supervision",
         rss_url="https://www.bankingsupervision.europa.eu/press/publications/rss.en.rss",
         category="Financial Regulation", jurisdiction="EU", tags_hint=["DORA"]),
    dict(name="EIOPA",
         rss_url="https://www.eiopa.europa.eu/rss.xml",
         category="Financial Regulation", jurisdiction="EU", tags_hint=["DORA"]),
    dict(name="ENISA",
         rss_url="https://www.enisa.europa.eu/news/enisa-news/RSS",
         category="Cybersecurity", jurisdiction="EU",
         tags_hint=["NIS2", "Cyber Resilience Act", "DORA"]),
    dict(name="IAPP",
         rss_url="https://iapp.org/news/feed/",
         category="Legal News", jurisdiction="Global",
         tags_hint=["GDPR", "AI Act", "ePrivacy"]),
    dict(name="Bird & Bird — Tech, Media & Comms",
         rss_url="https://www.twobirds.com/en/news/rss?practice=technology-communications-and-media",
         category="Legal News", jurisdiction="Global",
         tags_hint=["GDPR", "AI Act", "DORA"]),
    dict(name="Fieldfisher — Privacy & Security Blog",
         rss_url="https://www.fieldfisher.com/en/services/privacy-security-and-information/privacy-security-and-information-law-blog/rss",
         category="Legal News", jurisdiction="Global", tags_hint=["GDPR"]),
    dict(name="Linklaters — Insights",
         rss_url="https://www.linklaters.com/en/insights/rss",
         category="Legal News", jurisdiction="Global",
         tags_hint=["GDPR", "DORA", "AI Act"]),
    dict(name="Osborne Clarke — Insights",
         rss_url="https://www.osborneclarke.com/insights/rss",
         category="Legal News", jurisdiction="Global",
         tags_hint=["GDPR", "AI Act", "NIS2"]),
]

# ── Scraping targets (sites without RSS) ─────────────────────────────────────
SCRAPE_TARGETS = [
    dict(
        name="EU AI Office — Publications",
        url="https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
        link_selector="article a, h3 a, h2 a",
        base_url="https://digital-strategy.ec.europa.eu",
        category="AI Regulation", jurisdiction="EU", tags_hint=["AI Act"],
    ),
    dict(
        name="DNB — De Nederlandsche Bank (NL)",
        url="https://www.dnb.nl/en/news/news-and-archive/",
        link_selector=".news-list__item a, h3 a",
        base_url="https://www.dnb.nl",
        category="Financial Regulation", jurisdiction="NL", tags_hint=["DORA"],
    ),
    dict(
        name="AFM — Authority Financial Markets (NL)",
        url="https://www.afm.nl/en/nieuws/",
        link_selector=".news-item a, h3 a",
        base_url="https://www.afm.nl",
        category="Financial Regulation", jurisdiction="NL", tags_hint=["DORA", "FIDA"],
    ),
    dict(
        name="NCSC-NL — Cybersecurity Centre",
        url="https://www.ncsc.nl/actueel/nieuws",
        link_selector="article a, h3 a",
        base_url="https://www.ncsc.nl",
        category="Cybersecurity", jurisdiction="NL", tags_hint=["NIS2"],
    ),
    dict(
        name="European Commission — Data Economy",
        url="https://ec.europa.eu/newsroom/dae/en/news/1",
        link_selector=".item-title a, h3 a",
        base_url="https://ec.europa.eu",
        category="EU Legislation", jurisdiction="EU", tags_hint=["Data Act", "AI Act"],
    ),
]
