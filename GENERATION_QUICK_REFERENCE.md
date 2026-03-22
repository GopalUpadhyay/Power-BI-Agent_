# Code Generation Quick Reference

## Main Generation Functions - Quick Lookup

### 1. FormulaCorrector (DAX Smart Generation)

**File**: `assistant_app/formula_corrector.py`

| Function                 | Line | Input                        | Output                                  | Speed      | Uses LLM |
| ------------------------ | ---- | ---------------------------- | --------------------------------------- | ---------- | -------- |
| `generate_dax_formula()` | 93   | description, item_type       | formula, warnings                       | ⚡ 10-50ms | ❌ No    |
| `_get_intent()`          | 129  | description                  | "sum"\|"average"\|"profit"\|"ytd"       | ⚡ <1ms    | ❌ No    |
| `_make_sum()`            | 197  | fact_table                   | `SUM(Table[Amount])`                    | ⚡ <1ms    | ❌ No    |
| `_make_average()`        | 165  | fact_table                   | `DIVIDE(SUM(...), DISTINCTCOUNT(...))`  | ⚡ <1ms    | ❌ No    |
| `_make_profit()`         | 175  | fact_table                   | `DIVIDE(SUM(amt)-SUM(cost), SUM(amt))`  | ⚡ <1ms    | ❌ No    |
| `_make_ytd()`            | 185  | fact_table                   | `CALCULATE(SUM(...), DATESYTD(...))`    | ⚡ <1ms    | ❌ No    |
| `_make_flag()`           | 147  | description, fact_table      | `IF(SUM(...) > threshold, "Yes", "No")` | ⚡ <1ms    | ❌ No    |
| `correct_dax_formula()`  | 116  | code, description, item_type | corrected_code, warnings                | ⚡ 10-50ms | ❌ No    |

### 2. DAXGenerationEngine (LLM-Based)

**File**: `assistant_app/core.py`

| Function            | Line | Input                              | Output                        | Speed   | Uses LLM |
| ------------------- | ---- | ---------------------------------- | ----------------------------- | ------- | -------- |
| `generate()`        | 401  | item_type, description, conditions | expression, explanation       | 🐢 2-3s | ✅ Yes   |
| `_fallback()`       | 454  | item_type, description, conditions | expression dict               | ⚡ <1ms | ❌ No    |
| `_parse_response()` | 430  | llm_text                           | name, expression, explanation | ⚡ <1ms | ❌ No    |

### 3. MultiLanguageGenerationEngine (Fabric)

**File**: `assistant_app/fabric_universal.py`

| Function                     | Line | Input       | Output             | Speed             | Uses LLM |
| ---------------------------- | ---- | ----------- | ------------------ | ----------------- | -------- |
| `generate()`                 | 415  | intent dict | code, explanation  | 🐢 2-3s / ⚡ <1ms | ✅/❌    |
| `_fallback()`                | 425  | intent      | code, explanation  | ⚡ <1ms           | ❌ No    |
| `_build_sql_join_query()`    | 568  | request     | sql_code, note     | ⚡ <1ms           | ❌ No    |
| `_build_pyspark_join_code()` | 600  | request     | pyspark_code, note | ⚡ <1ms           | ❌ No    |

### 4. UI Integration

**File**: `assistant_app/ui.py`

| Section           | Line | What It Does                   | Calls                                     |
| ----------------- | ---- | ------------------------------ | ----------------------------------------- |
| Generate Tab Init | 969  | Form for new item              | -                                         |
| Form Submission   | 1000 | Process generation request     | ✅                                        |
| DAX Path          | 1140 | Smart DAX generation           | `FormulaCorrector.generate_dax_formula()` |
| Non-DAX Path      | 1200 | LLM generation for SQL/PySpark | `UniversalAssistant.run_once()`           |
| Registration      | 1210 | Save to local registry         | `agent.registry.register()`               |

---

## Generation Templates at a Glance

### DAX Templates (7 Total)

**Template 1: SUM (Default)**

```
When: No specific intent match
Formula: SUM(Table[Amount])
Example: "Total Sales" → SUM(Sales[SalesAmount])
```

**Template 2: AVERAGE**

```
When: "average" in description
Formula: DIVIDE(SUM(amount), DISTINCTCOUNT(count))
Example: "Average Order Value" → DIVIDE(SUM(Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))
```

**Template 3: PROFIT MARGIN**

```
When: "profit" in description
Formula: DIVIDE(SUM(amount) - SUM(cost), SUM(amount))
Example: "Profit Margin" → DIVIDE(SUM(Sales[SalesAmount]) - SUM(Sales[Cost]), SUM(Sales[SalesAmount]))
```

**Template 4: YEAR-TO-DATE**

```
When: "ytd" or "year" in description
Formula: CALCULATE(SUM(amount), DATESYTD(DateTable[Date]))
Example: "YTD Sales" → CALCULATE(SUM(Sales[SalesAmount]), DATESYTD(Dates[Date]))
```

**Template 5: FLAG/CONDITIONAL**

```
When: item_type == "flag"
Formula: IF(SUM(...) > threshold, "Yes", "No")
Example: "Sales > 1000" → IF(SUM(Sales[SalesAmount]) > 1000, "Yes", "No")
```

**Template 6: DISTINCT COUNT**

```
When: Fallback for counts
Formula: DISTINCTCOUNT(Table[Column])
Example: "Count of Orders" → DISTINCTCOUNT(Sales[OrderID])
```

**Template 7: GROWTH (Month-over-Month)**

```
When: LLM fallback, "growth" + "month"
Formula: VAR Current = SUM(...) VAR Prev = CALCULATE(..., DATEADD(..., -1, MONTH)) RETURN DIVIDE(Current - Prev, Prev)
Example: "Monthly Growth" → Two-line VAR formula
```

### SQL Templates

| Scenario        | Template                                                      |
| --------------- | ------------------------------------------------------------- |
| Simple Sum      | `SELECT SUM(column) FROM table;`                              |
| Join            | `SELECT t0.* FROM base LEFT JOIN other ON keys ...;`          |
| Group Aggregate | `SELECT group_col, SUM(value) FROM table GROUP BY group_col;` |

### PySpark Templates

| Scenario        | Template                                  |
| --------------- | ----------------------------------------- |
| Group Aggregate | `df.groupBy('col').sum('value')`          |
| Join            | `df.join(other_df, on='key', how='left')` |
| Create View     | `df.createOrReplaceTempView('view_name')` |

---

## Generation Decision Tree

```
Generate Button Clicked
    ↓
[Item Type, Output Language, Description]
    ↓
Is Output Language = DAX AND Item Type in [measure, flag, column]?
    ├─ YES → Use FormulaCorrector (SMART PATH)
    │   ├─ Identify intent (keywords: "average", "profit", "ytd", etc.)
    │   ├─ Find columns matching intent
    │   ├─ Apply template with matched columns
    │   └─ Return formula
    │
    └─ NO → Use LLM + Fallback (LLM PATH)
        ├─ Has OpenAI API key?
        │   ├─ YES → Call GPT-4o-mini with schema context
        │   │   ├─ Success → Return LLM code
        │   │   └─ Failure → Fall through to fallback
        │   └─ NO → Skip to fallback
        │
        └─ Fallback: Apply language-specific template
            ├─ SQL → Generate JOIN or SELECT
            ├─ PySpark → Generate group/join code
            └─ Python → Return generic transform
```

---

## Semantic Column Matching (Core Intelligence)

### How It Works

**SemanticColumnMatcher** class (formula_corrector.py, lines 1-84)

**Step 1: Index Columns by Type**

```python
AMOUNT_KEYWORDS = ["amount", "sales", "revenue", "price", "total", "value"]
COST_KEYWORDS = ["cost", "expense", "unit cost"]
ID_KEYWORDS = ["key", "id", "identifier"]
DATE_KEYWORDS = ["date", "month", "year", "time"]
COUNT_KEYWORDS = ["count", "number", "distinct", "orders", "orderid"]

# For each table column:
if col_contains("sales", "amount", "revenue"):
    index["amount"].append(column)
elif col_contains("cost", "expense"):
    index["cost"].append(column)
# ... etc
```

**Step 2: Find Fact Table**

```python
# Table with most relationships = fact table
fact_table = max(relationships, key=lambda x: count_of_x)

# If no relationships, pick table with most amount columns
```

**Step 3: Match Intent to Columns**

```python
"Average Order Value"
    → intent = "average"
    → need amount + count columns
    → find_column("amount") → (Sales, SalesAmount)
    → find_column("count") → (Sales, OrderID)
    → return DIVIDE(SUM($Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))
```

### Keyword-Based Intent Recognition

```python
def _get_intent(self, description: str) -> str:
    d = description.lower()
    if "average" in d:       → "average"
    elif "profit" in d:      → "profit"
    elif "ytd" in d or "year" in d: → "ytd"
    return "sum"  # default
```

**Current Keywords**:

- average: "average"
- profit: "profit"
- ytd: "ytd", "year"
- everything else: "sum"

---

## Error Patterns

### When Formula Generation Returns ERROR

| Error                          | Cause                         | Line        | Recovery              |
| ------------------------------ | ----------------------------- | ----------- | --------------------- |
| `ERROR: No tables found`       | Metadata empty                | 97          | User must upload file |
| `ERROR: Missing amount column` | No numeric column found       | 103,173,189 | System uses fallback  |
| `ERROR: Missing columns`       | Requires 2+ columns, found <2 | 172,180     | System uses fallback  |

### User-Facing Validation

```python
# In ValidationEngine (fabric_universal.py, lines 846+)
issues = []

# Check 1: Empty
if not code.strip():
    issues.append("Generated code is empty.")

# Check 2: Balanced syntax
if not _balanced(code):
    issues.append("Unbalanced brackets or parentheses.")

# Check 3: Table/Column exist (DAX only)
for table, column in re.findall(r"(\w+)\[(\w+)\]", code):
    if table not in metadata["tables"]:
        issues.append(f"Table not found: {table}")
    if column not in metadata["tables"][table]["columns"]:
        issues.append(f"Column not found: {table}[{column}]")

# Check 4: ID column summing (common mistake)
if re.search(r"SUM.*\[(.*Key|.*ID)\]", code):
    issues.append("SUM on ID column - use DISTINCTCOUNT")
```

---

## Hardcoded Constants

### Major Assumptions

| Location                 | Constant         | Value         | Alternative                           |
| ------------------------ | ---------------- | ------------- | ------------------------------------- |
| core.py:506 (fallback)   | Default table    | `"Sales"`     | Uses `_pick_trained_schema_targets()` |
| core.py:506 (fallback)   | Default column   | `"Sales"`     | Uses `preferred_value_column`         |
| core.py:512 (fallback)   | Default date     | `"OrderDate"` | Uses `preferred_date_column`          |
| formula_corrector.py:148 | Threshold amount | `"100"`       | Extracted from description via regex  |
| fabric_universal.py:569  | Threshold amount | None (varies) | Template-specific                     |

### Fallback Thresholds

```python
# If user description contains "$1000" or "1000":
if "1000" in description:
    return IF(SUM(...) > 1000, "Yes", "No")
else:
    return IF(SUM(...) > 0, "Yes", "No")  # Default: zero
```

---

## Testing the Generation

### Test Scenarios

```python
# Test 1: Good schema + recognized intent
metadata = {
    "tables": {
        "Sales": {"columns": {"SalesAmount": "float", "OrderID": "int", "Date": "date"}},
        "Product": {"columns": {"ProductKey": "int", "ProductName": "text"}}
    },
    "relationships": [...]
}
desc = "Average Order Value"
→ Expected: DIVIDE(SUM(Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))

# Test 2: Bad schema
metadata = {"tables": {}}
desc = "Total Sales"
→ Expected: ERROR: No tables found

# Test 3: Unrecognized intent
metadata = {...}
desc = "Top 5 products by revenue"
→ Expected: SUM(Sales[SalesAmount])  (falls back to default)

# Test 4: Missing columns
metadata = {"tables": {"Orders": {"columns": {"Price": "float"}}}}
desc = "Average Order Value"
→ Expected: ERROR: Missing columns (can't find OrderID for count)
```

---

## Performance Summary

| Operation                   | Speed       | Bottleneck               |
| --------------------------- | ----------- | ------------------------ |
| FormulaCorrector generation | 10-50ms     | Column matching          |
| LLM generation              | 2-3 seconds | Network, OpenAI API      |
| Schema context building     | 50-200ms    | Large schemas            |
| Total UI roundtrip (DAX)    | 100-300ms   | Fast, user feels instant |
| Total UI roundtrip (LLM)    | 3-5 seconds | API network latency      |

---

## Summary: Why Code Might Be Invalid

1. **Schema Mismatch**: Generated code assumes columns that don't exist
   - Solution: Upload PBIX or provide complete metadata

2. **LLM Hallucination**: GPT generates valid syntax but wrong logic
   - Solution: Validate against test data before use

3. **Insufficient Context**: Metadata incomplete or unclear
   - Solution: Train model with PBIX or provide column name mappings

4. **Template Limits**: Only 7 DAX templates, complex formulas need LLM
   - Solution: Provide custom formula or use LLM with good schema context

5. **Intent Not Recognized**: Description doesn't match keywords
   - Solution: Use richer descriptions or manual formula entry

---

**Document Version**: 1.0  
**Last Updated**: March 22, 2026
