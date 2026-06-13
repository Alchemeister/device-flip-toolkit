#!/usr/bin/env python3
"""
ROI Grid Calculator — profitability analysis for device flipping.
Shows buy/sell ranges, kit costs, profit, ROI%, difficulty, and time estimates.
Sortable, color-coded, with filtering by device type.
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install pyyaml rich")
    sys.exit(1)

console = Console()

PROFIT_COLORS = {
    "green": (100, float("inf")),   # >$100
    "yellow": (50, 100),             # $50-100
    "red": (0, 50),                  # <$50
}


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def calc_ebay_payout(sell_price: float, config: dict) -> float:
    """Calculate what you actually get after eBay fees."""
    fee_pct = config["ebay"]["fee_percent"] / 100
    pay_pct = config["ebay"]["payment_fee_percent"] / 100
    pay_fixed = config["ebay"]["payment_fee_fixed"]
    fee = sell_price * fee_pct
    payment = sell_price * pay_pct + pay_fixed
    return sell_price - fee - payment


def profit_color(profit: float) -> str:
    for color, (lo, hi) in PROFIT_COLORS.items():
        if lo <= profit < hi:
            return color
    return "green" if profit >= 100 else "red"


def build_table(devices: list, config: dict, sort_by: str = "profit", 
                device_type: str = "all", reverse: bool = False) -> Table:
    """Build a rich Table with all device profitability data."""
    
    table = Table(
        title="📱💻 Device Flip ROI Grid",
        box=box.ROUNDED,
        header_style="bold white",
        border_style="dim blue",
        title_style="bold cyan",
        show_lines=True,
    )
    
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Device", style="bold", min_width=22)
    table.add_column("Type", style="dim", width=8)
    table.add_column("Buy Range", justify="right", width=12)
    table.add_column("Kit", justify="right", width=6)
    table.add_column("Sell Range", justify="right", width=12)
    table.add_column("Net Sell", justify="right", width=10)
    table.add_column("Profit", justify="right", width=8)
    table.add_column("ROI", justify="right", width=6)
    table.add_column("Time", justify="right", width=6)
    table.add_column("Diff", width=8)
    table.add_column("$/hr", justify="right", width=8)

    rows = []
    for cat_name, cat_devices in devices.items():
        if device_type != "all" and cat_name != device_type:
            continue
        for dev in cat_devices:
            avg_buy = (dev["buy_min"] + dev["buy_max"]) / 2
            avg_sell = (dev["sell_min"] + dev["sell_max"]) / 2
            net_sell = calc_ebay_payout(avg_sell, config)
            shipping = config["shipping"].get(cat_name.rstrip("s"), 8.0)
            profit = net_sell - avg_buy - dev["kit_cost"] - shipping
            roi = (profit / (avg_buy + dev["kit_cost"])) * 100
            hourly = profit / (dev["time_minutes"] / 60) if dev["time_minutes"] > 0 else 0
            
            rows.append({
                "category": cat_name,
                "model": dev["model"],
                "storage": dev.get("storage", ""),
                "buy_min": dev["buy_min"],
                "buy_max": dev["buy_max"],
                "avg_buy": avg_buy,
                "kit_cost": dev["kit_cost"],
                "sell_min": dev["sell_min"],
                "sell_max": dev["sell_max"],
                "avg_sell": avg_sell,
                "net_sell": net_sell,
                "profit": profit,
                "roi": roi,
                "difficulty": dev["difficulty"],
                "time_minutes": dev["time_minutes"],
                "hourly": hourly,
            })

    # Sort
    sort_keys = {
        "profit": lambda r: r["profit"],
        "roi": lambda r: r["roi"],
        "hourly": lambda r: r["hourly"],
        "difficulty": lambda r: {"Easy": 0, "Medium": 1, "Hard": 2}[r["difficulty"]],
        "time": lambda r: r["time_minutes"],
        "buy": lambda r: r["avg_buy"],
        "sell": lambda r: r["avg_sell"],
        "name": lambda r: r["model"],
    }
    key_fn = sort_keys.get(sort_by, sort_keys["profit"])
    rows.sort(key=key_fn, reverse=reverse)

    for i, r in enumerate(rows, 1):
        color = profit_color(r["profit"])
        profit_style = f"bold {color}"
        
        device_name = f"{r['model']} ({r['storage']})" if r['storage'] else r['model']
        cat_label = r["category"].rstrip("s").capitalize()
        
        table.add_row(
            str(i),
            device_name,
            cat_label,
            f"${r['buy_min']}-${r['buy_max']}",
            f"${r['kit_cost']}",
            f"${r['sell_min']}-${r['sell_max']}",
            f"${r['net_sell']:.0f}",
            Text(f"${r['profit']:.0f}", style=profit_style),
            Text(f"{r['roi']:.0f}%", style=profit_style),
            f"{r['time_minutes']}m",
            r["difficulty"],
            Text(f"${r['hourly']:.0f}/hr", style=profit_style),
        )

    # Summary footer
    total_avg_profit = sum(r["profit"] for r in rows) / len(rows) if rows else 0
    best = max(rows, key=lambda r: r["profit"]) if rows else {"model": "N/A", "profit": 0}
    best_hourly = max(rows, key=lambda r: r["hourly"]) if rows else {"model": "N/A", "hourly": 0}
    
    summary = (
        f"[bold]Devices:[/] {len(rows)}  |  "
        f"[bold]Avg Profit:[/] ${total_avg_profit:.0f}  |  "
        f"[bold]Best Flip:[/] {best['model']} (${best['profit']:.0f})  |  "
        f"[bold]Best $/hr:[/] {best_hourly['model']} (${best_hourly['hourly']:.0f}/hr)"
    )
    table.caption = summary
    table.caption_style = "dim"

    return table


def main():
    parser = argparse.ArgumentParser(
        description="Device Flip ROI Grid — profitability analysis"
    )
    parser.add_argument(
        "--sort", "-s",
        choices=["profit", "roi", "hourly", "difficulty", "time", "buy", "sell", "name"],
        default="profit",
        help="Sort by column (default: profit)"
    )
    parser.add_argument(
        "--reverse", "-r",
        action="store_true",
        help="Reverse sort order"
    )
    parser.add_argument(
        "--type", "-t",
        choices=["all", "phones", "tablets", "laptops"],
        default="all",
        help="Filter by device type"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of table"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    devices = config["devices"]

    if args.json:
        import json
        rows = []
        for cat_name, cat_devices in devices.items():
            if args.type != "all" and cat_name != args.type:
                continue
            for dev in cat_devices:
                avg_buy = (dev["buy_min"] + dev["buy_max"]) / 2
                avg_sell = (dev["sell_min"] + dev["sell_max"]) / 2
                net_sell = calc_ebay_payout(avg_sell, config)
                shipping = config["shipping"].get(cat_name.rstrip("s"), 8.0)
                profit = net_sell - avg_buy - dev["kit_cost"] - shipping
                roi = (profit / (avg_buy + dev["kit_cost"])) * 100
                hourly = profit / (dev["time_minutes"] / 60) if dev["time_minutes"] > 0 else 0
                rows.append({
                    "model": dev["model"],
                    "storage": dev.get("storage", ""),
                    "type": cat_name,
                    "buy_min": dev["buy_min"],
                    "buy_max": dev["buy_max"],
                    "kit_cost": dev["kit_cost"],
                    "sell_min": dev["sell_min"],
                    "sell_max": dev["sell_max"],
                    "net_sell": round(net_sell, 2),
                    "profit": round(profit, 2),
                    "roi_pct": round(roi, 1),
                    "difficulty": dev["difficulty"],
                    "time_minutes": dev["time_minutes"],
                    "hourly_rate": round(hourly, 2),
                })
        print(json.dumps(rows, indent=2))
        return

    table = build_table(devices, config, args.sort, args.type, args.reverse)
    console.print(table)
    
    # Quick picks
    console.print()
    console.print(Panel.fit(
        "[bold green]🍒 Sweet Spot Picks:[/]\n"
        "• [bold]iPhone 13 (128GB)[/] — $110 profit, 30min, easiest repair, massive supply\n"
        "• [bold]iPhone 12 (128GB)[/] — $110 profit, 30min, cheapest buy-in\n"
        "• [bold]iPad 9th Gen[/] — $75 profit, 25min, cheapest parts\n"
        "• [bold]Dell XPS 15[/] — $285 profit, 60min, highest absolute margin",
        title="Quick Picks",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
