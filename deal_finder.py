#!/usr/bin/env python3
"""
Multi-Source Deal Finder — scrapes/searchs eBay, Facebook Marketplace, OfferUp,
Mercari, and Swappa for cracked/broken devices matching target models.
Outputs a formatted table of deals with buy filter integration.
"""

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urlencode

try:
    import yaml
    import httpx
    from bs4 import BeautifulSoup
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install pyyaml httpx beautifulsoup4 rich")
    sys.exit(1)

console = Console()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


@dataclass
class Deal:
    """A found deal from any source."""
    source: str
    model: str
    title: str
    price: float
    condition: str
    url: str
    location: str = ""
    buy_filter_result: Optional[dict] = None
    profit_estimate: float = 0.0
    score: int = 0  # 0-100 quality score


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def extract_price(text: str) -> Optional[float]:
    """Extract a dollar price from text."""
    # Match $XX.XX or $X,XXX.XX
    match = re.search(r'\$[\s]*([0-9,]+(?:\.[0-9]{2})?)', text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def match_model(title: str, config: dict) -> Optional[tuple]:
    """Try to match a listing title to a known device model.
    Returns (device_config, category_name) or None."""
    title_lower = title.lower()
    for cat_name, cat_devices in config["devices"].items():
        for dev in cat_devices:
            model_lower = dev["model"].lower()
            # Check if the model name appears in the title
            if model_lower in title_lower:
                return dev, cat_name
            # Check search terms
            for term in dev.get("search_terms", []):
                # Extract the core model identifier from search term
                core = term.split(" cracked")[0].split(" broken")[0].split(" for parts")[0]
                if core.lower() in title_lower:
                    return dev, cat_name
    return None, None


def score_deal(deal: Deal, dev_config: dict, config: dict) -> int:
    """Score a deal 0-100 based on profitability and risk."""
    if not dev_config:
        return 0
    
    avg_buy = (dev_config["buy_min"] + dev_config["buy_max"]) / 2
    avg_sell = (dev_config["sell_min"] + dev_config["sell_max"]) / 2
    kit = dev_config["kit_cost"]
    
    # Profit score (0-50)
    profit = avg_sell - deal.price - kit
    profit_score = min(50, max(0, (profit / 150) * 50))
    
    # Price relative to max bid (0-30)
    max_bid = dev_config["buy_max"]
    if deal.price <= max_bid * 0.7:
        price_score = 30
    elif deal.price <= max_bid * 0.85:
        price_score = 20
    elif deal.price <= max_bid:
        price_score = 10
    else:
        price_score = 0
    
    # Difficulty bonus (0-10)
    diff_score = {"Easy": 10, "Medium": 5, "Hard": 0}.get(dev_config["difficulty"], 0)
    
    # Source trust bonus (0-10)
    source_score = {"ebay": 8, "swappa": 10, "mercari": 6, "offerup": 4, "facebook": 3}.get(deal.source, 0)
    
    return int(profit_score + price_score + diff_score + source_score)


# ─── eBay Scraper ───────────────────────────────────────────────

async def scrape_ebay(config: dict, max_results: int = 30) -> list[Deal]:
    """Scrape eBay for cracked/broken devices matching target models."""
    deals = []
    client = httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)
    
    try:
        for cat_name, cat_devices in config["devices"].items():
            for dev in cat_devices:
                for term in dev.get("search_terms", []):
                    query = quote_plus(term)
                    # Search sold+completed for pricing, and active for buying
                    for sold_filter in ["&LH_Sold=1&LH_Complete=1", ""]:
                        url = (
                            f"https://www.ebay.com/sch/i.html?_nkw={query}"
                            f"&_sop=15{sold_filter}&_ipg=60"
                        )
                        try:
                            resp = await client.get(url)
                            if resp.status_code != 200:
                                continue
                            
                            soup = BeautifulSoup(resp.text, "html.parser")
                            items = soup.select(".s-item")[:max_results]
                            
                            for item in items:
                                title_el = item.select_one(".s-item__title")
                                price_el = item.select_one(".s-item__price")
                                link_el = item.select_one(".s-item__link")
                                cond_el = item.select_one(".s-item__subtitle")
                                
                                if not title_el or not price_el:
                                    continue
                                
                                title = title_el.get_text(strip=True)
                                if "shop on ebay" in title.lower():
                                    continue  # Skip sponsored header
                                
                                price = extract_price(price_el.get_text(strip=True))
                                if not price:
                                    continue
                                
                                url_link = link_el.get("href", "") if link_el else ""
                                condition = cond_el.get_text(strip=True) if cond_el else ""
                                
                                matched_dev, matched_cat = match_model(title, config)
                                if not matched_dev:
                                    continue
                                
                                deal = Deal(
                                    source="ebay",
                                    model=matched_dev["model"],
                                    title=title[:120],
                                    price=price,
                                    condition=condition,
                                    url=url_link,
                                )
                                deal.score = score_deal(deal, matched_dev, config)
                                deal.profit_estimate = (
                                    (matched_dev["sell_min"] + matched_dev["sell_max"]) / 2
                                    - price
                                    - matched_dev["kit_cost"]
                                )
                                deals.append(deal)
                            
                            await asyncio.sleep(1.5)  # Rate limit
                            
                        except Exception as e:
                            console.print(f"[dim]eBay error for '{term}': {e}[/]")
                            continue
    finally:
        await client.aclose()
    
    return deals


# ─── Mercari Scraper ─────────────────────────────────────────────

async def scrape_mercari(config: dict, max_results: int = 20) -> list[Deal]:
    """Scrape Mercari for cracked/broken devices."""
    deals = []
    client = httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)
    
    try:
        for cat_name, cat_devices in config["devices"].items():
            for dev in cat_devices:
                for term in dev.get("search_terms", []):
                    query = quote_plus(term)
                    url = f"https://www.mercari.com/search/?keyword={query}&sortBy=1"
                    
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            continue
                        
                        soup = BeautifulSoup(resp.text, "html.parser")
                        items = soup.select('[data-testid="item-cell"]')[:max_results]
                        
                        for item in items:
                            title_el = item.select_one('[data-testid="item-name"]') or item.select_one("p")
                            price_el = item.select_one('[data-testid="item-price"]') or item.select_one("span")
                            link_el = item.select_one("a")
                            
                            if not title_el:
                                continue
                            
                            title = title_el.get_text(strip=True)
                            price = extract_price(price_el.get_text(strip=True)) if price_el else None
                            url_link = f"https://www.mercari.com{link_el.get('href', '')}" if link_el else ""
                            
                            if not price:
                                continue
                            
                            matched_dev, matched_cat = match_model(title, config)
                            if not matched_dev:
                                continue
                            
                            deal = Deal(
                                source="mercari",
                                model=matched_dev["model"],
                                title=title[:120],
                                price=price,
                                condition="",
                                url=url_link,
                            )
                            deal.score = score_deal(deal, matched_dev, config)
                            deal.profit_estimate = (
                                (matched_dev["sell_min"] + matched_dev["sell_max"]) / 2
                                - price
                                - matched_dev["kit_cost"]
                            )
                            deals.append(deal)
                        
                        await asyncio.sleep(1.5)
                        
                    except Exception as e:
                        console.print(f"[dim]Mercari error for '{term}': {e}[/]")
                        continue
    finally:
        await client.aclose()
    
    return deals


# ─── Swappa Scraper ──────────────────────────────────────────────

async def scrape_swappa(config: dict, max_results: int = 20) -> list[Deal]:
    """Scrape Swappa boneyard for cracked/broken devices."""
    deals = []
    client = httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)
    
    # Swappa categories
    swappa_cats = {
        "iPhone 12": "iphone-12",
        "iPhone 13": "iphone-13",
        "iPhone 13 Pro": "iphone-13-pro",
        "iPhone 14": "iphone-14",
        "Galaxy S22": "samsung-galaxy-s22",
        "Galaxy S23": "samsung-galaxy-s23",
        "iPad 9th Gen": "ipad-9",
        "iPad Air 4th Gen": "ipad-air-4",
        "iPad Pro 11 (2018/2020)": "ipad-pro-11",
        "MacBook Air M1 (2020)": "macbook-air-m1",
    }
    
    try:
        for cat_name, cat_devices in config["devices"].items():
            for dev in cat_devices:
                swappa_slug = swappa_cats.get(dev["model"])
                if not swappa_slug:
                    continue
                
                url = f"https://swappa.com/buy/{swappa_slug}/boneyard"
                
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    
                    soup = BeautifulSoup(resp.text, "html.parser")
                    listings = soup.select(".listing_row")[:max_results]
                    
                    for listing in listings:
                        title_el = listing.select_one(".listing_title") or listing.select_one("h2")
                        price_el = listing.select_one(".listing_price") or listing.select_one(".price")
                        link_el = listing.select_one("a")
                        cond_el = listing.select_one(".listing_condition")
                        
                        if not title_el:
                            continue
                        
                        title = title_el.get_text(strip=True)
                        price = extract_price(price_el.get_text(strip=True)) if price_el else None
                        url_link = f"https://swappa.com{link_el.get('href', '')}" if link_el else ""
                        condition = cond_el.get_text(strip=True) if cond_el else "Boneyard"
                        
                        if not price:
                            continue
                        
                        deal = Deal(
                            source="swappa",
                            model=dev["model"],
                            title=title[:120],
                            price=price,
                            condition=condition,
                            url=url_link,
                        )
                        deal.score = score_deal(deal, dev, config)
                        deal.profit_estimate = (
                            (dev["sell_min"] + dev["sell_max"]) / 2
                            - price
                            - dev["kit_cost"]
                        )
                        deals.append(deal)
                    
                    await asyncio.sleep(1.5)
                    
                except Exception as e:
                    console.print(f"[dim]Swappa error for '{dev['model']}': {e}[/]")
                    continue
    finally:
        await client.aclose()
    
    return deals


# ─── OfferUp Scraper ─────────────────────────────────────────────

async def scrape_offerup(config: dict, max_results: int = 20) -> list[Deal]:
    """Scrape OfferUp for cracked/broken devices near configured location."""
    deals = []
    client = httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)
    location = config.get("location", {})
    radius = location.get("radius_miles", 50)
    
    try:
        for cat_name, cat_devices in config["devices"].items():
            for dev in cat_devices:
                for term in dev.get("search_terms", []):
                    query = quote_plus(term)
                    url = f"https://offerup.com/search/?q={query}&radius={radius}"
                    
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            continue
                        
                        soup = BeautifulSoup(resp.text, "html.parser")
                        items = soup.select('[data-testid="item-card"]')[:max_results]
                        
                        for item in items:
                            title_el = item.select_one("p") or item.select_one("span")
                            price_el = item.select_one('[data-testid="item-price"]') or item.select_one("span")
                            link_el = item.select_one("a")
                            
                            if not title_el:
                                continue
                            
                            title = title_el.get_text(strip=True)
                            price = extract_price(price_el.get_text(strip=True)) if price_el else None
                            url_link = f"https://offerup.com{link_el.get('href', '')}" if link_el else ""
                            
                            if not price:
                                continue
                            
                            matched_dev, matched_cat = match_model(title, config)
                            if not matched_dev:
                                continue
                            
                            deal = Deal(
                                source="offerup",
                                model=matched_dev["model"],
                                title=title[:120],
                                price=price,
                                condition="",
                                url=url_link,
                            )
                            deal.score = score_deal(deal, matched_dev, config)
                            deal.profit_estimate = (
                                (matched_dev["sell_min"] + matched_dev["sell_max"]) / 2
                                - price
                                - matched_dev["kit_cost"]
                            )
                            deals.append(deal)
                        
                        await asyncio.sleep(1.5)
                        
                    except Exception as e:
                        console.print(f"[dim]OfferUp error for '{term}': {e}[/]")
                        continue
    finally:
        await client.aclose()
    
    return deals


# ─── Facebook Marketplace ───────────────────────────────────────

def facebook_manual_search(config: dict) -> list[Deal]:
    """
    Facebook Marketplace requires login and has aggressive anti-bot measures.
    This provides instructions for manual searching and a template for logging finds.
    """
    location = config.get("location", {})
    city = location.get("city", "Lafayette")
    state = location.get("state", "LA")
    radius = location.get("radius_miles", 50)
    
    console.print(Panel.fit(
        f"[bold yellow]⚠️  Facebook Marketplace requires manual searching[/]\n\n"
        f"1. Go to: [link]https://www.facebook.com/marketplace/{city.lower()}-{state.lower()}/[/]\n"
        f"2. Set radius to {radius} miles\n"
        f"3. Search for these terms:\n"
        + "\n".join(
            f"   • [bold]{dev['model']}[/]: {', '.join(dev.get('search_terms', [])[:2])}"
            for cat_devices in config["devices"].values()
            for dev in cat_devices
        ) +
        f"\n\n4. For each find, run:\n"
        f"   [bold]python deal_finder.py --add-manual[/] to log it\n\n"
        f"Tip: FB Marketplace cash deals often beat eBay by 15-25%.",
        title="Facebook Marketplace Guide",
        border_style="yellow",
    ))
    
    return []


# ─── Main Deal Finder ────────────────────────────────────────────

async def find_deals(
    config: dict,
    sources: list[str] = None,
    max_results: int = 30,
    min_score: int = 0,
    device_type: str = "all",
) -> list[Deal]:
    """Run all enabled scrapers and return combined results."""
    
    if sources is None:
        sources = ["ebay", "mercari", "swappa", "offerup", "facebook"]
    
    all_deals = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        if "ebay" in sources:
            task = progress.add_task("[cyan]Scanning eBay...", total=None)
            ebay_deals = await scrape_ebay(config, max_results)
            all_deals.extend(ebay_deals)
            progress.update(task, description=f"[cyan]eBay: {len(ebay_deals)} deals found")
        
        if "mercari" in sources:
            task = progress.add_task("[magenta]Scanning Mercari...", total=None)
            mercari_deals = await scrape_mercari(config, max_results)
            all_deals.extend(mercari_deals)
            progress.update(task, description=f"[magenta]Mercari: {len(mercari_deals)} deals found")
        
        if "swappa" in sources:
            task = progress.add_task("[green]Scanning Swappa...", total=None)
            swappa_deals = await scrape_swappa(config, max_results)
            all_deals.extend(swappa_deals)
            progress.update(task, description=f"[green]Swappa: {len(swappa_deals)} deals found")
        
        if "offerup" in sources:
            task = progress.add_task("[blue]Scanning OfferUp...", total=None)
            offerup_deals = await scrape_offerup(config, max_results)
            all_deals.extend(offerup_deals)
            progress.update(task, description=f"[blue]OfferUp: {len(offerup_deals)} deals found")
        
        if "facebook" in sources:
            task = progress.add_task("[yellow]Facebook Marketplace...", total=None)
            fb_deals = facebook_manual_search(config)
            all_deals.extend(fb_deals)
            progress.update(task, description=f"[yellow]Facebook: manual search required")
    
    # Filter by device type
    if device_type != "all":
        all_deals = [d for d in all_deals if any(
            d.model.lower() in dev["model"].lower()
            for dev in config["devices"].get(device_type, [])
        )]
    
    # Filter by minimum score
    if min_score > 0:
        all_deals = [d for d in all_deals if d.score >= min_score]
    
    # Deduplicate by URL
    seen_urls = set()
    unique_deals = []
    for d in all_deals:
        if d.url not in seen_urls:
            seen_urls.add(d.url)
            unique_deals.append(d)
    
    # Sort by score descending
    unique_deals.sort(key=lambda d: d.score, reverse=True)
    
    return unique_deals


def print_deals(deals: list[Deal], config: dict):
    """Pretty-print the deals table."""
    if not deals:
        console.print("[yellow]No deals found matching your criteria.[/]")
        return
    
    table = Table(
        title="🎯 Cracked Device Deals",
        box=box.ROUNDED,
        header_style="bold white",
        border_style="dim blue",
        title_style="bold cyan",
        show_lines=True,
    )
    
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Score", justify="center", width=6)
    table.add_column("Source", style="bold", width=8)
    table.add_column("Device", style="bold", width=18)
    table.add_column("Title", min_width=30, max_width=50)
    table.add_column("Price", justify="right", width=8)
    table.add_column("Est. Profit", justify="right", width=10)
    table.add_column("Link", width=8)
    
    for i, deal in enumerate(deals[:50], 1):
        score_color = "green" if deal.score >= 70 else ("yellow" if deal.score >= 40 else "red")
        profit_color = "green" if deal.profit_estimate >= 100 else ("yellow" if deal.profit_estimate >= 50 else "red")
        
        source_icon = {
            "ebay": "🏷️",
            "mercari": "📦",
            "swappa": "✅",
            "offerup": "🏪",
            "facebook": "👤",
        }.get(deal.source, "🔗")
        
        table.add_row(
            str(i),
            Text(str(deal.score), style=f"bold {score_color}"),
            f"{source_icon} {deal.source}",
            deal.model,
            deal.title[:80],
            f"${deal.price:.0f}",
            Text(f"${deal.profit_estimate:.0f}", style=profit_color),
            f"[link={deal.url}]open[/]",
        )
    
    # Stats
    avg_price = sum(d.price for d in deals) / len(deals)
    avg_profit = sum(d.profit_estimate for d in deals) / len(deals)
    top_deal = deals[0]
    
    console.print(table)
    console.print()
    console.print(Panel.fit(
        f"[bold]Found:[/] {len(deals)} deals  |  "
        f"[bold]Avg Price:[/] ${avg_price:.0f}  |  "
        f"[bold]Avg Est. Profit:[/] ${avg_profit:.0f}  |  "
        f"[bold]Top Deal:[/] {top_deal.model} from {top_deal.source} at ${top_deal.price:.0f} "
        f"(score: {top_deal.score}/100)",
        border_style="dim blue",
    ))
    
    # Top 3 picks
    console.print()
    console.print("[bold green]🏆 Top 3 Picks:[/]")
    for i, deal in enumerate(deals[:3], 1):
        console.print(
            f"  {i}. [bold]{deal.model}[/] — ${deal.price:.0f} on {deal.source} "
            f"(~${deal.profit_estimate:.0f} profit) — [link={deal.url}]view listing[/]"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Source Deal Finder — find cracked devices to flip for profit."
    )
    parser.add_argument(
        "--sources", "-s",
        nargs="+",
        choices=["ebay", "mercari", "swappa", "offerup", "facebook"],
        default=["ebay", "mercari", "swappa", "offerup"],
        help="Sources to search (default: all except facebook)"
    )
    parser.add_argument(
        "--type", "-t",
        choices=["all", "phones", "tablets", "laptops"],
        default="all",
        help="Filter by device type"
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=30,
        help="Max results per source (default: 30)"
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Minimum deal score 0-100 (default: 0 = show all)"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--add-manual",
        action="store_true",
        help="Interactively add a manually found deal"
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.add_manual:
        console.print("[bold]Add Manual Deal[/]")
        model = console.input("Device model (e.g. iPhone 13): ")
        price = float(console.input("Price: $"))
        source = console.input("Source [ebay/mercari/offerup/facebook/swappa]: ") or "facebook"
        url = console.input("URL (optional): ") or ""
        title = console.input("Title (optional): ") or f"{model} - cracked screen"
        
        deal = Deal(
            source=source,
            model=model,
            title=title,
            price=price,
            condition="",
            url=url,
        )
        
        # Try to match to config
        matched_dev, matched_cat = match_model(title, config)
        if matched_dev:
            deal.score = score_deal(deal, matched_dev, config)
            deal.profit_estimate = (
                (matched_dev["sell_min"] + matched_dev["sell_max"]) / 2
                - price
                - matched_dev["kit_cost"]
            )
        
        print_deals([deal], config)
        return

    deals = asyncio.run(find_deals(
        config,
        sources=args.sources,
        max_results=args.max,
        min_score=args.min_score,
        device_type=args.type,
    ))

    if args.json:
        import json
        output = [
            {
                "source": d.source,
                "model": d.model,
                "title": d.title,
                "price": d.price,
                "condition": d.condition,
                "url": d.url,
                "score": d.score,
                "profit_estimate": round(d.profit_estimate, 2),
            }
            for d in deals
        ]
        print(json.dumps(output, indent=2))
        return

    print_deals(deals, config)


if __name__ == "__main__":
    main()
