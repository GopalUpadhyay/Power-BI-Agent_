# Relationship Detection Enhancements - Documentation

## Overview

The `ModelStore` class has been enhanced with intelligent relationship detection using confidence scoring to avoid false positives when analyzing model metadata.

## Changes Made

### 1. **New Method: `_detect_relationships()`**

- **Purpose**: Automatically detects relationships between tables based on matching column names
- **Location**: [assistant_app/model_store.py](assistant_app/model_store.py#L230)
- **How it works**:
  - Scans all tables for matching column names across different tables
  - For each match, checks if the column looks like a key (primary/foreign key)
  - Computes a confidence score (0.0 to 1.0) for the relationship
  - Only creates relationships with confidence ≥ 0.6 to avoid false positives
  - Tracks whether each relationship has been auto-validated (confidence ≥ 0.9)

### 2. **New Method: `_compute_relationship_confidence()`**

- **Purpose**: Calculates confidence score for potential relationships
- **Scoring Logic**:
  - **Base Score**: 0.7 for any matching column with key-like naming
  - **Bonus** (+0.2): Column name matches one of the table names (e.g., "CustomerID" matches "Customers")
  - **Penalty** (-0.3): Generic column names like bare "ID", "Key", "Code" (too ambiguous)
  - **Penalty** (-0.15): Generic patterns not qualified by table name
  - **Range**: Clamped to 0.0-1.0

### 3. **New Method: `_is_likely_key_column()`**

- **Purpose**: Identifies columns that look like primary/foreign keys
- **Patterns Recognized**:
  - Columns containing "id" (e.g., CustomerID, ProductID)
  - Columns containing "key" (e.g., PrimaryKey, ForeignKey)
  - Columns containing "code" (e.g., ProductCode, CountryCode)
  - Columns containing "identifier" (e.g., UniqueIdentifier)

### 4. **Integration in `_ingest_file_into_metadata()`**

- Automatically calls `_detect_relationships()` after ingesting any file
- Adds summary messages to ingestion notes about detected relationships:
  - Number of high-confidence relationships (≥0.9) - auto-validated
  - Number of low-confidence relationships (0.6-0.9) - need manual review

## Relationship Structure

Each detected relationship includes:

```python
{
    "name": "Customers_Orders_CustomerID",
    "from_table": "Customers",
    "from_column": "CustomerID",
    "to_table": "Orders",
    "to_column": "CustomerID",
    "confidence": 0.9,  # Confidence score (0.0-1.0)
    "validated": True   # True if auto-validated (confidence >= 0.9)
}
```

## Confidence Score Examples

| Column Match | Table Names             | Confidence | Status           | Reason                                      |
| ------------ | ----------------------- | ---------- | ---------------- | ------------------------------------------- |
| CustomerID   | Customers ↔ Orders      | 0.9        | ✓ Auto-validated | Table-qualified key name                    |
| OrderID      | Orders ↔ OrderDetails   | 0.9        | ✓ Auto-validated | Table-qualified key name                    |
| ID           | Table1 ↔ Table2         | 0.4        | ✗ Filtered       | Too generic (bare "ID")                     |
| ProductKey   | Products ↔ OrderDetails | 0.75       | ⚠ Needs review   | Qualified but uses "Key" pattern            |
| Code         | Region ↔ SalesData      | 0.55       | ✗ Filtered       | Generic pattern without table qualification |

## Benefits

1. **Automatic Relationship Discovery**: Saves manual effort identifying relationships
2. **False Positive Prevention**: Confidence scoring filters out common false matches like bare "ID" columns
3. **Quality Assurance**: High-confidence relationships are auto-validated; low-confidence ones flagged for review
4. **Clear Auditing**: Ingestion notes show how many relationships were detected and their confidence levels
5. **Extensible Design**: Confidence calculation is modular and can be enhanced with more sophisticated patterns

## Testing

A test script ([test_relationship_detection.py](test_relationship_detection.py)) verifies:

1. ✓ Relationships are detected correctly
2. ✓ Confidence scores are calculated and within 0.0-1.0 range
3. ✓ Generic column names are properly penalized
4. ✓ Auto-validation works for high-confidence relationships
5. ✓ Ingestion notes properly track detected relationships

**Test Results**:

```
✓ Detected Customers.CustomerID → Orders.CustomerID with 0.9 confidence (auto-validated)
✓ Generic 'ID' columns correctly filtered out below 0.6 threshold
✓ All relationships have valid confidence scores
```

## Usage Example

```python
from assistant_app.model_store import ModelStore

# Initialize store
store = ModelStore()

# Create a model
model = store.create_model("My Data Model", "Sales data")
model_id = model["id"]

# Add tables with metadata
metadata = {
    "tables": {
        "Customers": {
            "columns": {"CustomerID": "int", "Name": "string"}
        },
        "Orders": {
            "columns": {"OrderID": "int", "CustomerID": "int"}
        }
    },
    "relationships": [],
    "ingestion_notes": []
}
store.save_metadata(model_id, metadata)

# Relationships are auto-detected after ingestion
updated = store.load_metadata(model_id)
print(updated["relationships"])
# Output: [{'name': 'Customers_Orders_CustomerID',
#           'from_table': 'Customers', ...
#           'confidence': 0.9, 'validated': True}]
```

## Future Enhancements

Possible improvements for confidence scoring:

- Semantic analysis of table names (e.g., "Customer" vs "CustomerDim")
- Column type matching (e.g., both numeric types for link columns)
- Cardinality analysis (1:1, 1:N relationships)
- Historical relationship validation based on user feedback
- Support for composite keys (multiple columns)
