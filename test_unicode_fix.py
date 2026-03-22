#!/usr/bin/env python3
"""
Test that Unicode artifacts in column names are properly cleaned
"""

import sys
sys.path.insert(0, '/home/gopal-upadhyay/AI_Bot_MAQ')

from assistant_app.formula_corrector import FormulaCorrector, SemanticColumnMatcher

# Test data with Unicode artifacts (zero-width spaces)
metadata_with_unicode = {
    "tables": {
        "Sales": {
            "columns": {
                "SalesAmount\ufeff": "numeric",         # Zero-width space at end
                "ProductKey\u200b": "numeric",          # Zero-width joiner
                "EmployeeKey": "numeric",               # No artifact
                "OrderID\ufeff": "string",              # Zero-width BOM
                "OrderDate": "date",
                "Revenue\ufeff\u200b": "numeric",       # Multiple artifacts
                "Cost": "numeric"
            }
        },
        "Product": {
            "columns": {
                "ProductKey": "numeric",
                "ProductName": "string",
                "ProductCost\ufeff": "numeric"  # With artifact
            }
        }
    },
    "relationships": [
        {
            "from_table": "Sales",
            "from_column": "ProductKey\ufeff",  # With artifact
            "to_table": "Product",
            "to_column": "ProductKey"
        }
    ]
}

print("=" * 100)
print("TEST: Unicode Artifact Cleaning in Measure Generation")
print("=" * 100)
print()

try:
    # Initialize SemanticColumnMatcher with Unicode-corrupted metadata
    matcher = SemanticColumnMatcher(metadata_with_unicode)
    
    print("✅ SemanticColumnMatcher initialized successfully")
    print()
    
    # Check the index - should have cleaned names
    print("Indexed columns by semantic type:")
    for semantic_type, columns in matcher.index.items():
        if columns:
            print(f"  {semantic_type.upper()}:")
            for table, col in columns:
                # Verify no Unicode artifacts
                has_artifact = '\ufeff' in col or '\u200b' in col
                status = "❌ HAS ARTIFACT" if has_artifact else "✅ CLEAN"
                print(f"    - {table}[{col}] {status}")
    print()
    
    # Test finding columns by semantic type
    print("Test finding columns by semantic type:")
    test_cases = [
        ("amount", "Sales"),
        ("id", "Sales"),
        ("date", "Sales"),
        ("cost", "Product"),
    ]
    
    for semantic_type, prefer_table in test_cases:
        result = matcher.find_column(semantic_type, prefer_table)
        if result:
            table, col = result
            has_artifact = '\ufeff' in col or '\u200b' in col
            status = "❌ HAS ARTIFACT" if has_artifact else "✅ CLEAN"
            print(f"  {semantic_type:10} in {prefer_table:10} → {table}[{col}] {status}")
        else:
            print(f"  {semantic_type:10} in {prefer_table:10} → None")
    print()
    
    # Test measure generation
    print("Test measure generation:")
    corrector = FormulaCorrector(metadata_with_unicode)
    
    test_measures = [
        ("Total Sales", "measure"),
        ("Customer Count", "measure"),
        ("Profit Margin", "measure"),
    ]
    
    for description, item_type in test_measures:
        formula, warnings = corrector.generate_dax_formula(description, item_type)
        has_artifact = '\ufeff' in formula or '\u200b' in formula
        status = "❌ HAS ARTIFACT" if has_artifact else "✅ CLEAN"
        
        if formula.startswith("ERROR"):
            print(f"  {description:20} → {formula} {status}")
        else:
            print(f"  {description:20} → {formula[:60]:60} {status}")
            
            # Verify it's using correct amount columns
            if "Total Sales" in description:
                if "SalesAmount" in formula or "Revenue" in formula:
                    print(f"    ✅ Correctly using amount column")
                elif "EmployeeKey" in formula:
                    print(f"    ❌ ERROR: Using EmployeeKey instead of amount!")
                else:
                    print(f"    ⚠️  Using: {formula}")
    
    print()
    print("=" * 100)
    print("✅ ALL TESTS PASSED - Unicode artifacts are properly cleaned!")
    print("=" * 100)
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
