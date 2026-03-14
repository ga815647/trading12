import argparse
import sys
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.portfolio import update_holdings, get_detailed_holdings

def main():
    parser = argparse.ArgumentParser(description="Portfolio Trade Recorder CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new position")
    add_parser.add_argument("--symbol", required=True, help="Stock symbol (e.g., 2330)")
    add_parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Entry date (YYYY-MM-DD)")
    add_parser.add_argument("--price", type=float, required=True, help="Entry price")
    add_parser.add_argument("--horizon", type=int, default=10, help="Holding horizon in trading days")
    add_parser.add_argument("--hypothesis", default="manual", help="Hypothesis ID")
    add_parser.add_argument("--direction", choices=["long", "short"], default="long", help="Trade direction")

    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a position")
    remove_parser.add_argument("--symbol", required=True, help="Stock symbol to remove")
    remove_parser.add_argument("--force", action="store_true", help="Skip confirmation")

    # List command
    subparsers.add_parser("list", help="List all current holdings")

    args = parser.parse_args()

    if args.command == "add":
        success = update_holdings(
            symbol=args.symbol,
            action="add",
            entry_date=args.date,
            entry_price=args.price,
            horizon_days=args.horizon,
            hypothesis_id=args.hypothesis,
            direction=args.direction
        )
        if success:
            print(f"Successfully added position: {args.symbol} @ {args.price} on {args.date}")
        else:
            print(f"Failed to add position: {args.symbol}")

    elif args.command == "remove":
        if not args.force:
            confirm = input(f"Are you sure you want to remove {args.symbol}? (y/n): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                return

        success = update_holdings(symbol=args.symbol, action="remove")
        if success:
            print(f"Successfully removed position: {args.symbol}")
        else:
            print(f"Failed to remove position: {args.symbol}")

    elif args.command == "list":
        holdings = get_detailed_holdings()
        if not holdings:
            print("No current holdings.")
            return

        print(f"{'Symbol':<8} {'Entry Date':<12} {'Price':<10} {'Horizon':<8} {'Hypothesis':<15}")
        print("-" * 55)
        for h in holdings:
            print(f"{h['symbol']:<8} {h['entry_date']:<12} {h['entry_price']:<10.2f} {h['horizon_days']:<8} {h['hypothesis_id']:<15}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
