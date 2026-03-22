import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

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
from .fabric_universal import (
    ContextBuilder,
    DataIngestionLayer,
    DuplicateDetectionEngine,
    ExecutionEngine,
    IntentDetectionEngine,
    MetadataStore,
    ModelDiscoveryEngine,
    MultiLanguageGenerationEngine,
    UniversalFabricAssistant,
    configure_openai_client as configure_universal_client,
    run_agent as run_universal_agent,
)
from .training_engine import FabricModelTrainer


def build_agent(
    api_key: Optional[str] = None,
    metadata_override: Optional[Dict[str, Any]] = None,
    registry_path: Optional[str] = None,
) -> PowerBIAssistantAgent:
    client = configure_openai_client(api_key=api_key)
    loader = None if metadata_override else SparkDataLoader()
    metadata = SemanticModelMetadata(loader=loader, metadata_override=metadata_override)
    resolved_registry_path = Path(registry_path) if registry_path else (Path(__file__).resolve().parents[1] / ".assistant_registry.json")

    # Auto-load training profile if available for this registry/model.
    training_path = resolved_registry_path.parent / (resolved_registry_path.stem + ".training.json")
    if training_path.exists():
        try:
            training_profile = json.loads(training_path.read_text(encoding="utf-8"))
            if isinstance(training_profile, dict):
                metadata.metadata["training_profile"] = training_profile
        except Exception:
            pass

    context_builder = AIContextBuilder(metadata)
    generator = DAXGenerationEngine(client=client, context_builder=context_builder)
    validator = ValidationEngine(metadata)
    registry = MeasureRegistry(metadata, storage_path=resolved_registry_path)
    explainer = ExplanationModule(generator)
    return PowerBIAssistantAgent(
        metadata=metadata,
        generator=generator,
        validator=validator,
        registry=registry,
        explainer=explainer,
    )


def run_demo(agent: PowerBIAssistantAgent) -> None:
    print("\nDEMO MODE: Creating semantic model items\n")
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

    created_count = 0
    for i, req in enumerate(demo_requests, start=1):
        result = agent.generate_item(
            description=req["description"],
            item_type=req["item_type"],
            conditions=req.get("conditions", ""),
            auto_register=True,
        )
        status = "✓" if not result["is_duplicate"] else "✓ (already exists)"
        print(f"[{i}] {result['name']} ({result['item_type']}) {status}")
        if not result["is_duplicate"]:
            created_count += 1
        if result["validation_errors"]:
            print(f"    ⚠ Warning: {', '.join(result['validation_errors'])}")

    print(f"\n✓ Successfully stored {created_count} items in registry")
    print(f"\nTo view expressions, run:")
    print(f"  python run_app.py --show-expression <item-name>")
    print(f"\nTo view all created items, run:")
    print(f"  python run_app.py --created")


def show_flags(agent: PowerBIAssistantAgent) -> None:
    """Display all created flags (without expressions by default)."""
    flags = agent.registry.get_items_by_type('flag')
    
    print("\n" + "=" * 70)
    print(f"FLAGS ({len(flags)})")
    print("=" * 70 + "\n")
    
    if not flags:
        print("✗ No flags created yet.")
        print("\nCreate a flag using:")
        print("  python run_app.py --interactive")
        print("  Then select 'flag' as the item type\n")
        return
    
    existing = [f for f in flags if f['source'] == 'existing']
    generated = [f for f in flags if f['source'] == 'generated']
    
    if existing:
        print(f"EXISTING ({len(existing)})")
        print("-" * 70)
        for i, flag in enumerate(existing, 1):
            print(f"[{i}] {flag['name']}")
            if flag.get('description'):
                print(f"    {flag['description']}")
    
    if generated:
        if existing:
            print()
        print(f"GENERATED ({len(generated)})")
        print("-" * 70)
        for i, flag in enumerate(generated, 1):
            print(f"[{i}] {flag['name']}")
            if flag.get('description'):
                print(f"    {flag['description']}")
            if flag.get('created_at'):
                print(f"    Created: {flag['created_at']}")
    
    print("\n" + "-" * 70)
    print("\nTo view the expression for a flag, run:")
    print("  python run_app.py --show-expression <flag-name>")
    print("=" * 70 + "\n")


def show_registry(agent: PowerBIAssistantAgent, item_type: str | None = None) -> None:
    """Display registry filtered by item type (without expressions)."""
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
    """Display only generated items (without expressions by default)."""
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
        print(f"[{idx}] {item['name']} ({item['item_type']})")
        if item.get("description"):
            print(f"    Description: {item['description']}")
        if item.get("created_at"):
            print(f"    Created: {item['created_at']}")

    print("\n" + "-" * 70)
    print("\nTo view the expression for an item, run:")
    print("  python run_app.py --show-expression <item-name>")
    print("\nExamples:")
    if created_items:
        print(f"  python run_app.py --show-expression {created_items[0]['name']}")
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


def test_created_fields(agent: PowerBIAssistantAgent) -> None:
    """Validate generated fields against current model metadata."""
    created_items = [i for i in agent.registry.items.values() if i.get("source") == "generated"]

    print("\n" + "=" * 70)
    print(f"CREATED FIELD TESTS ({len(created_items)})")
    print("=" * 70 + "\n")

    if not created_items:
        print("No generated items found to test.")
        print("Run --demo or --interactive first.\n")
        return

    passed = 0
    failed = 0
    for idx, item in enumerate(created_items, start=1):
        valid, issues = agent.validator.validate_expression(item.get("expression", ""))
        status = "PASS" if valid else "FAIL"
        print(f"[{idx}] {item.get('name', '')} [{item.get('item_type', '')}] -> {status}")
        if valid:
            passed += 1
        else:
            failed += 1
            for issue in issues:
                print(f"    - {issue}")

    print("\n" + "-" * 70)
    print(f"Summary: passed={passed}, failed={failed}, total={len(created_items)}")
    print("=" * 70 + "\n")


def show_expression(agent: PowerBIAssistantAgent, item_name: str) -> None:
    """Display the DAX/Spark expression for a specific item."""
    item = agent.registry.items.get(item_name)
    
    if not item:
        # Try case-insensitive search
        for key, val in agent.registry.items.items():
            if key.lower() == item_name.lower():
                item = val
                break
    
    if not item:
        print(f"\n✗ Item '{item_name}' not found in registry.")
        print(f"\nAvailable items:")
        all_items = list(agent.registry.items.keys())
        if all_items:
            for i, name in enumerate(all_items, 1):
                print(f"  {name}")
        else:
            print("  (no items created yet)")
        print()
        return
    
    print("\n" + "=" * 70)
    print(f"EXPRESSION: {item['name']}")
    print("=" * 70 + "\n")
    
    print(f"Type: {item['item_type']}")
    print(f"Source: {item['source']}")
    if item.get('description'):
        print(f"Description: {item['description']}")
    if item.get('created_at'):
        print(f"Created: {item['created_at']}")
    
    print(f"\nExpression (DAX/Spark Query):")
    print("-" * 70)
    print(item.get('expression', '(no expression)'))
    print("-" * 70 + "\n")


def train_model(agent: PowerBIAssistantAgent) -> None:
    """Train the assistant on current model schema + expression history."""
    expressions = []

    for item in agent.registry.items.values():
        expr = item.get("expression", "")
        if expr:
            expressions.append(expr)

    for measure in agent.metadata.metadata.get("measures", {}).values():
        if isinstance(measure, dict):
            expr = measure.get("expression", "")
            if expr:
                expressions.append(expr)

    profile = FabricModelTrainer.train(agent.metadata.metadata, expressions)
    agent.metadata.metadata["training_profile"] = profile

    # Persist profile to registry storage companion file.
    profile_path = agent.registry.storage_path.parent / (agent.registry.storage_path.stem + ".training.json")
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print("MODEL TRAINING COMPLETED")
    print("=" * 70)
    print(f"Preferred Table       : {profile.get('preferred_table', 'n/a')}")
    print(f"Preferred Value Column: {profile.get('preferred_value_column', 'n/a')}")
    print(f"Preferred Date Column : {profile.get('preferred_date_column', 'n/a')}")
    print(f"Expressions Learned   : {profile.get('observed_expression_count', 0)}")
    print(f"Training Profile File : {profile_path}")
    print("=" * 70 + "\n")



def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI-powered Power BI Semantic Model Assistant"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Groq API key (optional if GROQ_API_KEY is set)",
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
        help="View only generated items (without expressions)",
    )
    parser.add_argument(
        "--show-expression",
        type=str,
        metavar="NAME",
        help="Show the expression/query for a specific item (example: --show-expression Total_Sales)",
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
        "--test-created",
        action="store_true",
        help="Run backend validation tests on generated fields",
    )
    parser.add_argument(
        "--train-model",
        action="store_true",
        help="Train assistant on current model schema and usage patterns",
    )
    parser.add_argument(
        "--fabric-interactive",
        action="store_true",
        help="Run Universal Fabric assistant interactive loop",
    )
    parser.add_argument(
        "--fabric-request",
        type=str,
        help="Run a single Universal Fabric request",
    )
    parser.add_argument(
        "--fabric-target",
        type=str,
        choices=["semantic", "warehouse", "notebook", "python", "dax", "sql", "pyspark"],
        help="Preferred output target for --fabric-request",
    )
    parser.add_argument(
        "--fabric-load-csv",
        type=str,
        help="Load CSV file into Universal Fabric metadata learning store",
    )
    parser.add_argument(
        "--fabric-load-table",
        type=str,
        help="Load Spark/Lakehouse/Warehouse table reference into learning store",
    )
    parser.add_argument(
        "--fabric-discover",
        action="store_true",
        help="Run auto-discovery for tables/relationships in Universal Fabric metadata",
    )
    parser.add_argument(
        "--fabric-identify-relationships",
        action="store_true",
        help="Identify/refresh relationships from current Universal Fabric model metadata",
    )
    parser.add_argument(
        "--fabric-train",
        action="store_true",
        help="Train Universal Fabric model profile from learned metadata and usage history",
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

    if args.fabric_interactive:
        run_universal_agent(api_key=args.api_key)
        return

    if (
        args.fabric_request
        or args.fabric_load_csv
        or args.fabric_load_table
        or args.fabric_discover
        or args.fabric_identify_relationships
        or args.fabric_train
    ):
        store = MetadataStore()
        ingestion = DataIngestionLayer(store)
        discovery = ModelDiscoveryEngine(store)

        if args.fabric_load_csv:
            print(json.dumps(ingestion.load_data(csv_path=args.fabric_load_csv), indent=2))
        if args.fabric_load_table:
            print(json.dumps(ingestion.load_data(table_name=args.fabric_load_table), indent=2))
        if args.fabric_discover:
            print(json.dumps(discovery.discover_model(), indent=2))
        if args.fabric_identify_relationships:
            rels = discovery.detect_relationships(store.metadata.get("tables", {}))
            store.metadata["relationships"] = rels
            store.save_metadata()
            print(json.dumps({"relationship_count": len(rels), "relationships": rels}, indent=2))

        if args.fabric_train:
            client = configure_universal_client(api_key=args.api_key)
            assistant = UniversalFabricAssistant(
                store=store,
                ingestion=ingestion,
                discovery=discovery,
                detector=IntentDetectionEngine(),
                generator=MultiLanguageGenerationEngine(client, context_builder=ContextBuilder(store.metadata)),
                executor=ExecutionEngine(),
                duplicate=DuplicateDetectionEngine(store),
            )
            print(json.dumps(assistant.train_model(), indent=2))

        if args.fabric_request:
            client = configure_universal_client(api_key=args.api_key)
            assistant = UniversalFabricAssistant(
                store=store,
                ingestion=ingestion,
                discovery=discovery,
                detector=IntentDetectionEngine(),
                generator=MultiLanguageGenerationEngine(client, context_builder=ContextBuilder(store.metadata)),
                executor=ExecutionEngine(),
                duplicate=DuplicateDetectionEngine(store),
            )
            result = assistant.run_once(args.fabric_request, target=args.fabric_target)
            print(json.dumps(result, indent=2))
        return

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
    elif args.test_created:
        test_created_fields(agent)
    elif args.train_model:
        train_model(agent)
    elif args.show_expression:
        show_expression(agent, item_name=args.show_expression)
    else:
        print("\nAI-powered Power BI Semantic Model Assistant")
        print("=" * 60)
        print("\nCore Commands:")
        print("  python run_app.py --demo              # Run demo scenario")
        print("  python run_app.py --interactive       # Interactive mode")
        print("\nView Commands:")
        print("  python run_app.py --created           # View all created items")
        print("  python run_app.py --registry          # View all items in registry")
        print("  python run_app.py --flags             # View all flags")
        print("  python run_app.py --list-by-type TYPE # View items by type")
        print("  python run_app.py --schema            # Print schema summary")
        print("  python run_app.py --schema-json       # Print full schema JSON")
        print("\nExpression Commands:")
        print("  python run_app.py --show-expression NAME  # Show expression for item")
        print("\nExport & Test Commands:")
        print("  python run_app.py --export-created-csv FILE  # Export to CSV")
        print("  python run_app.py --test-created      # Validate created fields")
        print("  python run_app.py --train-model       # Train on current model patterns")
        print("\nUniversal Fabric Commands:")
        print("  python run_app.py --fabric-interactive")
        print("  python run_app.py --fabric-load-csv PATH")
        print("  python run_app.py --fabric-load-table TABLE")
        print("  python run_app.py --fabric-discover")
        print("  python run_app.py --fabric-identify-relationships")
        print("  python run_app.py --fabric-train")
        print("  python run_app.py --fabric-request \"Create total sales\" --fabric-target semantic")
        print("\nOptions:")
        print("  --api-key KEY                         # Provide Groq API key")
        print("  --log-level {DEBUG,INFO,WARNING}      # Set logging level")

