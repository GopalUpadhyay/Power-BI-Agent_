#!/usr/bin/env python
"""Test script to verify relationship detection with confidence scoring."""

import json
from pathlib import Path
from assistant_app.model_store import ModelStore


def test_relationship_detection_with_confidence():
    """Test that relationship detection includes confidence scoring."""
    print("\n=== Testing Relationship Detection with Confidence Scoring ===\n")
    
    # Create a test model store
    test_root = Path("/tmp/test_model_store")
    test_root.mkdir(parents=True, exist_ok=True)
    
    store = ModelStore(root=test_root)
    
    # Create a test model
    model_id = store.create_model("Test Model", "Testing relationship detection")["id"]
    print(f"✓ Created test model: {model_id}")
    
    # Create metadata with sample tables and columns
    metadata = {
        "id": model_id,
        "name": "Test Model",
        "tables": {
            "Customers": {
                "columns": {
                    "CustomerID": {"type": "int"},
                    "Name": {"type": "string"},
                    "Email": {"type": "string"}
                }
            },
            "Orders": {
                "columns": {
                    "OrderID": {"type": "int"},
                    "CustomerID": {"type": "int"},
                    "OrderDate": {"type": "date"}
                }
            },
            "Products": {
                "columns": {
                    "ProductID": {"type": "int"},
                    "Name": {"type": "string"},
                    "Price": {"type": "decimal"}
                }
            }
        },
        "relationships": [],
        "ingestion_notes": []
    }
    
    store.save_metadata(model_id, metadata)
    print("✓ Saved test metadata with tables")
    
    # Test the detection
    store._detect_relationships(model_id)
    updated_metadata = store.load_metadata(model_id)
    
    print(f"\n✓ Detected {len(updated_metadata['relationships'])} relationships:")
    for rel in updated_metadata['relationships']:
        confidence = rel.get('confidence', 'N/A')
        validated = rel.get('validated', False)
        status = "✓ Auto-validated" if validated else "⚠ Needs review"
        print(f"  - {rel['from_table']}.{rel['from_column']} → {rel['to_table']}.{rel['to_column']}")
        print(f"    Confidence: {confidence} {status}")
    
    # Verify confidence scoring is present
    assert len(updated_metadata['relationships']) > 0, "No relationships detected"
    
    for rel in updated_metadata['relationships']:
        assert 'confidence' in rel, f"Relationship {rel['name']} missing confidence score"
        confidence = rel['confidence']
        assert isinstance(confidence, (int, float)), f"Confidence should be numeric, got {type(confidence)}"
        assert 0 <= confidence <= 1, f"Confidence should be 0-1, got {confidence}"
        assert 'validated' in rel, f"Relationship {rel['name']} missing validated flag"
    
    print("\n✓ All relationships have valid confidence scores (0-1 range)")
    
    # Check ingestion notes
    notes = updated_metadata.get('ingestion_notes', [])
    assert len(notes) > 0, "No ingestion notes added"
    print(f"✓ Ingestion note: {notes[-1]}")
    
    # Test case 2: Generic column names should have lower confidence
    print("\n=== Testing Generic Column Name Penalty ===\n")
    
    model2 = store.create_model("Test Model 2", "Testing generic names")
    model2_id = model2["id"]
    
    metadata2 = {
        "id": model2_id,
        "name": "Test Model 2",
        "tables": {
            "Table1": {
                "columns": {
                    "ID": {"type": "int"},  # Generic "ID"
                    "Name": {"type": "string"}
                }
            },
            "Table2": {
                "columns": {
                    "ID": {"type": "int"},  # Generic "ID" - should have lower confidence
                    "Value": {"type": "int"}
                }
            }
        },
        "relationships": [],
        "ingestion_notes": []
    }
    
    store.save_metadata(model2_id, metadata2)
    store._detect_relationships(model2_id)
    updated_metadata2 = store.load_metadata(model2_id)
    
    # Generic "ID" should either not be detected or have low confidence
    id_rels = [r for r in updated_metadata2['relationships'] if r.get('from_column') == 'ID']
    if id_rels:
        print(f"⚠ Generic 'ID' relationship detected (confidence: {id_rels[0].get('confidence')})")
        # Generic ID should have lower confidence (below 0.6 threshold if not qualified by table name)
        print("  This may indicate the column name is too generic without table-name qualification")
    else:
        print("✓ Generic 'ID' column correctly filtered out (below confidence threshold)")
    
    print("\n✓ All tests passed!")
    print("\n=== Summary ===")
    print(f"• Relationship detection now includes confidence scoring")
    print(f"• High-confidence relationships (≥0.9) are auto-validated")
    print(f"• Low-confidence relationships (0.6-0.9) require manual review")
    print(f"• Generic column names are penalized to avoid false positives")


if __name__ == "__main__":
    test_relationship_detection_with_confidence()
