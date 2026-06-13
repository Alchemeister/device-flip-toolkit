#!/usr/bin/env python3
"""
Buy Filter — scans a device listing for deal-killers before you bid.
Checks: iCloud lock, Face ID, battery health, carrier lock, back glass, water damage.
Outputs PASS/FAIL with reasoning and adjusted max bid.
"""

import argparse
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    import yaml
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install pyyaml rich")
    sys.exit(1)

console = Console()


@dataclass
class DealKillerResult:
    """Result of checking one deal-killer condition."""
    name: str
    passed: bool
    detail: str
    penalty: float = 0.0
    time_penalty: int = 0


@dataclass
class BuyFilterResult:
    """Full result of analyzing a listing."""
    model: str
    listing_price: float
    max_bid: float
    adjusted_max_bid: float
    checks: list = field(default_factory=list)
    passed: bool = True
    warnings: list = field(default_factory=list)
    recommendation: str = ""


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def find_device_config(config: dict, model: str):
    """Find the device config entry matching the model name.
    Returns (device_dict, category_name) or (None, None)."""
    for cat_name, cat_devices in config["devices"].items():
        for dev in cat_devices:
            if dev["model"].lower() in model.lower():
                return dev, cat_name
    return None, None


def check_icloud(text: str, dev_config: dict) -> DealKillerResult:
    """Check for iCloud/activation lock."""
    # First check for explicit "no iCloud lock" or "icloud unlocked" — these are GOOD
    clean_patterns = [
        r"no\s*i[cC]loud\s*lock",
        r"i[cC]loud\s*(unlock|clean|clear|free|off|removed)",
        r"activation\s*lock\s*(off|removed|cleared|disabled)",
        r"FMI\s*(off|disabled|removed)",
        r"find\s*my\s*(iphone|ipad|mac)\s*(off|disabled|removed)",
    ]
    for pat in clean_patterns:
        if re.search(pat, text):
            return DealKillerResult(
                name="iCloud Lock",
                passed=True,
                detail="Listing explicitly states iCloud/activation lock is OFF — good.",
            )
    
    # Now check for actual lock indicators
    danger_patterns = [
        r"i[cC]loud\s*lock(ed)?(?!.*(?:off|removed|disabled|clean|clear|free|unlock))",
        r"activation\s*lock(ed)?(?!.*(?:off|removed|disabled|cleared))",
        r"find\s*my\s*(iphone|ipad|mac).*on",
        r"cannot\s*(be\s*)?activate",
        r"locked\s*to\s*owner",
        r"apple\s*id\s*lock",
        r"FMI\s*(on|enabled)",
    ]
    for pat in danger_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="iCloud Lock",
                passed=False,
                detail="Device is iCloud/activation locked — PAPERWEIGHT. Do not buy.",
                penalty=float("inf"),
            )
    return DealKillerResult(
        name="iCloud Lock",
        passed=True,
        detail="No iCloud lock detected in listing text.",
    )


def check_face_id(text: str, dev_config: dict) -> DealKillerResult:
    """Check if Face ID is broken."""
    patterns = [
        r"face\s*id\s*(not\s*working|broken|doesn'?t\s*work|disabled|unavailable)",
        r"true\s*tone\s*(not\s*working|broken|disabled)",
        r"front\s*(camera|sensor).*(broken|not\s*working)",
        r"earpiece\s*(broken|not\s*working)",
    ]
    penalty = dev_config.get("deal_killers", {}).get("face_id_broken_penalty", 50)
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Face ID / Front Sensors",
                passed=False,
                detail=f"Face ID or front sensors damaged — deduct ${penalty} from max bid.",
                penalty=penalty,
            )
    return DealKillerResult(
        name="Face ID / Front Sensors",
        passed=True,
        detail="No Face ID issues mentioned.",
    )


def check_battery(text: str, dev_config: dict) -> DealKillerResult:
    """Check battery health percentage."""
    threshold = dev_config.get("deal_killers", {}).get("battery_threshold", 85)
    penalty = dev_config.get("deal_killers", {}).get("battery_penalty", 20)
    
    # Look for battery health percentage
    match = re.search(r"battery\s*(health|capacity|life).*?(\d{1,3})\s*%", text, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d{1,3})\s*%\s*battery", text, re.IGNORECASE)
    
    if match:
        pct = int(match.group(2) if match.lastindex >= 2 else match.group(1))
        if pct < threshold:
            return DealKillerResult(
                name="Battery Health",
                passed=False,
                detail=f"Battery at {pct}% (below {threshold}% threshold) — add ${penalty} for replacement.",
                penalty=penalty,
            )
        return DealKillerResult(
            name="Battery Health",
            passed=True,
            detail=f"Battery at {pct}% — acceptable.",
        )
    
    # Check for keywords indicating bad battery
    bad_patterns = [
        r"battery.*(bad|poor|needs\s*replac|draining|swollen|dead)",
        r"(bad|poor|dying)\s*battery",
    ]
    for pat in bad_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Battery Health",
                passed=False,
                detail=f"Battery described as bad/poor — add ${penalty} for replacement.",
                penalty=penalty,
            )
    
    return DealKillerResult(
        name="Battery Health",
        passed=True,
        detail="No battery issues mentioned.",
    )


def check_carrier(text: str, dev_config: dict) -> DealKillerResult:
    """Check carrier lock status."""
    avoid_patterns = [
        r"sprint.*lock",
        r"financed",
        r"still\s*owing",
        r"not\s*paid\s*off",
        r"blacklisted",
        r"bad\s*esn",
        r"bad\s*imei",
        r"reported\s*(lost|stolen)",
    ]
    for pat in avoid_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Carrier / IMEI Status",
                passed=False,
                detail="Device is financed, blacklisted, or has bad IMEI — AVOID.",
                penalty=float("inf"),
            )
    
    # Check if it's locked but unlockable
    locked_patterns = [
        r"locked\s*to\s*(at&t|att|t-mobile|tmobile|verizon)",
        r"(at&t|att|t-mobile|tmobile)\s*locked",
    ]
    for pat in locked_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Carrier / IMEI Status",
                passed=True,
                detail="Carrier locked but likely unlockable (AT&T/T-Mobile). Factor in unlock time.",
            )
    
    unlocked_patterns = [r"unlock(ed)?", r"factory\s*unlock", r"sim\s*free"]
    for pat in unlocked_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Carrier / IMEI Status",
                passed=True,
                detail="Device appears unlocked.",
            )
    
    return DealKillerResult(
        name="Carrier / IMEI Status",
        passed=True,
        detail="No carrier issues detected.",
    )


def check_back_glass(text: str, dev_config: dict) -> DealKillerResult:
    """Check if back glass is also damaged."""
    penalty = dev_config.get("deal_killers", {}).get("back_glass_penalty", 25)
    time_penalty = dev_config.get("deal_killers", {}).get("back_glass_time", 60)
    
    patterns = [
        r"back\s*glass.*(cracked|broken|shattered|damaged)",
        r"rear\s*glass.*(cracked|broken)",
        r"(cracked|broken|shattered).*back\s*glass",
        r"(cracked|broken).*rear\s*glass",
        r"both\s*(sides|front\s*and\s*back).*(cracked|broken)",
        r"front\s*and\s*back.*(cracked|broken)",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Back Glass",
                passed=False,
                detail=f"Back glass also damaged — add ${penalty} cost + {time_penalty}min extra time.",
                penalty=penalty,
                time_penalty=time_penalty,
            )
    return DealKillerResult(
        name="Back Glass",
        passed=True,
        detail="No back glass damage mentioned.",
    )


def check_water_damage(text: str, dev_config: dict) -> DealKillerResult:
    """Check for water damage indicators."""
    patterns = [
        r"water\s*damag",
        r"liquid\s*damag",
        r"moisture\s*damag",
        r"corrosion",
        r"water\s*indicator.*(red|triggered|tripped)",
        r"LCI.*(red|triggered)",
        r"got\s*wet",
        r"dropped\s*in\s*(water|pool|toilet|sink|bath)",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Water Damage",
                passed=False,
                detail="Water damage mentioned — AVOID. Unpredictable future failures.",
                penalty=float("inf"),
            )
    return DealKillerResult(
        name="Water Damage",
        passed=True,
        detail="No water damage mentioned.",
    )


def check_frame_damage(text: str, dev_config: dict) -> DealKillerResult:
    """Check for frame/bend damage."""
    patterns = [
        r"(frame|housing|body|chassis).*(bent|dented|damaged|warped)",
        r"(bent|dented|warped).*(frame|housing|body)",
        r"doesn'?t\s*sit\s*flat",
        r"won'?t\s*charge.*(port|lightning)",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Frame / Physical Damage",
                passed=False,
                detail="Frame/housing damage — may prevent proper screen fit. Deduct $30.",
                penalty=30,
            )
    return DealKillerResult(
        name="Frame / Physical Damage",
        passed=True,
        detail="No frame damage mentioned.",
    )


def check_missing_parts(text: str, dev_config: dict) -> DealKillerResult:
    """Check if essential parts are missing."""
    patterns = [
        r"no\s*(screen|display|lcd)",
        r"(screen|display|lcd)\s*(missing|removed|gone)",
        r"no\s*(battery|camera|charging\s*port)",
        r"stripped\s*screws",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return DealKillerResult(
                name="Missing Parts",
                passed=False,
                detail="Essential parts missing — cost and complexity increase significantly.",
                penalty=50,
            )
    return DealKillerResult(
        name="Missing Parts",
        passed=True,
        detail="No missing parts mentioned.",
    )


def analyze_listing(text: str, model: str, listing_price: float, config: dict) -> BuyFilterResult:
    """Run all deal-killer checks on a listing."""
    dev_config, cat_name = find_device_config(config, model)
    
    if not dev_config:
        return BuyFilterResult(
            model=model,
            listing_price=listing_price,
            max_bid=0,
            adjusted_max_bid=0,
            passed=False,
            recommendation=f"Model '{model}' not found in config. Add it to config.yaml first.",
        )

    avg_buy = (dev_config["buy_min"] + dev_config["buy_max"]) / 2
    max_bid = dev_config["buy_max"]
    
    checks = [
        check_icloud(text, dev_config),
        check_water_damage(text, dev_config),
        check_carrier(text, dev_config),
        check_face_id(text, dev_config),
        check_battery(text, dev_config),
        check_back_glass(text, dev_config),
        check_frame_damage(text, dev_config),
        check_missing_parts(text, dev_config),
    ]

    # Calculate adjusted max bid
    total_penalty = 0
    total_time_penalty = 0
    fatal = False
    warnings = []

    for check in checks:
        if check.penalty == float("inf"):
            fatal = True
        elif not check.passed:
            total_penalty += check.penalty
            total_time_penalty += check.time_penalty
            warnings.append(check.detail)

    adjusted_max_bid = max_bid - total_penalty if not fatal else 0
    passed = not fatal and listing_price <= adjusted_max_bid

    if fatal:
        recommendation = "❌ DO NOT BUY — fatal deal-killer detected."
    elif listing_price > adjusted_max_bid:
        recommendation = (
            f"⚠️  OVERPRICED — listing at ${listing_price:.0f} but max bid is ${adjusted_max_bid:.0f}. "
            f"Offer ${adjusted_max_bid:.0f} or pass."
        )
    elif listing_price <= adjusted_max_bid * 0.8:
        recommendation = (
            f"✅ GREAT DEAL — ${listing_price:.0f} is well under max ${adjusted_max_bid:.0f}. Buy immediately."
        )
    else:
        recommendation = (
            f"✅ GOOD DEAL — ${listing_price:.0f} is within range. "
            f"Estimated profit: ~${(dev_config['sell_min'] + dev_config['sell_max'])/2 - listing_price - dev_config['kit_cost'] - total_penalty:.0f}"
        )

    return BuyFilterResult(
        model=dev_config["model"],
        listing_price=listing_price,
        max_bid=max_bid,
        adjusted_max_bid=adjusted_max_bid,
        checks=checks,
        passed=passed,
        warnings=warnings,
        recommendation=recommendation,
    )


def print_result(result: BuyFilterResult):
    """Pretty-print the analysis result."""
    # Status panel
    status_color = "green" if result.passed else "red"
    status_text = "✅ PASS" if result.passed else "❌ FAIL"
    
    console.print(Panel.fit(
        f"[bold {status_color}]{status_text}[/] — {result.model}\n"
        f"Listing: ${result.listing_price:.0f} | Max Bid: ${result.max_bid:.0f} | Adjusted: ${result.adjusted_max_bid:.0f}",
        title="Buy Filter Result",
        border_style=status_color,
    ))

    # Checks table
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Check", style="bold", width=22)
    table.add_column("Status", width=8)
    table.add_column("Detail", min_width=40)
    table.add_column("Penalty", justify="right", width=10)

    for check in result.checks:
        status = "[green]✓[/]" if check.passed else "[red]✗[/]"
        penalty_str = f"${check.penalty:.0f}" if check.penalty > 0 and check.penalty != float("inf") else ("∞" if check.penalty == float("inf") else "-")
        table.add_row(check.name, status, check.detail, penalty_str)

    console.print(table)
    console.print()
    console.print(f"[bold]Recommendation:[/] {result.recommendation}")

    if result.warnings:
        console.print()
        console.print("[yellow]⚠️  Warnings:[/]")
        for w in result.warnings:
            console.print(f"  • {w}")


def main():
    parser = argparse.ArgumentParser(
        description="Buy Filter — check a device listing for deal-killers before bidding."
    )
    parser.add_argument("model", help="Device model (e.g., 'iPhone 13', 'iPad 9th Gen')")
    parser.add_argument("price", type=float, help="Listing price in USD")
    parser.add_argument(
        "--text", "-t",
        help="Listing description text to analyze"
    )
    parser.add_argument(
        "--file", "-f",
        help="Read listing text from a file"
    )
    parser.add_argument(
        "--url", "-u",
        help="Fetch listing text from URL (eBay, Mercari, etc.)"
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
    args = parser.parse_args()

    config = load_config(args.config)

    # Get listing text
    text = ""
    if args.text:
        text = args.text
    elif args.file:
        with open(args.file) as f:
            text = f.read()
    elif args.url:
        try:
            import httpx
            r = httpx.get(args.url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            text = r.text
        except ImportError:
            console.print("[red]httpx not installed. Run: pip install httpx[/]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Failed to fetch URL: {e}[/]")
            sys.exit(1)
    else:
        console.print("[yellow]No listing text provided. Use --text, --file, or --url.[/]")
        console.print("[dim]Running in interactive mode — paste listing text below (Ctrl+D when done):[/]")
        text = sys.stdin.read()

    if not text.strip():
        console.print("[red]No listing text to analyze.[/]")
        sys.exit(1)

    result = analyze_listing(text, args.model, args.price, config)

    if args.json:
        import json
        output = {
            "model": result.model,
            "listing_price": result.listing_price,
            "max_bid": result.max_bid,
            "adjusted_max_bid": result.adjusted_max_bid,
            "passed": result.passed,
            "recommendation": result.recommendation,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail,
                    "penalty": c.penalty if c.penalty != float("inf") else "inf",
                }
                for c in result.checks
            ],
            "warnings": result.warnings,
        }
        print(json.dumps(output, indent=2))
        return

    print_result(result)


if __name__ == "__main__":
    main()
