#!/usr/bin/env python3
"""
AI Tools — advanced AI-powered features for device flipping.
- Market trend detection (is a model's resale price trending up/down?)
- Auto-negotiation drafts (generate messages for FB Marketplace/OfferUp)
- Competitor analysis (track what other refurb sellers are pricing at)
- Bulk listing generator (generate listings for multiple devices at once)
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import yaml
    import httpx
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install pyyaml httpx rich")
    sys.exit(1)

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_ollama_config(config: dict) -> dict:
    ai = config.get("ai", {})
    ollama = ai.get("ollama", {})
    return {
        "base_url": ollama.get("base_url", "http://localhost:11434"),
        "model": ollama.get("model", "llama3.2"),
    }


def check_ollama(base_url: str) -> bool:
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def ollama_chat(base_url: str, model: str, prompt: str, system: str = "") -> str:
    """Send a prompt to Ollama and get the response."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1000},
    }
    
    try:
        r = httpx.post(f"{base_url}/api/chat", json=payload, timeout=60)
        if r.status_code == 200:
            return r.json().get("message", {}).get("content", "")
        return f"Error: {r.status_code}"
    except Exception as e:
        return f"Error: {e}"


# ─── Market Trend Detection ──────────────────────────────────────

def market_trends(args):
    """Analyze whether a device model's resale price is trending up or down."""
    config = load_config(args.config)
    ollama = get_ollama_config(config)
    
    if not check_ollama(ollama["base_url"]):
        console.print("[red]Ollama not running. Start with: ollama serve[/]")
        return
    
    model_filter = args.model or ""
    
    console.print("[bold cyan]📈 Market Trend Analysis[/]")
    console.print("[dim]Analyzing resale price trends for target devices...[/]")
    
    # Build device list
    devices = []
    for cat_name, cat_devices in config["devices"].items():
        for dev in cat_devices:
            if model_filter and model_filter.lower() not in dev["model"].lower():
                continue
            devices.append((dev, cat_name))
    
    if not devices:
        console.print(f"[yellow]No devices matching '{model_filter}'[/]")
        return
    
    prompt = f"""You are a market analyst for refurbished electronics. Based on your knowledge of the used device market as of mid-2026, analyze the resale price trend for each of these devices:

{chr(10).join(f"- {dev['model']} ({dev.get('storage', '')}): current resale range ${dev['sell_min']}-${dev['sell_max']}" for dev, _ in devices)}

For each device, provide:
1. TREND: "Rising", "Falling", or "Stable"
2. CONFIDENCE: High/Medium/Low
3. REASON: 1-2 sentences explaining why (new model released? seasonal demand? supply glut?)
4. ACTION: "Buy now", "Wait", or "Caution"
5. PRICE ADJUSTMENT: Suggested % adjustment to the sell price range

Format each as a JSON object in a JSON array. Example:
[
  {{"model": "iPhone 13", "trend": "Falling", "confidence": "High", "reason": "iPhone 17 release imminent, 13 values dropping 5-8% monthly", "action": "Caution", "adjustment_pct": -5}},
  ...
]

Be specific and data-driven. Consider: new model releases, seasonal patterns (holiday demand, tax refund season, back-to-school), and supply chain factors."""
    
    response = ollama_chat(ollama["base_url"], ollama["model"], prompt)
    
    # Try to parse JSON from response
    try:
        # Find JSON array in response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            trends = json.loads(response[start:end])
        else:
            trends = []
    except json.JSONDecodeError:
        console.print("[yellow]Could not parse AI response as JSON. Raw output:[/]")
        console.print(response)
        return
    
    if not trends:
        console.print("[yellow]No trend data returned.[/]")
        console.print(response)
        return
    
    # Display table
    table = Table(
        title="📈 Market Trend Analysis",
        box=box.ROUNDED,
        header_style="bold white",
        border_style="dim blue",
    )
    
    table.add_column("Device", style="bold", width=18)
    table.add_column("Trend", width=10)
    table.add_column("Confidence", width=12)
    table.add_column("Action", width=10)
    table.add_column("Adjustment", justify="right", width=10)
    table.add_column("Reason", min_width=30)
    
    for t in trends:
        trend_color = {"Rising": "green", "Falling": "red", "Stable": "yellow"}.get(t.get("trend", ""), "white")
        action_color = {"Buy now": "green", "Wait": "yellow", "Caution": "red"}.get(t.get("action", ""), "white")
        adj = t.get("adjustment_pct", 0)
        adj_str = f"{adj:+.0f}%" if adj else "-"
        
        table.add_row(
            t.get("model", "?"),
            Text(t.get("trend", "?"), style=f"bold {trend_color}"),
            t.get("confidence", "?"),
            Text(t.get("action", "?"), style=f"bold {action_color}"),
            adj_str,
            t.get("reason", "")[:100],
        )
    
    console.print(table)
    
    # Summary advice
    rising = [t for t in trends if t.get("trend") == "Rising"]
    falling = [t for t in trends if t.get("trend") == "Falling"]
    
    if rising:
        console.print(f"\n[bold green]🟢 Buy Now:[/] {', '.join(t['model'] for t in rising)}")
    if falling:
        console.print(f"[bold red]🔴 Caution:[/] {', '.join(t['model'] for t in falling)}")


# ─── Auto-Negotiation Drafts ────────────────────────────────────

def negotiate(args):
    """Generate negotiation messages for FB Marketplace / OfferUp."""
    config = load_config(args.config)
    ollama = get_ollama_config(config)
    
    if not check_ollama(ollama["base_url"]):
        console.print("[red]Ollama not running. Start with: ollama serve[/]")
        return
    
    prompt = f"""You are helping someone negotiate a better price on a used/cracked device on Facebook Marketplace or OfferUp. Generate 3 different negotiation messages.

DEVICE: {args.model}
LISTED PRICE: ${args.price:.0f}
TARGET PRICE: ${args.target:.0f}
CONDITION: {args.condition or 'Cracked screen, otherwise working'}
PLATFORM: {args.platform or 'Facebook Marketplace'}
SELLER NOTES: {args.notes or 'None'}

Generate 3 messages with different approaches:
1. DIRECT — straightforward offer with reasoning about repair costs
2. FRIENDLY — casual, builds rapport, mentions you fix these as a hobby
3. VALUE — focuses on market comparables and what similar devices actually sell for

Each message should:
- Be 2-4 sentences max
- Sound like a real person, not a bot
- Include the specific offer amount
- Mention the repair cost as justification
- Be ready to copy-paste and send

Format:
## Direct
[message]

## Friendly
[message]

## Value
[message]"""
    
    response = ollama_chat(ollama["base_url"], ollama["model"], prompt)
    
    console.print(Panel.fit(
        response,
        title=f"💬 Negotiation Drafts — {args.model}",
        border_style="cyan",
    ))


# ─── Competitor Analysis ─────────────────────────────────────────

def competitors(args):
    """Analyze competitor pricing for refurbished devices."""
    config = load_config(args.config)
    ollama = get_ollama_config(config)
    
    if not check_ollama(ollama["base_url"]):
        console.print("[red]Ollama not running. Start with: ollama serve[/]")
        return
    
    model_filter = args.model or ""
    
    devices = []
    for cat_name, cat_devices in config["devices"].items():
        for dev in cat_devices:
            if model_filter and model_filter.lower() not in dev["model"].lower():
                continue
            devices.append((dev, cat_name))
    
    if not devices:
        console.print(f"[yellow]No devices matching '{model_filter}'[/]")
        return
    
    prompt = f"""You are a competitive intelligence analyst for refurbished electronics sold on eBay. Analyze the competitive landscape for these devices:

{chr(10).join(f"- {dev['model']} ({dev.get('storage', '')}): typical refurb resale ${dev['sell_min']}-${dev['sell_max']}" for dev, _ in devices)}

For each device, provide:
1. COMPETITION LEVEL: "Low", "Medium", "High", or "Saturated"
2. AVG COMPETITOR PRICE: What refurbished units actually sell for
3. PRICE POSITIONING: Should we price at market, below market, or premium?
4. DIFFERENTIATION: What could make our listing stand out?
5. LISTING COUNT: Estimated number of competing refurb listings

Format as JSON array. Be realistic — the refurb market on eBay is competitive for popular models."""
    
    response = ollama_chat(ollama["base_url"], ollama["model"], prompt)
    
    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
        else:
            data = []
    except json.JSONDecodeError:
        console.print("[yellow]Could not parse. Raw output:[/]")
        console.print(response)
        return
    
    if not data:
        console.print(response)
        return
    
    table = Table(
        title="🏪 Competitor Analysis",
        box=box.ROUNDED,
        header_style="bold white",
        border_style="dim blue",
    )
    
    table.add_column("Device", style="bold", width=18)
    table.add_column("Competition", width=12)
    table.add_column("Avg Price", justify="right", width=10)
    table.add_column("Positioning", width=12)
    table.add_column("Differentiation", min_width=30)
    
    for d in data:
        comp_color = {
            "Low": "green", "Medium": "yellow", "High": "red", "Saturated": "red"
        }.get(d.get("competition_level", ""), "white")
        
        table.add_row(
            d.get("model", "?"),
            Text(d.get("competition_level", "?"), style=f"bold {comp_color}"),
            d.get("avg_competitor_price", "?"),
            d.get("price_positioning", "?"),
            d.get("differentiation", "")[:80],
        )
    
    console.print(table)


# ─── Bulk Listing Generator ──────────────────────────────────────

def bulk_listings(args):
    """Generate listings for multiple devices from a CSV/JSON input."""
    config = load_config(args.config)
    ollama = get_ollama_config(config)
    
    if not check_ollama(ollama["base_url"]):
        console.print("[red]Ollama not running. Start with: ollama serve[/]")
        return
    
    # Read input
    devices = []
    if args.input:
        with open(args.input) as f:
            if args.input.endswith(".json"):
                devices = json.load(f)
            else:
                import csv
                reader = csv.DictReader(f)
                devices = list(reader)
    else:
        console.print("[yellow]Use --input to provide a CSV or JSON file of devices.[/]")
        console.print("[dim]CSV format: model,storage,color,carrier,condition,repair,price[/]")
        return
    
    console.print(f"[bold]Generating {len(devices)} listings...[/]")
    
    for i, dev in enumerate(devices, 1):
        model = dev.get("model", "Unknown")
        storage = dev.get("storage", "128GB")
        color = dev.get("color", "")
        carrier = dev.get("carrier", "Unlocked")
        condition = dev.get("condition", "Cracked screen, otherwise good")
        repair = dev.get("repair", "Screen replaced with aftermarket display")
        price = float(dev.get("price", 300))
        
        console.print(f"\n[bold]── Listing {i}/{len(devices)}: {model} ──[/]")
        
        prompt = f"""Create an eBay listing title (max 80 chars) and 2-sentence condition description for:

{model} {storage} {color} - {carrier}
Condition: {condition}
Repair: {repair}
Price: ${price:.0f}

Output format:
TITLE: [title]
DESC: [description]"""
        
        response = ollama_chat(ollama["base_url"], ollama["model"], prompt)
        
        title = ""
        desc = ""
        for line in response.split("\n"):
            if line.startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("DESC:"):
                desc = line[5:].strip()
        
        console.print(f"  [bold cyan]Title:[/] {title}")
        console.print(f"  [dim]Desc:[/] {desc[:120]}...")


# ─── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI Tools — advanced AI features for device flipping."
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # market-trends
    trends_parser = subparsers.add_parser("trends", help="Analyze market price trends")
    trends_parser.add_argument("--model", "-m", help="Filter by model")
    trends_parser.add_argument("--config", default="config.yaml")
    
    # negotiate
    neg_parser = subparsers.add_parser("negotiate", help="Generate negotiation messages")
    neg_parser.add_argument("model", help="Device model")
    neg_parser.add_argument("price", type=float, help="Listed price")
    neg_parser.add_argument("target", type=float, help="Your target price")
    neg_parser.add_argument("--condition", help="Device condition")
    neg_parser.add_argument("--platform", default="Facebook Marketplace")
    neg_parser.add_argument("--notes", help="Seller notes/observations")
    neg_parser.add_argument("--config", default="config.yaml")
    
    # competitors
    comp_parser = subparsers.add_parser("competitors", help="Analyze competitor pricing")
    comp_parser.add_argument("--model", "-m", help="Filter by model")
    comp_parser.add_argument("--config", default="config.yaml")
    
    # bulk-listings
    bulk_parser = subparsers.add_parser("bulk", help="Generate bulk listings from CSV/JSON")
    bulk_parser.add_argument("--input", "-i", required=True, help="CSV or JSON file of devices")
    bulk_parser.add_argument("--config", default="config.yaml")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    commands = {
        "trends": market_trends,
        "negotiate": negotiate,
        "competitors": competitors,
        "bulk": bulk_listings,
    }
    
    commands[args.command](args)


if __name__ == "__main__":
    main()
