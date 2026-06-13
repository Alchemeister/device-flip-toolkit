# Device Flip Toolkit

A complete Python toolkit for sourcing, analyzing, and listing cracked/broken phones, tablets, and laptops for repair-and-resell profit.

## Quick Start

```bash
pip install -r requirements.txt
```

## Tools

### 1. ROI Grid — `roi_grid.py`
Profitability analysis for all target devices. Shows buy/sell ranges, kit costs, profit, ROI%, difficulty, and time estimates.

```bash
# Show all devices sorted by profit
python roi_grid.py

# Sort by hourly rate, phones only
python roi_grid.py --sort hourly --type phones

# JSON output for piping to other tools
python roi_grid.py --json
```

### 2. Buy Filter — `buy_filter.py`
Scans a listing for deal-killers before you bid. Checks: iCloud lock, Face ID, battery health, carrier lock, back glass, water damage, frame damage, missing parts.

```bash
# Analyze a listing by pasting text
python buy_filter.py "iPhone 13" 220 --text "iPhone 13 128GB unlocked cracked screen only, Face ID works, battery 89%, clean IMEI"

# Analyze from a URL
python buy_filter.py "iPhone 13" 220 --url "https://www.ebay.com/itm/123456789"

# Analyze from a file
python buy_filter.py "iPhone 13" 220 --file listing.txt
```

### 3. Deal Finder — `deal_finder.py`
Scrapes eBay, Mercari, Swappa, and OfferUp for cracked/broken devices matching your target models. Scores deals 0-100 based on profitability and risk.

```bash
# Search all sources
python deal_finder.py

# eBay only, phones only, high-quality deals
python deal_finder.py --sources ebay --type phones --min-score 50

# Add a manually found deal (Facebook Marketplace, etc.)
python deal_finder.py --add-manual
```

### 4. AI Listing Generator — `listing_generator.py`
Uses local Ollama to generate complete eBay listings from device specs. Creates SEO-optimized titles, honest condition descriptions, item specifics, pricing, and seller protection caveats.

```bash
# Generate a listing (requires Ollama running)
python listing_generator.py "iPhone 13" --storage 128GB --color Midnight --carrier Unlocked --price 395

# Include photos for AI damage assessment
python listing_generator.py "iPhone 13" --photos phone1.jpg phone2.jpg

# Template mode (no AI required)
python listing_generator.py "iPhone 13" --no-ai
```

### 5. Profit Tracker — `profit_tracker.py`
SQLite database to track every flip from purchase to sale. Analytics on profit, ROI, hourly rate, best/worst flips, and per-model performance.

```bash
# Add a new purchase
python profit_tracker.py add "iPhone 13" 210 --source ebay --repair-cost 40

# Mark as sold
python profit_tracker.py sold 1 395 --platform ebay

# Update repair details
python profit_tracker.py update 1 --repair-cost 38 --repair-time 30 --status repairing

# View all flips
python profit_tracker.py list

# Show stats
python profit_tracker.py stats

# Export to CSV
python profit_tracker.py export
```

## Configuration

Edit `config.yaml` to customize:
- Target devices and their buy/sell ranges
- Repair kit costs and difficulty ratings
- Deal-killer thresholds (battery %, penalties)
- Location for local searches
- eBay fee percentages
- Ollama model settings

## AI Features (requires Ollama)

Install and start Ollama:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2
ollama pull llama3.2-vision  # for photo analysis
ollama serve
```

Then the listing generator and photo assessment will use your local GPU for free.

## Workflow

1. **Find deals:** `python deal_finder.py` — scan multiple sources
2. **Filter:** `python buy_filter.py "iPhone 13" <price> --url <listing>` — check for deal-killers
3. **Buy:** Purchase the device
4. **Track:** `python profit_tracker.py add "iPhone 13" <price>` — log the purchase
5. **Repair:** Order kit from MobileSentrix/InjuredGadgets, fix the screen
6. **List:** `python listing_generator.py "iPhone 13" --price <target>` — generate listing
7. **Sell:** List on eBay/Mercari/FB
8. **Track profit:** `python profit_tracker.py sold <id> <sell_price>`

## Sweet Spot Picks

| Device | Buy | Kit | Sell | Profit | Time |
|---|---|---|---|---|---|
| iPhone 13 (128GB) | ~$230 | $40 | $380-420 | ~$110 | 30min |
| iPhone 12 (128GB) | ~$165 | $35 | $310-340 | ~$110 | 30min |
| iPad 9th Gen | ~$125 | $25 | $225-250 | ~$75 | 25min |
| Dell XPS 15 | ~$350 | $90 | $650-800 | ~$285 | 60min |

## Parts Sources

- [MobileSentrix](https://www.mobilesentrix.com) — wholesale, fast shipping
- [InjuredGadgets](https://www.injuredgadgets.com) — best for bulk
- Amazon — good for singles (Prime returns if DOA)
