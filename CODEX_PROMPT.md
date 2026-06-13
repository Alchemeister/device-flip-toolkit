# Codex Task: Device Flip Toolkit

Build a complete Python toolkit for sourcing, analyzing, and listing cracked/broken devices for repair-and-resell profit. This is a real business — the user flips phones, tablets, and laptops with cracked screens.

## Core Deliverables

### 1. Multi-Source Deal Finder (`deal_finder.py`)
Scrape/search these sources for cracked/broken devices matching target models:
- **eBay** — search for "cracked screen", "for parts", "broken glass" on target models. Filter by auction ending soonest, Buy It Now under max price. Parse sold listings for pricing data.
- **Facebook Marketplace** — search local listings (Lafayette, LA area). Parse price, condition keywords.
- **OfferUp** — search for target models with damage keywords.
- **Mercari** — search for cracked/broken devices.
- **Swappa** — check boneyard listings for target models.

For each source, output: device model, price, condition notes, source link, whether it passes the buy filter.

### 2. ROI Calculator Grid (`roi_grid.py`)
A CLI tool that prints a formatted profitability grid for all target devices. Must include:

**Phones:**
- iPhone 12 (128GB): buy $140-190, kit $35, sell $280-340, profit ~$110, difficulty Easy
- iPhone 13 (128GB): buy $200-260, kit $40, sell $340-420, profit ~$110, difficulty Easy
- iPhone 13 Pro: buy $280-350, kit $55, sell $450-550, profit ~$130, difficulty Medium
- iPhone 14 (128GB): buy $300-370, kit $50, sell $430-520, profit ~$90, difficulty Easy
- Galaxy S22: buy $120-170, kit $60, sell $250-310, profit ~$75, difficulty Medium
- Galaxy S23: buy $180-240, kit $70, sell $320-390, profit ~$75, difficulty Medium

**Tablets:**
- iPad 9th Gen: buy $100-150, kit $25, sell $200-250, profit ~$75, difficulty Medium
- iPad Air 4th Gen: buy $180-240, kit $40, sell $320-400, profit ~$110, difficulty Medium
- iPad Pro 11" (2018/2020): buy $250-350, kit $60, sell $450-550, profit ~$90, difficulty Hard

**Laptops:**
- MacBook Air M1 (2020): buy $300-400, kit $150, sell $550-700, profit ~$125, difficulty Hard
- Dell XPS 15 (9510): buy $300-400, kit $90, sell $650-800, profit ~$285, difficulty Medium
- ThinkPad X1 Carbon Gen 9: buy $250-350, kit $80, sell $500-650, profit ~$170, difficulty Medium
- HP Spectre x360 14: buy $250-350, kit $100, sell $500-650, profit ~$150, difficulty Medium

Grid should show: device name, buy range, kit cost, sell range, avg profit, ROI%, difficulty, time estimate. Sortable by any column. Color-coded by profit tier (green >$100, yellow $50-100, red <$50).

### 3. AI Listing Generator (`listing_generator.py`)
Takes device specs + condition + photo paths as input. Uses a local LLM (Ollama) to generate:
- eBay title with SEO keywords (max 80 chars)
- Condition description (honest but sells — mentions the repair, emphasizes what's good)
- Full item specifics (brand, model, storage, color, carrier, condition)
- Suggested BIN price based on current market data
- Caveats/disclaimers to protect seller

Output as a ready-to-paste eBay listing.

### 4. Buy Filter / Deal-Killer Checker (`buy_filter.py`)
Before buying, check for deal-killers:
- iCloud/activation lock (parse listing text for keywords)
- Face ID status (if mentioned as broken, flag and adjust max bid down $50)
- Battery health (if <85%, add $20 to cost estimate)
- Carrier lock status (flag financed/Sprint-locked as avoid)
- Back glass damage (if also cracked, add $25 cost + 60min time)
- Water damage indicators (if mentioned, flag as avoid)

Output: PASS/FAIL with reasoning and adjusted max bid.

### 5. Profit Tracker (`profit_tracker.py`)
Simple SQLite database to track:
- Device bought (model, price, source, date)
- Repair cost (parts, time spent)
- Sold price, platform, date
- Net profit
- Notes/lessons learned

CLI to add entries and print summary stats (total profit, avg margin, best/worst flips, profit per hour).

## Architecture Requirements
- All scripts should be standalone CLI tools with argparse
- Use `rich` library for formatted terminal output (tables, colors)
- Use `httpx` or `requests` for web scraping
- Use `beautifulsoup4` for HTML parsing
- Use `sqlite3` (stdlib) for profit tracker
- Use Ollama Python client for AI listing generator
- Configuration via `config.yaml` (target models, max buy prices, location for FB Marketplace)
- Requirements in `requirements.txt`
- README.md with setup instructions and usage examples

## AI Integration Ideas (implement if feasible)
- **Photo damage assessment**: feed listing photos to Ollama vision model to detect hidden damage (dents, back cracks, water indicators) that sellers don't mention
- **Market trend detection**: scrape sold listings weekly, detect if a model's resale price is trending up/down, adjust buy prices accordingly
- **Auto-negotiation drafts**: for FB Marketplace/OfferUp, generate negotiation messages based on listed flaws
- **Competitor analysis**: track what other refurb sellers are pricing at, flag if you're under/over market

## Optimizations to Consider
- Bulk parts ordering discounts (InjuredGadgets, MobileSentrix wholesale accounts)
- Seasonal pricing patterns (phones drop before new iPhone launch, spike during holidays)
- Cross-listing automation (list on eBay + Mercari + FB simultaneously)
- Shipping cost optimization (PirateShip vs eBay labels)
- Tax automation (track expenses, generate quarterly summary for Schedule C)

## Important Notes
- User is in Lafayette, Louisiana (CST)
- User is disabled — all work is from home
- Starting capital is small — focus on single-device flips first
- Target profit per flip: $75-150
- Target time per repair: 30-60 minutes
- No heat gun needed for iPhone repairs (suction cup + pick method)
- Aftermarket screens are fine — don't chase OEM premium for now
- eBay fees are ~13% — factor into all sell price calculations

Build everything in `/root/device-flip-toolkit/`. Make it production-quality, not a prototype. The user is starting a real business with this.
