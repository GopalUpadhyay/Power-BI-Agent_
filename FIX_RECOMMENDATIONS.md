# DETAILED RECOMMENDATIONS & FIX STRATEGIES

## Critical Issue #1: Empty Model Code Generation

### Current Behavior (BROKEN)

```
User creates model → No files uploaded → Asks for "total sales" measure
Generated Code: "Total_Sales = SUM(Sales[SalesAmount])"
Result: ❌ Error in Power BI (table 'Sales' doesn't exist)
```

### Recommended Fix

**Location:** `assistant_app/core.py` - `SemanticModelMetadata.__init__()` and `DAXGenerator.generate()`

```python
# ADD VALIDATION
class SemanticModelMetadata:
    def __init__(self, metadata_dict):
        self.tables = metadata_dict.get('tables', {})
        self.relationships = metadata_dict.get('relationships', [])
        # NEW: Track if initialized with real data
        self.is_empty = len(self.tables) == 0

    def validate_ready_for_generation(self):
        if self.is_empty:
            return False, "Model has no tables. Please upload CSV/PBIX files first."
        if len(self.tables) < 1:
            return False, "At least 1 table required to generate code."
        return True, "Model ready"
```

**Location:** `assistant_app/cli.py` - `build_agent()`

```python
def build_agent(api_key, metadata_override):
    # NEW: Validate metadata before creating agent
    validator = SemanticModelMetadata(metadata_override)
    is_valid, message = validator.validate_ready_for_generation()

    if not is_valid and not api_key:  # No API key = fallback to sample (OK for demo)
        logger.warning(f"Model not ready: {message}")
        # Log warning but allow fallback mode

    return Agent(...)
```

**Location:** `assistant_app/ui.py` - Generate form submit

```python
if submit:
    # NEW: Check model is not empty
    active_metadata = model_store.load_metadata(active_model["id"])
    tables_count = len(active_metadata.get('tables', {}))

    if tables_count == 0:
        st.error("❌ Model '{active_model[name]}' is empty!")
        st.info("✅ Steps to fix:\n1. Upload CSV files in Model Hub\n2. Auto-detect schema\n3. Come back to Generate")
        st.stop()

    # Then proceed with generation
    result = agent.generate_item(...)
```

---

## Critical Issue #2: Model Context Isolation

### Current Behavior (BROKEN)

```
Model A tables: [Sales, Product]
Model B tables: [Employees, Departments]
User switches to Model B
Generates "total sales"
Result: Code still references Sales table OR uses wrong context
```

### Recommended Fix

**Location:** `assistant_app/ui.py` - Universal assistant initialization

```python
# CURRENT (WRONG):
if "universal_assistant" not in st.session_state:
    st.session_state.universal_assistant = _build_universal_assistant(api_key_input, metadata=active_metadata)

# BETTER:
# Force rebuild if model changed
model_changed = st.session_state.get("last_model_id") != active_model["id"]

if ("universal_assistant" not in st.session_state
    or model_changed
    or st.session_state.get("universal_api_key") != api_key_input):

    st.session_state.universal_assistant = _build_universal_assistant(
        api_key_input,
        metadata=active_metadata  # ← Ensure current model's metadata
    )
    st.session_state.universal_api_key = api_key_input
    st.session_state.last_model_id = active_model["id"]  # ← Track model ID

    # Log the change
    st.info(f"✓ Switched to model: {active_model['name']}")
```

**Add validation in generation:**

```python
def run_once(self, prompt, target):
    # Validate prompt references existing tables
    mentioned_tables = self._extract_table_references(prompt)
    available_tables = list(self.store.metadata.get('tables', {}).keys())

    for table in mentioned_tables:
        if table.lower() not in [t.lower() for t in available_tables]:
            self.explanation = f"⚠️ Warning: Referenced table '{table}' not found in model. Available: {available_tables}"
            logger.warning(self.explanation)

    # Proceed with generation
    ...
```

---

## Critical Issue #3: CSV Validation

### Current Behavior (BROKEN)

```
Upload CSV:
  "ProductID,Price|Quantity"  ← Wrong delimiter (| instead of ,)
  "1,2|5"

Result: ❌ Silent failure. Metadata shows 1 column "Price|Quantity" instead of 2
```

### Recommended Fix

**Location:** `assistant_app/model_store.py` - `_ingest_file_into_metadata()`

```python
def _ingest_file_into_metadata(self, model_id: str, file_path: Path) -> Dict[str, str]:
    """NEW: Add validation"""
    metadata = self.load_metadata(model_id)

    if file_path.suffix.lower() in {".csv", ".tsv"}:
        result = self._validate_and_ingest_csv(file_path)
        if not result['valid']:
            return {
                'status': 'error',
                'message': result['error_message'],
                'suggestions': result['suggestions']
            }

        # Ingest validated data
        ...

def _validate_and_ingest_csv(self, file_path: Path) -> Dict:
    """NEW: Validate CSV before ingestion"""
    try:
        df = pd.read_csv(file_path, nrows=5)  # Sample first 5 rows

        # Check for issues
        if df.shape[1] < 1:
            return {
                'valid': False,
                'error_message': "CSV has no columns",
                'suggestions': ["Check file has header row"]
            }

        if any(df.columns.str.len() > 100):
            return {
                'valid': False,
                'error_message': "CSV has invalid column names (too long or corrupted)",
                'suggestions': ["Check delimiter matches your file (comma vs tab?)",
                              "Re-save as CSV with proper formatting"]
            }

        # Check for mixed types suggesting wrong delimiter
        suspicious_cols = [col for col in df.columns if '|' in col or ';' in col]
        if suspicious_cols:
            return {
                'valid': False,
                'error_message': f"Columns contain delimiter characters: {suspicious_cols}",
                'suggestions': ["Your file might use dif delimiter (tab? semicolon?)",
                              "Re-save as CSV with comma delimiter"]
            }

        return {'valid': True}

    except Exception as e:
        return {
            'valid': False,
            'error_message': f"CSV parsing failed: {str(e)}",
            'suggestions': ["File might not be valid UTF-8",
                          "Try opening in Excel and saving as CSV",
                          "Check for non-ASCII characters"]
        }
```

**In UI:** `assistant_app/ui.py`

```python
if st.button("Store Uploaded Files"):
    if not uploads:
        st.warning("No files selected.")
    else:
        errors = []
        success_count = 0

        for up in uploads:
            target_path = model_upload_dir / up.name
            target_path.write_bytes(up.getvalue())

            # NEW: Get validation result
            result = model_store._ingest_file_into_metadata(active_model["id"], target_path)

            if isinstance(result, dict) and result.get('status') == 'error':
                errors.append({
                    'file': up.name,
                    'error': result['message'],
                    'suggestions': result.get('suggestions', [])
                })
            else:
                success_count += 1

        # Show feedback
        if success_count > 0:
            st.success(f"✓ Successfully ingested {success_count} file(s)")

        if errors:
            st.error("❌ Some files had issues:")
            for err in errors:
                st.write(f"**{err['file']}**: {err['error']}")
                for suggestion in err['suggestions']:
                    st.write(f"  → {suggestion}")
```

---

## Critical Issue #4: Relationship Validation

### Current Behavior (BROKEN)

```
Table A: [OrderID], [CustomerID]       (Fact: many-to-one)
Table B: [CustomerID], [CustomerName]  (Dimension)

Auto-detection sees CustomerID in both → Creates relationship
But Direction is wrong! System can't know multi-table aggregation is correct.
```

### Recommended Fix

**Location:** `assistant_app/model_store.py` - `identify_relationships()`

```python
def _detect_relationships(self, model_id: str) -> List[Dict]:
    """Enhanced with validation"""
    metadata = self.load_metadata(model_id)
    tables = metadata.get('tables', {})
    detected = []

    for table1_name, table1_info in tables.items():
        for table2_name, table2_info in tables.items():
            if table1_name >= table2_name:  # Avoid duplicates
                continue

            # Find potential foreign keys
            for col1 in table1_info.get('columns', {}):
                for col2 in table2_info.get('columns', {}):
                    if self._is_valid_relationship(col1, col2, table1_name, table2_name):
                        detected.append({
                            'from_table': table1_name,
                            'from_column': col1,
                            'to_table': table2_name,
                            'to_column': col2,
                            'confidence': self._compute_confidence(col1, col2, table1_info, table2_info),
                            'validated': False,  # NEW: Mark for user review
                        })

    return detected

def _is_valid_relationship(self, col1: str, col2: str, table1: str, table2: str) -> bool:
    """NEW: Strict validation rules"""

    # Rule 1: Names must match exactly (case-insensitive)
    if col1.lower() != col2.lower():
        return False

    # Rule 2: Must follow naming patterns
    # Valid: OrderID ↔ OrderID, CustomerID ↔ CustomerID
    # Invalid: ID ↔ ID (too generic)
    generic_names = {'id', 'key', 'code'}
    if col1.lower() in generic_names or col2.lower() in generic_names:
        # Accept only if combined with table context
        # E.g., OrderID matches (table=Order context) but plain "ID" is too generic
        if not any(table.lower().startswith(col1.lower().replace('id', ''))
                   for table in [table1, table2]):
            return False

    return True

def _compute_confidence(self, col1: str, col2: str, table1: Dict, table2: Dict) -> float:
    """NEW: Confidence score for relationship"""
    score = 0.8  # Base score

    # Bonus for exact semantic match
    if col1.lower() == col2.lower() and col1.lower() in ['customerid', 'orderid', 'productid']:
        score = 0.95

    # Penalty for generic names
    if col1.lower() in ['id', 'key', 'code']:
        score = 0.6

   # Penalty if column appears in many tables (might not be FK)
    similar_col_count = sum(1 for table in [table1, table2]
                           if col1.lower() in str(table).lower())
    if similar_col_count > 2:
        score -= 0.2

    return min(max(score, 0.0), 1.0)
```

**In UI:** Show confidence scores and let users validate

```python
# Show relationships with confidence indicator
for rel in relationships:
    confidence = rel.get('confidence', 0.8)
    confidence_badge = "✅ High" if confidence > 0.8 else "⚠️ Medium" if confidence > 0.6 else "❌ Low"

    st.write(f"{rel['from_table']}.{rel['from_column']} → {rel['to_table']}.{rel['to_column']} [{confidence_badge}]")

st.warning("⚠️ Review confidence scores. Low-confidence relationships may need manual adjustment.")
```

---

## High Priority Issue: Output Type Mismatches

### Location: `assistant_app/fabric_universal.py` - `_enforce_target_output_type()`

**ADD VISUAL FEEDBACK:**

```python
def _enforce_target_output_type(self, generated, intent, target):
    """Enforce output type, show user if correction happened"""

    expected_type = self._get_expected_type(target)
    actual_type = generated.get('type', '')

    if expected_type.lower() not in actual_type.lower():
        # Need to correct
        original_explanation = generated.get('explanation', '')
        generated = self._fallback(...)  # Regenerate in correct type

        # NEW: Add visible correction notice
        correction_notice = f"⚠️ **Note:** Output was auto-corrected from {actual_type} to {expected_type}. "
        generated['explanation'] = correction_notice + "\n\n" + generated.get('explanation', '')
        generated['auto_corrected'] = True

        logger.info(f"Auto-corrected {actual_type} → {expected_type} for target {target}")

    return generated
```

**In Streamlit UI:** Show the correction notice prominently

```python
if u_result.get('auto_corrected'):
    st.warning("⚠️ Output type was automatically corrected to match your selection")

st.code(u_result.get("code", ""), language=...)
```

---

## TESTING CHECKLIST

Before releasing to corporate users, verify:

### ✅ Empty Model Test

```python
model = store.create_model("Test")
result = agent.generate_item("Create measure")
assert result['error'] or result['validation_errors'] or "Warning" in result['explanation']
```

### ✅ Model Isolation Test

```
Model A: [SalesAmount], [Orders]
Model B: [EmployeeCount]
Switch to Model B → Generate "sales" → Should NOT reference [SalesAmount]
```

### ✅ CSV Validation Test

```python
bad_csv = "Name|Age|Salary"  # Wrong delimiter
model.upload(bad_csv)
assert result['status'] == 'error'
assert 'delimiter' in result['suggestions']
```

### ✅ Relationship Validation Test

```python
# Generic ID shouldn't auto-relate
table1['data'] = {ID: ..}
table2['data'] = {ID: ..}
relationships = model.detect_relationships()
assert len(relationships) == 0  # Should NOT detect false positive
```

### ✅ Output Type Consistency Test

```python
for target in ['semantic', 'warehouse', 'notebook']:
    result = assistant.run_once("Create measure", target=target)
    assert expected_type_for_target(target) in result['type']
```
