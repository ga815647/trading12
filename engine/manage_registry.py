import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.lifecycle import LIFECYCLE_FILE, load_lifecycle, save_lifecycle

def confirm_action(message: str) -> bool:
    print(f"\n[WARNING] {message}")
    choice = input("Are you sure? (y/N): ").strip().lower()
    return choice == 'y'

def show_stats():
    registry = load_lifecycle()
    if not registry:
        print("Registry is empty or does not exist.")
        return
        
    stats = {"active": 0, "soft_fail": 0, "hard_fail": 0}
    for record in registry.values():
        status = record.get("status", "unknown")
        if status in stats:
            stats[status] += 1
            
    print("\n=== Strategy Registry Stats ===")
    print(f"Total Records: {len(registry)}")
    print(f"• Active:    {stats['active']}")
    print(f"• Soft Fail: {stats['soft_fail']}")
    print(f"• Hard Fail: {stats['hard_fail']}")

def clear_registry(all_flag: bool, theme: str | None):
    registry = load_lifecycle()
    if not registry:
        print("Nothing to clear.")
        return

    if all_flag:
        if confirm_action("This will PERMANENTLY delete ALL strategy records."):
            save_lifecycle({})
            print("Registry fully cleared.")
        else:
            print("Operation cancelled.")
    elif theme:
        # theme could be 'A', 'K01', etc.
        to_delete = []
        for h_hash, record in registry.items():
            h_id = record.get("id", "")
            if h_id.startswith(theme):
                to_delete.append(h_hash)
        
        if not to_delete:
            print(f"No records found starting with theme prefix: {theme}")
            return
            
        if confirm_action(f"This will delete {len(to_delete)} records belonging to theme '{theme}'."):
            for h_hash in to_delete:
                del registry[h_hash]
            save_lifecycle(registry)
            print(f"Cleared {len(to_delete)} records for theme '{theme}'.")
        else:
            print("Operation cancelled.")

def force_thaw():
    registry = load_lifecycle()
    if not registry:
        print("Nothing to thaw.")
        return

    thawed_count = 0
    to_delete = []
    
    # In orchestrator, thawing happens if the strategy is GONE from registry 
    # OR if we explicitly reset its status. Let's delete soft_fails to trigger re-test.
    for h_hash, record in registry.items():
        if record.get("status") == "soft_fail":
            to_delete.append(h_hash)
            
    if not to_delete:
        print("No soft_fail records found to thaw.")
        return
        
    if confirm_action(f"This will FORCE-THAW {len(to_delete)} soft_fail strategies (unconditional re-test)."):
        for h_hash in to_delete:
            del registry[h_hash]
        save_lifecycle(registry)
        print(f"Successfully force-thawed {len(to_delete)} strategies.")
    else:
        print("Operation cancelled.")

def main():
    parser = argparse.ArgumentParser(description="Strategy Registry Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Stats command
    subparsers.add_parser("stats", help="Show registry statistics")

    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear part or all of the registry")
    clear_parser.add_argument("--all", action="store_true", help="Clear the entire registry")
    clear_parser.add_argument("--theme", help="Clear only strategies with this theme prefix (e.g. A, K01)")

    # Force-thaw command
    subparsers.add_parser("force-thaw", help="Unconditionally thaw all soft_fail strategies")

    args = parser.parse_args()

    if args.command == "stats":
        show_stats()
    elif args.command == "clear":
        if not args.all and not args.theme:
            print("Error: Specify --all or --theme <PREFIX>")
            return
        clear_registry(args.all, args.theme)
    elif args.command == "force-thaw":
        force_thaw()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
