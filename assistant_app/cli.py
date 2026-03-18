import argparse
import csv
import logging
from pathlib import Path

from .core import (
    AIContextBuilder,
    DAXGenerationEngine,
    ExplanationModule,
    MeasureRegistry,
    PowerBIAssistantAgent,
    SemanticModelMetadata,
    SparkDataLoader,
    ValidationEngine,
    configure_openai_client,
)


def build_agent(api_key: str | None = None) -> PowerBIAssistantAgent:
    client = configure_openai_client(api_key=api_key)
    loader = SparkDataLoader()
    metadata = SemanticModelMetadata(loader)
    context_builder = AIContextBuilder(metadata)
    generator = DAXGenerationEngine(client=client, context_builder=context_builder)
    validator = ValidationEngine(metadata)
    registry = MeasureRegistry(metadata)
    explainer = ExplanationModule(generator)
    return PowerBIAssistantAgent(
        metadata=metadata,
        generator=generator,
        validator=validator,
        registry=registry,
        explainer=explainer,
    )


def run_demo(agent: PowerBIAssistantAgent) -> None:
    print("\nDEMO MODE: End-to-end semantic model assistant\n")
    demo_requests = [
        {"item_type": "measure", "description": "Create total sales measure"},
        {
            "item_type": "flag",
            "description": "Create AI pipeline flag",
            "conditions": "where Sales > 1000",
        },
        {
            "item_type": "measure",
            "description": "Create month over month sales growth",
        },
        {
            "item_type": "table",
            "description": "Create top 5 products table by total sales",
        },
    ]

    for i, req in enumerate(demo_requests, start=1):
        print(f"[{i}] Request: {req['description']}")
        result = agent.generate_item(
            description=req["description"],
            item_type=req["item_type"],
            conditions=req.get("conditions", ""),
            auto_register=True,
        )
        print(f"Name: {result['name']}")
        print("Expression:")
        print(result["expression"])
        if result["validation_errors"]:
            print("Validation issues:")
            for issue in result["validation_errors"]:
                print(f"- {issue}")
        print("Explanation:")
        print(result["explanation"])
        print("-" * 60)

    print("\nRegistry snapshot:")
    print(agent.registry_summary())


def show_flags(agent: PowerBIAssistantAgent) -> None:
    """Display all created flags in detail."""
    flags = agent.registry.get_items_by_type('flag')
    
    print("\n" + "=" * 70)
    print("FLAGS REGISTRY")
    print("=" * 70 + "\n")
    
    if not flags:
        print("✗ No flags created yet.")
        print("\nCreate a flag using:")
        print("  python run_app.py --interactive")
        print("  Then select 'flag' as the item type\n")
        return
    
    print(f"✓ Total flags: {len(flags)}\n")
    
    existing = [f for f in flags if f['source'] == 'existing']
    generated = [f for f in flags if f['source'] == 'generated']
    
    if existing:
        print(f"EXISTING FLAGS ({len(existing)})")
        print("-" * 70)
        for i, flag in enumerate(existing, 1):
            print(f"\n[{i}] {flag['name']}")
            print(f"    Expression: {flag['expression']}")
            if flag['description']:
                print(f"    Description: {flag['description']}")
        print()
    
    if generated:
        print(f"GENERATED FLAGS ({len(generated)})")
        print("-" * 70)
        for i, flag in enumerate(generated, 1):
            print(f"\n[{i}] {flag['name']}")
            print(f"    Expression: {flag['expression']}")
            if flag['description']:
                print(f"    Description: {flag['description']}")
            if flag['created_at']:
                print(f"    Created: {flag['created_at']}")
        print()
    
    print("=" * 70 + "\n")


def show_registry(agent: PowerBIAssistantAgent, item_type: str | None = None) -> None:
    """Display registry filtered by item type."""
    print("\n" + "=" * 70)
    
    if item_type:
        items = agent.registry.get_items_by_type(item_type)
        print(f"REGISTRY - {item_type.upper()}S ({len(items)})")
    else:
        items = list(agent.registry.items.values())
        print(f"FULL REGISTRY ({len(items)} items)")
    
    print("=" * 70 + "\n")
    
    if not items:
        print(f"No {item_type}s found.\n")
        return
    
    # Group by type if showing all
    if not item_type:
        types_dict = {}
        for item in items:
            t = item['item_type']
            if t not in types_dict:
                types_dict[t] = []
            types_dict[t].append(item)
        
        for t in sorted(types_dict.keys()):
            print(f"{t.upper()}S ({len(types_dict[t])})")
            print("-" * 70)
            for item in types_dict[t]:
                status = "✓" if item['source'] == 'generated' else "○"
                print(f"  {status} {item['name']} ({item['source']})")
                if item['description']:
                    print(f"      - {item['description']}")
            print()
    else:
        for item in items:
            status = "✓" if item['source'] == 'generated' else "○"
            print(f"{status} {item['name']} ({item['source']})")
            print(f"   Expression: {item['expression']}")
            if item['description']:
                print(f"   Description: {item['description']}")
            print()
    
    print("=" * 70 + "\n")


def show_created(agent: PowerBIAssistantAgent) -> None:
    """Display only generated items with full expressions."""
    created_items = [i for i in agent.registry.items.values() if i.get("source") == "generated"]

    print("\n" + "=" * 70)
    print(f"CREATED ITEMS ({len(created_items)})")
    print("=" * 70 + "\n")

    if not created_items:
        print("No generated items found yet.")
        print("Run one of these first:")
        print("  python run_app.py --demo")
        print("  python run_app.py --interactive\n")
        return

    for idx, item in enumerate(created_items, start=1):
        print(f"[{idx}] {item['name']}")
        print(f"    Type: {item['item_type']}")
        print(f"    Expression: {item['expression']}")
        if item.get("description"):
            print(f"    Description: {item['description']}")
        if item.get("created_at"):
            print(f"    Created: {item['created_at']}")
        print()

    print("=" * 70 + "\n")


def show_schema(agent: PowerBIAssistantAgent, as_json: bool = False) -> None:
    """Display semantic model schema summary or full JSON."""
    print("\n" + "=" * 70)
    print("SEMANTIC MODEL SCHEMA")
    print("=" * 70 + "\n")

    if as_json:
        print(agent.metadata.as_json())
    else:
        print(agent.metadata.summary())

    print("\n" + "=" * 70 + "\n")


def export_created_csv(agent: PowerBIAssistantAgent, output_path: str) -> None:
    """Export generated items to CSV for reporting and handoff."""
    created_items = [i for i in agent.registry.items.values() if i.get("source") == "generated"]
    path = Path(output_path).expanduser()

    fieldnames = [
        "name",
        "item_type",
        "expression",
        "description",
        "source",
        "created_at",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in created_items:
            writer.writerow(
                {
                    "name": item.get("name", ""),
                    "item_type": item.get("item_type", ""),
                    "expression": item.get("expression", ""),
                    "description": item.get("description", ""),
                    "source": item.get("source", ""),
                    "created_at": item.get("created_at", ""),
                }
            )

    print(f"\nExported {len(created_items)} generated items to: {path}\n")



def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI-powered Power BI Semantic Model Assistant"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (optional if OPENAI_API_KEY is set)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive assistant loop",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run manager-ready demo scenario",
    )
    parser.add_argument(
        "--flags",
        action="store_true",
        help="View all created flags",
    )
    parser.add_argument(
        "--registry",
        action="store_true",
        help="View full registry of all items",
    )
    parser.add_argument(
        "--list-by-type",
        type=str,
        choices=["flag", "measure", "table", "column"],
        help="List items of specific type (flag, measure, table, column)",
    )
    parser.add_argument(
        "--created",
        action="store_true",
        help="View only generated items with output expressions",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print semantic model schema summary",
    )
    parser.add_argument(
        "--schema-json",
        action="store_true",
        help="Print full semantic model schema as JSON",
    )
    parser.add_argument(
        "--export-created-csv",
        type=str,
        metavar="PATH",
        help="Export generated items to CSV (example: --export-created-csv created_items.csv)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    )

    agent = build_agent(api_key=args.api_key)

    if args.demo:
        run_demo(agent)
    elif args.interactive:
        agent.run_interactive_loop()
    elif args.flags:
        show_flags(agent)
    elif args.registry:
        show_registry(agent)
    elif args.list_by_type:
        show_registry(agent, item_type=args.list_by_type)
    elif args.created:
        show_created(agent)
    elif args.schema:
        show_schema(agent, as_json=False)
    elif args.schema_json:
        show_schema(agent, as_json=True)
    elif args.export_created_csv:
        export_created_csv(agent, output_path=args.export_created_csv)
    else:
        print("\nAI-powered Power BI Semantic Model Assistant")
        print("=" * 60)
        print("\nUsage:")
        print("  python run_app.py --demo              # Run demo scenario")
        print("  python run_app.py --interactive       # Interactive mode")
        print("  python run_app.py --flags             # View all flags")
        print("  python run_app.py --registry          # View all items")
        print("  python run_app.py --created           # View generated items + output")
        print("  python run_app.py --schema            # Print schema summary")
        print("  python run_app.py --schema-json       # Print full schema JSON")
        print("  python run_app.py --export-created-csv created_items.csv")
        print("  python run_app.py --list-by-type flag # View only flags")
        print("\nOptions:")
        print("  --api-key KEY                         # Provide API key")
        print("  --log-level {DEBUG,INFO,WARNING}      # Set logging level")

