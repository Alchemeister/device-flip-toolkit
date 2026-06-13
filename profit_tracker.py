#!/usr/bin/env python3
"""
Profit Tracker — SQLite database for tracking device flips.
Tracks purchases, repairs, sales, and provides profit analytics.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install rich")
    sys.exit(1)

console = Console()

DB_PATH = Path(__file__).parent / "flips.db"


def get_db() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS flips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            storage TEXT,
            color TEXT,
            source TEXT NOT NULL,
            source_url TEXT,
            buy_price REAL NOT NULL,
            buy_date TEXT NOT NULL,
            repair_type TEXT,
            repair_cost REAL DEFAULT 0,
            repair_time_minutes INTEGER DEFAULT 0,
            repair_notes TEXT,
            sell_price REAL,
            sell_platform TEXT,
            sell_date TEXT,
            sell_url TEXT,
            shipping_cost REAL DEFAULT 0,
            fees REAL DEFAULT 0,
            status TEXT DEFAULT 'bought',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS parts_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_model TEXT NOT NULL,
            part_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            unit_cost REAL NOT NULL,
            source TEXT,
            purchased_date TEXT,
            notes TEXT
        )
    """)
    db.commit()
    return db


def add_flip(args):
    """Add a new device flip to the tracker."""
    db = get_db()
    db.execute("""
        INSERT INTO flips (model, storage, color, source, source_url, buy_price, buy_date,
                          repair_type, repair_cost, repair_time_minutes, repair_notes,
                          status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'bought', ?)
    """, (
        args.model, args.storage, args.color, args.source, args.url,
        args.price, args.date or datetime.now().strftime("%Y-%m-%d"),
        args.repair_type, args.repair_cost or 0, args.repair_time or 0,
        args.repair_notes, args.notes or ""
    ))
    db.commit()
    flip_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    console.print(f"[green]✅ Added flip #{flip_id}: {args.model} — bought for ${args.price:.0f}[/]")


def mark_sold(args):
    """Mark a flip as sold with sale details."""
    db = get_db()
    
    # Get the flip
    flip = db.execute("SELECT * FROM flips WHERE id = ?", (args.id,)).fetchone()
    if not flip:
        console.print(f"[red]Flip #{args.id} not found.[/]")
        return
    
    # Calculate fees
    sell_price = args.price
    # eBay fees: ~13.25% FVF + 2.9% + $0.30 payment processing
    fees = sell_price * 0.1325 + sell_price * 0.029 + 0.30
    shipping = args.shipping or 8.0
    
    db.execute("""
        UPDATE flips SET
            sell_price = ?,
            sell_platform = ?,
            sell_date = ?,
            sell_url = ?,
            shipping_cost = ?,
            fees = ?,
            status = 'sold',
            updated_at = datetime('now')
        WHERE id = ?
    """, (
        sell_price, args.platform or "ebay",
        args.date or datetime.now().strftime("%Y-%m-%d"),
        args.url or "", shipping, round(fees, 2), args.id
    ))
    db.commit()
    
    # Calculate profit
    total_cost = flip["buy_price"] + (flip["repair_cost"] or 0) + shipping + fees
    profit = sell_price - total_cost
    roi = (profit / total_cost * 100) if total_cost > 0 else 0
    
    console.print(f"[green]✅ Flip #{args.id} marked SOLD![/]")
    console.print(f"   Sell price: ${sell_price:.0f} | Total cost: ${total_cost:.0f} | [bold]Profit: ${profit:.0f}[/] ({roi:.0f}% ROI)")


def update_flip(args):
    """Update repair details or notes on an existing flip."""
    db = get_db()
    flip = db.execute("SELECT * FROM flips WHERE id = ?", (args.id,)).fetchone()
    if not flip:
        console.print(f"[red]Flip #{args.id} not found.[/]")
        return
    
    updates = []
    params = []
    
    if args.repair_type:
        updates.append("repair_type = ?")
        params.append(args.repair_type)
    if args.repair_cost is not None:
        updates.append("repair_cost = ?")
        params.append(args.repair_cost)
    if args.repair_time is not None:
        updates.append("repair_time_minutes = ?")
        params.append(args.repair_time)
    if args.repair_notes:
        updates.append("repair_notes = ?")
        params.append(args.repair_notes)
    if args.notes:
        updates.append("notes = ?")
        params.append(args.notes)
    if args.status:
        updates.append("status = ?")
        params.append(args.status)
    
    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(args.id)
        db.execute(f"UPDATE flips SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
        console.print(f"[green]✅ Updated flip #{args.id}[/]")
    else:
        console.print("[yellow]No updates specified.[/]")


def list_flips(args):
    """List all flips with optional filtering."""
    db = get_db()
    
    query = "SELECT * FROM flips WHERE 1=1"
    params = []
    
    if args.status:
        query += " AND status = ?"
        params.append(args.status)
    if args.model:
        query += " AND model LIKE ?"
        params.append(f"%{args.model}%")
    if args.days:
        cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        query += " AND buy_date >= ?"
        params.append(cutoff)
    
    query += " ORDER BY buy_date DESC"
    if args.limit:
        query += f" LIMIT {args.limit}"
    
    flips = db.execute(query, params).fetchall()
    
    if not flips:
        console.print("[yellow]No flips found.[/]")
        return
    
    table = Table(
        title="📊 Device Flip Tracker",
        box=box.ROUNDED,
        header_style="bold white",
        border_style="dim blue",
        show_lines=True,
    )
    
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("Status", width=8)
    table.add_column("Device", style="bold", width=18)
    table.add_column("Bought", width=10)
    table.add_column("Buy $", justify="right", width=7)
    table.add_column("Repair $", justify="right", width=8)
    table.add_column("Sold $", justify="right", width=7)
    table.add_column("Profit", justify="right", width=8)
    table.add_column("ROI", justify="right", width=6)
    table.add_column("Source", width=8)
    
    for flip in flips:
        status_color = {
            "bought": "yellow",
            "repairing": "blue",
            "listed": "cyan",
            "sold": "green",
            "cancelled": "red",
        }.get(flip["status"], "white")
        
        total_cost = flip["buy_price"] + (flip["repair_cost"] or 0) + (flip["shipping_cost"] or 0) + (flip["fees"] or 0)
        profit = (flip["sell_price"] or 0) - total_cost if flip["sell_price"] else 0
        roi = (profit / total_cost * 100) if total_cost > 0 and profit != 0 else 0
        
        profit_style = "green" if profit > 0 else ("red" if profit < 0 else "dim")
        
        device = f"{flip['model']}"
        if flip["storage"]:
            device += f" ({flip['storage']})"
        
        table.add_row(
            str(flip["id"]),
            Text(flip["status"].upper(), style=f"bold {status_color}"),
            device,
            flip["buy_date"] or "-",
            f"${flip['buy_price']:.0f}",
            f"${flip['repair_cost']:.0f}" if flip["repair_cost"] else "-",
            f"${flip['sell_price']:.0f}" if flip["sell_price"] else "-",
            Text(f"${profit:.0f}", style=profit_style) if flip["sell_price"] else "-",
            Text(f"{roi:.0f}%", style=profit_style) if flip["sell_price"] else "-",
            flip["source"],
        )
    
    console.print(table)


def stats(args):
    """Print profit statistics and analytics."""
    db = get_db()
    
    # Overall stats
    total = db.execute("SELECT COUNT(*) FROM flips").fetchone()[0]
    sold = db.execute("SELECT COUNT(*) FROM flips WHERE status = 'sold'").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM flips WHERE status IN ('bought', 'repairing', 'listed')").fetchone()[0]
    
    # Financial stats for sold flips
    sold_flips = db.execute("""
        SELECT buy_price, repair_cost, sell_price, shipping_cost, fees, repair_time_minutes
        FROM flips WHERE status = 'sold'
    """).fetchall()
    
    total_profit = 0
    total_revenue = 0
    total_cost = 0
    total_time = 0
    best_profit = 0
    best_flip = None
    worst_profit = float("inf")
    worst_flip = None
    
    for f in sold_flips:
        cost = f["buy_price"] + (f["repair_cost"] or 0) + (f["shipping_cost"] or 0) + (f["fees"] or 0)
        revenue = f["sell_price"]
        profit = revenue - cost
        total_profit += profit
        total_revenue += revenue
        total_cost += cost
        total_time += f["repair_time_minutes"] or 0
        
        if profit > best_profit:
            best_profit = profit
            best_flip = f
        if profit < worst_profit:
            worst_profit = profit
            worst_flip = f
    
    # Per-model stats
    model_stats = db.execute("""
        SELECT model, COUNT(*) as count, 
               AVG(sell_price - buy_price - COALESCE(repair_cost,0) - COALESCE(shipping_cost,0) - COALESCE(fees,0)) as avg_profit,
               SUM(sell_price - buy_price - COALESCE(repair_cost,0) - COALESCE(shipping_cost,0) - COALESCE(fees,0)) as total_profit
        FROM flips WHERE status = 'sold'
        GROUP BY model ORDER BY total_profit DESC
    """).fetchall()
    
    # Source stats
    source_stats = db.execute("""
        SELECT source, COUNT(*) as count,
               AVG(buy_price) as avg_buy
        FROM flips
        GROUP BY source ORDER BY count DESC
    """).fetchall()
    
    # Print overview
    console.print(Panel.fit(
        f"[bold]Total Flips:[/] {total}  |  "
        f"[bold green]Sold:[/] {sold}  |  "
        f"[bold yellow]Active:[/] {active}  |  "
        f"[bold]Total Profit:[/] [green]${total_profit:.0f}[/]  |  "
        f"[bold]Total Revenue:[/] ${total_revenue:.0f}  |  "
        f"[bold]Avg Margin:[/] {((total_profit/total_revenue*100) if total_revenue > 0 else 0):.0f}%",
        title="💰 Profit Overview",
        border_style="bold green",
    ))
    
    if sold > 0 and best_flip and worst_flip:
        console.print()
        
        # Best/worst
        best_cost = best_flip["buy_price"] + (best_flip["repair_cost"] or 0) + (best_flip["shipping_cost"] or 0) + (best_flip["fees"] or 0)
        worst_cost = worst_flip["buy_price"] + (worst_flip["repair_cost"] or 0) + (worst_flip["shipping_cost"] or 0) + (worst_flip["fees"] or 0)
        
        console.print(f"[bold green]🏆 Best Flip:[/] ${best_profit:.0f} profit (${best_flip['sell_price']:.0f} sell - ${best_cost:.0f} cost)")
        console.print(f"[bold red]📉 Worst Flip:[/] ${worst_profit:.0f} profit (${worst_flip['sell_price']:.0f} sell - ${worst_cost:.0f} cost)")
        
        # Hourly rate
        if total_time > 0:
            hourly = total_profit / (total_time / 60)
            console.print(f"[bold]⏱️  Effective Hourly Rate:[/] ${hourly:.0f}/hr across {total_time} minutes of repair work")
        
        console.print()
        
        # Per-model table
        if model_stats:
            model_table = Table(title="📱 Profit by Model", box=box.SIMPLE, border_style="dim blue")
            model_table.add_column("Model", style="bold", width=20)
            model_table.add_column("Flips", justify="right", width=8)
            model_table.add_column("Avg Profit", justify="right", width=12)
            model_table.add_column("Total Profit", justify="right", width=14)
            
            for m in model_stats:
                profit_color = "green" if m["avg_profit"] > 0 else "red"
                model_table.add_row(
                    m["model"],
                    str(m["count"]),
                    Text(f"${m['avg_profit']:.0f}", style=profit_color),
                    Text(f"${m['total_profit']:.0f}", style=profit_color),
                )
            console.print(model_table)
        
        console.print()
        
        # Source breakdown
        if source_stats:
            source_table = Table(title="🛒 Deals by Source", box=box.SIMPLE, border_style="dim blue")
            source_table.add_column("Source", style="bold", width=12)
            source_table.add_column("Found", justify="right", width=8)
            source_table.add_column("Avg Buy Price", justify="right", width=14)
            
            for s in source_stats:
                source_table.add_row(s["source"], str(s["count"]), f"${s['avg_buy']:.0f}")
            console.print(source_table)


def delete_flip(args):
    """Delete a flip from the tracker."""
    db = get_db()
    flip = db.execute("SELECT * FROM flips WHERE id = ?", (args.id,)).fetchone()
    if not flip:
        console.print(f"[red]Flip #{args.id} not found.[/]")
        return
    
    db.execute("DELETE FROM flips WHERE id = ?", (args.id,))
    db.commit()
    console.print(f"[yellow]🗑️  Deleted flip #{args.id}: {flip['model']}[/]")


def export_csv(args):
    """Export flips to CSV."""
    db = get_db()
    flips = db.execute("SELECT * FROM flips ORDER BY buy_date DESC").fetchall()
    
    import csv
    out_path = args.output or "flips_export.csv"
    
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([col[0] for col in db.execute("PRAGMA table_info(flips)")])
        for flip in flips:
            writer.writerow([flip[col] for col in flip.keys()])
    
    console.print(f"[green]✅ Exported {len(flips)} flips to {out_path}[/]")


def main():
    parser = argparse.ArgumentParser(
        description="Profit Tracker — track device flips from purchase to sale."
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # add
    add_parser = subparsers.add_parser("add", help="Add a new device purchase")
    add_parser.add_argument("model", help="Device model (e.g., 'iPhone 13')")
    add_parser.add_argument("price", type=float, help="Purchase price")
    add_parser.add_argument("--source", "-s", default="ebay", help="Where you bought it")
    add_parser.add_argument("--url", "-u", help="Listing URL")
    add_parser.add_argument("--date", "-d", help="Purchase date (YYYY-MM-DD, default: today)")
    add_parser.add_argument("--storage", default="128GB", help="Storage capacity")
    add_parser.add_argument("--color", default="", help="Device color")
    add_parser.add_argument("--repair-type", default="Screen replacement", help="Type of repair needed")
    add_parser.add_argument("--repair-cost", type=float, help="Estimated repair cost")
    add_parser.add_argument("--repair-time", type=int, help="Estimated repair time (minutes)")
    add_parser.add_argument("--repair-notes", help="Repair notes")
    add_parser.add_argument("--notes", help="General notes")
    
    # sold
    sold_parser = subparsers.add_parser("sold", help="Mark a flip as sold")
    sold_parser.add_argument("id", type=int, help="Flip ID")
    sold_parser.add_argument("price", type=float, help="Sale price")
    sold_parser.add_argument("--platform", "-p", default="ebay", help="Where you sold it")
    sold_parser.add_argument("--date", "-d", help="Sale date (YYYY-MM-DD, default: today)")
    sold_parser.add_argument("--url", "-u", help="Sold listing URL")
    sold_parser.add_argument("--shipping", type=float, help="Shipping cost")
    
    # update
    update_parser = subparsers.add_parser("update", help="Update flip details")
    update_parser.add_argument("id", type=int, help="Flip ID")
    update_parser.add_argument("--repair-type", help="Repair type")
    update_parser.add_argument("--repair-cost", type=float, help="Repair cost")
    update_parser.add_argument("--repair-time", type=int, help="Repair time (minutes)")
    update_parser.add_argument("--repair-notes", help="Repair notes")
    update_parser.add_argument("--notes", help="General notes")
    update_parser.add_argument("--status", choices=["bought", "repairing", "listed", "sold", "cancelled"])
    
    # list
    list_parser = subparsers.add_parser("list", help="List all flips")
    list_parser.add_argument("--status", choices=["bought", "repairing", "listed", "sold", "cancelled"])
    list_parser.add_argument("--model", help="Filter by model")
    list_parser.add_argument("--days", type=int, help="Show last N days")
    list_parser.add_argument("--limit", "-n", type=int, default=50, help="Max results")
    
    # stats
    subparsers.add_parser("stats", help="Show profit statistics")
    
    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete a flip")
    delete_parser.add_argument("id", type=int, help="Flip ID")
    
    # export
    export_parser = subparsers.add_parser("export", help="Export to CSV")
    export_parser.add_argument("--output", "-o", help="Output file path")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    commands = {
        "add": add_flip,
        "sold": mark_sold,
        "update": update_flip,
        "list": list_flips,
        "stats": stats,
        "delete": delete_flip,
        "export": export_csv,
    }
    
    commands[args.command](args)


if __name__ == "__main__":
    main()
