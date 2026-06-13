#!/usr/bin/env python3
"""
AI Listing Generator — uses local Ollama to generate eBay listings from device specs.
Creates SEO-optimized titles, honest condition descriptions, item specifics,
suggested pricing, and seller protection caveats.
"""

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
    import httpx
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.table import Table
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
    """Get Ollama connection settings from config."""
    ai = config.get("ai", {})
    ollama = ai.get("ollama", {})
    return {
        "base_url": ollama.get("base_url", "http://localhost:11434"),
        "model": ollama.get("model", "llama3.2"),
        "vision_model": ollama.get("vision_model", "llama3.2-vision"),
    }


def check_ollama(base_url: str) -> bool:
    """Check if Ollama is running and reachable."""
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def encode_image(path: str) -> str:
    """Base64 encode an image for Ollama vision API."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_photos(photo_paths: list[str], ollama_config: dict) -> str:
    """Use Ollama vision model to analyze device photos for hidden damage."""
    if not photo_paths:
        return ""
    
    base_url = ollama_config["base_url"]
    model = ollama_config["vision_model"]
    
    images = []
    for path in photo_paths:
        try:
            images.append(encode_image(path))
        except Exception as e:
            console.print(f"[yellow]Could not read photo {path}: {e}[/]")
    
    if not images:
        return ""
    
    prompt = (
        "You are inspecting a used electronic device for resale. Look at these photos and identify:\n"
        "1. Any damage beyond what's obvious (back glass cracks, frame dents, bent corners, missing screws)\n"
        "2. Water damage indicators (red LCI sticker visible?)\n"
        "3. Whether parts appear original or aftermarket\n"
        "4. Overall cosmetic condition (rate 1-10)\n"
        "5. Any red flags that would affect resale value\n\n"
        "Be specific and honest. If you can't see something clearly, say so."
    )
    
    try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": images,
                }
            ],
            "stream": False,
        }
        r = httpx.post(f"{base_url}/api/chat", json=payload, timeout=60)
        if r.status_code == 200:
            data = r.json()
            return data.get("message", {}).get("content", "")
        else:
            console.print(f"[yellow]Vision model error: {r.status_code}[/]")
            return ""
    except Exception as e:
        console.print(f"[yellow]Vision analysis failed: {e}[/]")
        return ""


def generate_listing(
    model: str,
    storage: str,
    color: str,
    carrier: str,
    condition_notes: str,
    repair_done: str,
    photo_analysis: str,
    suggested_price: float,
    config: dict,
    ollama_config: dict,
) -> dict:
    """Generate a complete eBay listing using Ollama."""
    
    base_url = ollama_config["base_url"]
    ollama_model = ollama_config["model"]
    
    listing_config = config.get("ai", {}).get("listing", {})
    title_max = listing_config.get("title_max_chars", 80)
    
    prompt = f"""You are an expert eBay seller specializing in refurbished electronics. Create a complete eBay listing for the following device.

DEVICE DETAILS:
- Model: {model}
- Storage: {storage}
- Color: {color}
- Carrier: {carrier}
- Condition: {condition_notes}
- Repair performed: {repair_done}
- Photo analysis: {photo_analysis if photo_analysis else 'No photo analysis available'}
- Suggested BIN price: ${suggested_price:.0f}

REQUIREMENTS:
1. TITLE: Max {title_max} characters. Include brand, model, storage, color, carrier, and key selling points. Use SEO keywords buyers search for (e.g., "unlocked", "excellent condition", "new screen"). NO ALL CAPS except brand names.

2. CONDITION DESCRIPTION: Be honest about the repair but emphasize what's GOOD about the device. Structure:
   - Opening: what was repaired and why (1-2 sentences, honest)
   - The good: what works perfectly (screen quality, battery, buttons, cameras, no scratches on body)
   - What's included: device only or with accessories
   - IMEI/activation status: clean, iCloud-free, ready to activate

3. ITEM SPECIFICS (JSON format):
   - Brand
   - Model
   - Storage Capacity
   - Color
   - Carrier (or "Unlocked")
   - Condition (use "Seller Refurbished" or "Used")
   - Screen Size
   - Connectivity (5G, 4G LTE, Wi-Fi, Bluetooth)
   - Operating System (iOS/Android version)
   - Features (Face ID, etc.)

4. PRICING: Justify the ${suggested_price:.0f} price. Mention comparable sold listings.

5. CAVEATS (seller protection):
   - "Screen has been professionally replaced with a high-quality aftermarket display"
   - "Device has been tested and all functions work as expected"
   - "Sold as-is with no returns unless item is not as described"
   - "Please verify carrier compatibility before purchasing"
   - Any other relevant disclaimers

6. SHIPPING: Free shipping, ships within 1 business day, USPS Priority Mail with tracking.

Output format — use these exact section headers:

## Title
[the title]

## Condition Description
[the description]

## Item Specifics
```json
{{...}}
```

## Pricing Note
[justification]

## Caveats
- [bullet points]

## Shipping
[shipping info]
"""

    try:
        payload = {
            "model": ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 1500,
            },
        }
        r = httpx.post(f"{base_url}/api/chat", json=payload, timeout=120)
        if r.status_code != 200:
            console.print(f"[red]Ollama error: {r.status_code} — {r.text[:200]}[/]")
            return {"error": f"Ollama returned {r.status_code}"}
        
        data = r.json()
        response_text = data.get("message", {}).get("content", "")
        
        # Parse sections
        sections = {}
        current_section = None
        current_content = []
        
        for line in response_text.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[3:].strip()
                current_content = []
            elif current_section:
                current_content.append(line)
        
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()
        
        # Extract title
        title = sections.get("Title", "").strip()
        if not title:
            # Fallback: first non-header line
            for line in response_text.split("\n"):
                if line.strip() and not line.startswith("##") and not line.startswith("```"):
                    title = line.strip()
                    break
        
        # Extract JSON specifics
        specifics = {}
        specifics_text = sections.get("Item Specifics", "")
        json_match = None
        if "```json" in specifics_text:
            json_match = specifics_text.split("```json")[1].split("```")[0]
        elif "```" in specifics_text:
            json_match = specifics_text.split("```")[1].split("```")[0]
        
        if json_match:
            try:
                specifics = json.loads(json_match.strip())
            except json.JSONDecodeError:
                pass
        
        return {
            "title": title,
            "condition_description": sections.get("Condition Description", ""),
            "item_specifics": specifics,
            "pricing_note": sections.get("Pricing Note", ""),
            "caveats": sections.get("Caveats", ""),
            "shipping": sections.get("Shipping", ""),
            "raw_response": response_text,
        }
        
    except Exception as e:
        console.print(f"[red]Generation failed: {e}[/]")
        return {"error": str(e)}


def print_listing(result: dict, model: str, price: float):
    """Pretty-print the generated listing."""
    
    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/]")
        return
    
    # Title
    console.print(Panel.fit(
        result.get("title", "No title generated"),
        title="📝 eBay Title",
        border_style="bold cyan",
    ))
    
    # Condition
    console.print(Panel.fit(
        result.get("condition_description", "No description generated"),
        title="📋 Condition Description",
        border_style="green",
    ))
    
    # Item Specifics
    specifics = result.get("item_specifics", {})
    if specifics:
        table = Table(title="🔧 Item Specifics", box=box.SIMPLE, border_style="dim blue")
        table.add_column("Field", style="bold", width=20)
        table.add_column("Value", width=30)
        for key, value in specifics.items():
            table.add_row(key, str(value))
        console.print(table)
    
    # Pricing
    console.print(Panel.fit(
        result.get("pricing_note", f"Suggested BIN: ${price:.0f}"),
        title="💰 Pricing",
        border_style="yellow",
    ))
    
    # Caveats
    console.print(Panel.fit(
        result.get("caveats", "No caveats generated"),
        title="🛡️ Seller Protection Caveats",
        border_style="red",
    ))
    
    # Shipping
    console.print(Panel.fit(
        result.get("shipping", "Free shipping, USPS Priority, 1 business day"),
        title="📦 Shipping",
        border_style="dim green",
    ))
    
    # Copy-paste ready
    console.print()
    console.print("[bold]Copy-Paste Ready Listing:[/]")
    console.print("─" * 60)
    
    full_listing = f"""**{result.get('title', '')}**

**Condition:** {result.get('condition_description', '')}

**Item Specifics:**
"""
    for k, v in specifics.items():
        full_listing += f"- {k}: {v}\n"
    
    full_listing += f"\n**Price:** ${price:.0f} (Buy It Now)\n"
    full_listing += f"\n{result.get('caveats', '')}\n"
    full_listing += f"\n**Shipping:** {result.get('shipping', '')}\n"
    
    console.print(full_listing)


def main():
    parser = argparse.ArgumentParser(
        description="AI Listing Generator — create eBay listings with local Ollama."
    )
    parser.add_argument("model", help="Device model (e.g., 'iPhone 13')")
    parser.add_argument("--storage", "-s", default="128GB", help="Storage capacity")
    parser.add_argument("--color", "-c", default="Midnight", help="Device color")
    parser.add_argument("--carrier", default="Unlocked", help="Carrier or 'Unlocked'")
    parser.add_argument("--condition", default="Cracked screen only, otherwise good condition", 
                       help="Condition notes before repair")
    parser.add_argument("--repair", default="Screen replaced with high-quality aftermarket display assembly",
                       help="What repair was done")
    parser.add_argument("--price", "-p", type=float, help="Suggested BIN price (auto-calculated if omitted)")
    parser.add_argument("--photos", "-i", nargs="+", help="Paths to device photos for AI analysis")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--raw", action="store_true", help="Output raw AI response")
    parser.add_argument("--no-ai", action="store_true", help="Skip AI, use template only")
    args = parser.parse_args()

    config = load_config(args.config)
    ollama_config = get_ollama_config(config)

    # Auto-calculate price if not provided
    if not args.price:
        for cat_name, cat_devices in config["devices"].items():
            for dev in cat_devices:
                if dev["model"].lower() in args.model.lower():
                    args.price = (dev["sell_min"] + dev["sell_max"]) / 2
                    break
        if not args.price:
            console.print("[yellow]Could not auto-calculate price. Use --price to set one.[/]")
            args.price = 300  # fallback

    # Photo analysis
    photo_analysis = ""
    if args.photos and not args.no_ai:
        if check_ollama(ollama_config["base_url"]):
            console.print("[dim]Analyzing photos with AI vision...[/]")
            photo_analysis = analyze_photos(args.photos, ollama_config)
            if photo_analysis:
                console.print(Panel.fit(
                    photo_analysis,
                    title="📸 AI Photo Analysis",
                    border_style="magenta",
                ))
        else:
            console.print("[yellow]Ollama not running — skipping photo analysis.[/]")

    # Generate listing
    if args.no_ai:
        # Template-only mode
        result = {
            "title": f"{args.model} {args.storage} {args.color} - {args.carrier} - New Screen - Excellent",
            "condition_description": (
                f"This {args.model} had a cracked screen which has been professionally replaced "
                f"with a high-quality aftermarket display. The new screen is bright, responsive, "
                f"and looks fantastic. All buttons, cameras, speakers, and charging port work "
                f"perfectly. The body is in good condition with normal wear. Battery health is good. "
                f"Device is fully tested and ready to use."
            ),
            "item_specifics": {
                "Brand": args.model.split()[0],
                "Model": args.model,
                "Storage Capacity": args.storage,
                "Color": args.color,
                "Carrier": args.carrier,
                "Condition": "Seller Refurbished",
                "Screen Size": "6.1 inches" if "Pro" not in args.model else "6.7 inches",
            },
            "pricing_note": f"Priced at ${args.price:.0f} based on recent sold listings for similar condition {args.model} devices.",
            "caveats": (
                "- Screen has been professionally replaced with a high-quality aftermarket display\n"
                "- Device has been fully tested — all functions work as expected\n"
                "- Sold as-is with no returns unless item is not as described\n"
                "- Please verify carrier compatibility before purchasing\n"
                "- IMEI is clean and device is iCloud/activation lock free"
            ),
            "shipping": "Free shipping via USPS Priority Mail with tracking. Ships within 1 business day.",
        }
    else:
        if not check_ollama(ollama_config["base_url"]):
            console.print("[red]Ollama is not running! Start it with: ollama serve[/]")
            console.print("[yellow]Falling back to template mode. Install Ollama for AI generation.[/]")
            # Re-run with no-ai
            args.no_ai = True
            return main.__wrapped__(parser.parse_args([args.model] + 
                [f"--storage={args.storage}", f"--color={args.color}", f"--carrier={args.carrier}",
                 f"--condition={args.condition}", f"--repair={args.repair}", f"--price={args.price}",
                 "--no-ai"]))
        
        console.print("[dim]Generating listing with Ollama...[/]")
        result = generate_listing(
            model=args.model,
            storage=args.storage,
            color=args.color,
            carrier=args.carrier,
            condition_notes=args.condition,
            repair_done=args.repair,
            photo_analysis=photo_analysis,
            suggested_price=args.price,
            config=config,
            ollama_config=ollama_config,
        )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    if args.raw:
        print(result.get("raw_response", json.dumps(result, indent=2)))
        return

    print_listing(result, args.model, args.price)


if __name__ == "__main__":
    main()
