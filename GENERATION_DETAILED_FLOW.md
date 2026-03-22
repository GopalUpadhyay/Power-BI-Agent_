# Code Generation Pipeline - Detailed Flow

## Complete Request-to-Response Flow

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ USER: Clicks "Generate" Button in UI Tab                    │
│ Inputs: item_type (measure/flag/column/table)               │
│         output_language (DAX/SQL/PySpark/Python)            │
│         description (user description)                      │
│         conditions (optional filters)                       │
│         usage_target (Semantic/Warehouse/Notebook/Script)   │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ UI: ui.py lines 1000-1020                                   │
│ - Validate inputs (item_name required)                      │
│ - Load active_metadata from model store                     │
│ - Build schema_context (lines 1050-1140)                    │
│ - Map usage_target to target (semantic/warehouse/etc)       │
└─────────────────────────────────────────────────────────────┘
        ↓
        ├─────────────────────────────────┬──────────────────────────────┐
        │                                  │                              │
        │ IS DAX AND measure/flag/column?  │ ELSE (SQL/PySpark/Python)    │
        │                                  │                              │
        YES                                NO                             │
        │                                  │                              │
        ↓                                  ↓                              │
┌──────────────────────────────────┐ ┌──────────────────────────────┐    │
│ SMART PATH: FormulaCorrector     │ │ LLM PATH: UniversalAssistant │    │
├──────────────────────────────────┤ ├──────────────────────────────┤    │
│ File: formula_corrector.py:1140  │ │ File: ui.py:1200             │    │
│                                  │ │ Call: UniversalAssistant     │    │
│ 1. Create corrector              │ │    .run_once(prompt, target) │    │
│    FormulaCorrector(metadata)    │ │                              │    │
│                                  │ │ Prompt includes:             │    │
│ 2. Call generate_dax_formula()   │ │ - Item type                  │    │
│    formula, warnings =            │ │ - Description               │    │
│    corrector.generate_dax_formula │ │ - Conditions                │    │
│    (description, item_type)       │ │ - schema_context            │    │
│                                  │ │                              │    │
│ Returns: formula, warnings       │ │ Then calls:                  │    │
│                                  │ │ - MultiLanguageGenerationEngine │
│ └─ Speed: 10-50ms                │ │   .generate(intent)          │    │
│                                  │ │                              │    │
│                                  │ │ Which:                       │    │
│                                  │ │ a) Tries LLM if client      │    │
│                                  │ │ b) Falls back to template   │    │
│                                  │ │ c) Returns code, explanation│    │
│                                  │ │                              │    │
│                                  │ │ └─ Speed: 2-3s (LLM) or    │    │
│                                  │ │           <1ms (fallback)    │    │
└──────────────────────────────────┘ └──────────────────────────────┘    │
        │                                      │                          │
        │ u_result = {                         │ u_result = {             │
        │   "type": "DAX",                     │   "type": output_type,   │
        │   "code": formula,                   │   "code": code,          │
        │   "explanation": "...",              │   "explanation": "...",  │
        │   "validation": "..."                │   "errors": [...],       │
        │ }                                    │   "paste_ready": "..."   │
        │                                      │ }                        │
        └──────────────────┬───────────────────┘                         │
                           ↓
        ┌──────────────────────────────────────────────────────────┐
        │ UI: Lines 1210-1240                                      │
        │ - Register in agent.registry                            │
        │ - Display code with syntax highlighting                │
        │ - Show explanation                                     │
        │ - Show validation issues (if any)                      │
        │ - Display paste-ready version                         │
        └──────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────────────────────────┐
        │ USER: Sees generated code, can:                          │
        │ - Copy to clipboard                                    │
        │ - Run in Power BI / SQL / Notebook                     │
        │ - Edit and save                                       │
        │ - Delete from registry                                │
        └──────────────────────────────────────────────────────────┘
```

---

## Smart Path (DAX) - Detailed Steps

### Step 1: FormulaCorrector Initialization

```python
# ui.py:1140
from .formula_corrector import FormulaCorrector

corrector = FormulaCorrector(active_metadata)
# Creates SemanticColumnMatcher internally
# Indexes all columns by semantic type (amount, cost, id, date, count)
# Identifies fact table
```

### Step 2: Intent Detection

```python
# formula_corrector.py:129-138
def _get_intent(self, description: str) -> str:
    d = description.lower()

    # Keyword matching (SIMPLE)
    if "average" in d:
        return "average"
    elif "profit" in d:
        return "profit"
    elif "ytd" in d or "year" in d:
        return "ytd"
    elif "count" in d or "distinct" in d:
        return "count"
    else:
        return "sum"  # DEFAULT
```

**Current Limitations**:

- Only 4 distinct intents recognized
- Case-insensitive keyword matching
- No semantic analysis (uses regex only)
- "revenue growth" would match "profit" if both present

### Step 3: Column Matching

```python
# formula_corrector.py:93-110
def generate_dax_formula(self, description: str, item_type: str = "measure"):
    # Find fact table (most relationships)
    fact_table = self.matcher.find_fact_table()

    # Route to appropriate generator based on intent
    intent = self._get_intent(description)

    # Get actual columns from metadata
    if intent == "average":
        amt = self.matcher.find_column("amount", fact_table)  # Looks in index
        cnt = self.matcher.find_column("count", fact_table)
        if both found:
            return f"DIVIDE(SUM({amt[0]}[{amt[1]}]), DISTINCTCOUNT({cnt[0]}[{cnt[1]}]))"
        else:
            return "ERROR: Missing columns"
```

**How Column Matching Works**:

```python
# SemanticColumnMatcher._build_index() - formula_corrector.py:34-63
for table_name, table_info in self.tables.items():
    columns = table_info.get("columns", {})
    for col_name in columns.keys():
        col_lower = col_name.lower()

        # Check keywords in order of priority
        if any(kw in col_lower for kw in COUNT_KEYWORDS):  # count first!
            self.index["count"].append((table_name, col_name))
        elif any(kw in col_lower for kw in AMOUNT_KEYWORDS):
            self.index["amount"].append((table_name, col_name))
        elif any(kw in col_lower for kw in COST_KEYWORDS):
            self.index["cost"].append((table_name, col_name))
        # ... etc

# Then find_column() returns first match with optional table preference
def find_column(self, semantic_type: str, prefer_table: str = None):
    candidates = self.index.get(semantic_type, [])  # Get all indexed columns
    if prefer_table:
        for table, col in candidates:
            if table == prefer_table:
                return (table, col)  # Prefer specified table
    return candidates[0] if candidates else None  # Return first match
```

### Step 4: Formula Generation

```python
# Based on intent, route to template generator
if intent == "sum":
    return self._make_sum(fact_table)
elif intent == "average":
    return self._make_average(fact_table)
elif intent == "profit":
    return self._make_profit(fact_table)
elif intent == "ytd":
    return self._make_ytd(fact_table)
elif intent == "flag":
    return self._make_flag(description, fact_table)
```

### Example: "Average Order Value"

```
Input:
  - description: "Average Order Value"
  - item_type: "measure"
  - metadata: {
      "tables": {
        "Sales": {
          "columns": {
            "SalesAmount": "float",
            "OrderID": "int",
            "OrderDate": "date"
          }
        },
        "Product": {...}
      },
      "relationships": [...7 relationships...]
    }

Step 1: Initialize
  → Create SemanticColumnMatcher(metadata)
  → Index columns:
      amount: [(Sales, SalesAmount)]
      count: [(Sales, OrderID)]
      date: [(Sales, OrderDate)]

Step 2: Find fact table
  → Table with most relationships = Sales (has 7 connections)

Step 3: Get intent
  → description.lower() = "average order value"
  → "average" in description? YES
  → intent = "average"

Step 4: Generate average formula
  → Call _make_average(Sales)
  → amt = find_column("amount", Sales) = (Sales, SalesAmount)
  → cnt = find_column("count", Sales) = (Sales, OrderID)
  → Return DIVIDE(SUM(Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))

Output:
  formula = "DIVIDE(SUM(Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))"
  warnings = []  # Empty list, no issues
```

---

## LLM Path (SQL/PySpark) - Detailed Steps

### Step 1: Build Comprehensive Prompt

```python
# ui.py:1050-1140 (builds schema_context)

schema_context = """
=== SCHEMA INFORMATION ===

TABLE STRUCTURES:
  • Sales: ProductKey, OrderID, SalesAmount, OrderDate
  • Product: ProductKey, ProductName, Category
  • Customer: CustomerKey, CustomerName, Region

RELATIONSHIP MAP (for joining):
  • Sales[ProductKey] joins Product[ProductKey]
  • Sales[CustomerKey] joins Customer[CustomerKey]

COLUMN DEFINITIONS:
Sales:
    • ProductKey: ID/KEY (for joins)
    • OrderID: NUMERIC (count/quantity)
    • SalesAmount: NUMERIC (monetary value)
    • OrderDate: DATE/TIME

Product:
    • ProductKey: ID/KEY (for joins)
    • ProductName: TEXT/ATTRIBUTE
    • Category: TEXT/ATTRIBUTE

=== COMMON DAX METRIC PATTERNS ===
Total/Sum: SUM(Sales[SalesAmount])
Average: AVERAGE(Sales[SalesAmount])
Count of Orders: DISTINCTCOUNT(Sales[OrderID])
Average Order Value: DIVIDE(SUM(Sales[SalesAmount]), DISTINCTCOUNT(Sales[OrderID]))

=== OUTPUT REQUIREMENTS ===
For SQL:
  1. Use correct table names
  2. Use GROUP BY with SUM/AVG/COUNT
  3. Use LEFT JOINs to preserve rows
  4. Include WHERE conditions if needed

For PySpark:
  1. Use df.join() for relationships
  2. Use groupBy() with sum/avg/count
  3. Create temp views with createOrReplaceTempView()
  4. Use comments to explain joins
"""
```

### Step 2: Create Prompt for LLM

```python
# ui.py:1170-1200
universal_prompt = f"""
Create measure: Denormalized fact table with all customer and product details

CRITICAL INSTRUCTIONS:
• DO use metric patterns above as templates
• DO use exact column names from COLUMN DEFINITIONS
• DO keep code language consistent: SQL
• DO NOT use columns not listed in schema
• RETURN ONLY the code, no explanation
""" + schema_context
```

### Step 3: Call Universal Assistant

```python
# ui.py:1200
u_result = universal_assistant.run_once(universal_prompt, target="warehouse")

# Which internally:
# 1. Calls MultiLanguageGenerationEngine.generate(intent)
# 2. Which tries LLM first (if client exists)
#    OR falls back to templates immediately
```

### Step 4a: LLM Request (if API available)

```python
# fabric_universal.py:416-445
try:
    response = self.client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,  # Very deterministic
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": "You are a Microsoft Fabric multi-language assistant."
            },
            {
                "role": "user",
                "content": universal_prompt  # All that schema context!
            }
        ]
    )
    text = response.choices[0].message.content

    # Parse response for CODE and EXPLANATION
    code = _extract_block(text, "CODE", "EXPLANATION")
    explanation = _extract_field(text, "EXPLANATION")

    if code:
        return {"type": "SQL", "code": code, "explanation": explanation}
    else:
        # LLM returned empty or unparseable
        raise Exception("Empty LLM response")

except Exception as exc:
    # Any LLM error → fallback to templates
    return None  # Signals fallback
```

### Step 4b: Fallback to Templates

```python
# fabric_universal.py:425-510
def _fallback(self, intent: Dict[str, Any]) -> Dict[str, str]:
    req = intent["raw"].lower()
    t = intent["output_type"]  # "sql_query", "dax_measure", etc

    # Pick columns
    table_name, value_col, date_col = self._pick_core_columns()
    group_col = self._pick_group_column(table, value_col, date_col)

    if t == "sql_query":
        if "join" in req or "denormalize" in req:
            # Multi-table query
            code, note = self._build_sql_join_query(req)
        else:
            # Simple aggregation
            code = f"SELECT {group_col}, SUM({value_col}) FROM {table_name} GROUP BY {group_col};"

    elif t == "pyspark_transformation":
        if "join" in req:
            code, note = self._build_pyspark_join_code(req)
        else:
            code = f"result_df = df.groupBy('{group_col}').sum('{value_col}')"

    return {"type": ..., "code": code, "explanation": "..."}
```

### Example: "Denormalized sales fact table with customer and product details"

```
Input (LLM Path):
  - description: "Denormalized sales fact table with customer and product details"
  - output_language: "SQL"
  - metadata includes relationships:
      Sales → Product, Sales → Customer

Step 1: Build prompt
  → schema_context includes all tables, relationships, columns

Step 2: Create universal_prompt
  → "Create measure: Denormalized sales fact table..."
  → Plus all schema context

Step 3: Call LLM
  → Send prompt to GPT-4o-mini
  → GPT recognizes "denormalized" + "all details"
  → Generates JOIN query

Step 4a (LLM Success):
  → GPT returns:
    """
    CODE:
    SELECT t0.*, t1.ProductName, t2.CustomerName
    FROM Sales t0
    LEFT JOIN Product t1 ON t0.ProductKey = t1.ProductKey
    LEFT JOIN Customer t2 ON t0.CustomerKey = t2.CustomerKey;

    EXPLANATION:
    Joins Sales with Product and Customer to denormalize all attributes.
    """

Step 4b (LLM Failure - uses fallback):
  → API error, quota exceeded, etc.
  → Falls back to _build_sql_join_query()
  → Analyzes relationships
  → Returns similar JOIN query

Output:
  u_result = {
    "type": "SQL",
    "code": "SELECT ... FROM Sales LEFT JOIN Product ... LEFT JOIN Customer ...",
    "explanation": "Denormalized query with all related data"
  }
```

---

## Schema Context - What Gets Passed to LLM

The schema context (lines 1050-1140 in ui.py) includes:

```
1. TABLE STRUCTURES (lines ~1070)
   - Lists each table name
   - Lists column names (comma-separated on one line)
   - Example: "Sales: ProductKey, OrderID, SalesAmount, OrderDate"

2. RELATIONSHIP MAP (lines ~1080)
   - From table[column] joins To table[column]
   - Example: "Sales[ProductKey] joins Product[ProductKey]"
   - Cleans Unicode artifacts (ufeff)

3. COLUMN DEFINITIONS (lines ~1090)
   - For EACH table:
     - For EACH column:
       - Type classification (NUMERIC, DATE, ID, TEXT)
       - Based on column name keywords
   - Example:
     OrderID: NUMERIC (count/quantity)
     SalesAmount: NUMERIC (monetary value)
     OrderDate: DATE/TIME

4. COMMON PATTERNS (lines ~1110)
   - Example metric formulas
   - Shows pattern: SUM(Table[Column])
   - Includes: Average, DISTINCTCOUNT, CALCULATE examples

5. OUTPUT REQUIREMENTS (lines ~1130)
   - Language-specific rules
   - "Use exact column names"
   - "Never sum ID columns"
   - "Use LEFT JOIN"
   - Etc.
```

**Result**: LLM has rich context and examples of what good code looks like

---

## Error Handling & Fallbacks

### When FormulaCorrector Fails

```python
# formula_corrector.py
fact_table = self.matcher.find_fact_table()
if not fact_table:
    return ("ERROR: No tables found", ["No metadata available"])

# The caller (UI) sees this ERROR and:
# 1. Logs warning
# 2. Falls back to universal assistant
# 3. Retries with LLM
```

### When LLM Fails

```python
# fabric_universal.py:447-456
except Exception as exc:
    msg = str(exc).lower()

    # Persistent auth errors? Disable for this run
    if any(code in msg for code in
           ["insufficient_quota", "invalid_api_key", "401", "429"]):
        self.client = None
        log.warning("OpenAI disabled for this run")

    # Any error → return None (triggers fallback to templates)
    return None
```

### When Both Fail

```python
# Both FormulaCorrector and LLM failed, no fallback used
# UI displays:
# 1. Error message
# 2. Empty code block
# 3. Validation issues

# User can:
# - Manually enter formula
# - Upload better metadata
# - Re-try with different description
```

---

## Validation After Generation

### FormulaCorrector Validation

```python
# formula_corrector.py:242-273
def _validate(self, code: str) -> List[str]:
    warnings = []

    # Check 1: Balanced parentheses
    if code.count("(") != code.count(")"):
        warnings.append("❌ Unbalanced parentheses")

    # Check 2: Balanced brackets
    if code.count("[") != code.count("]"):
        warnings.append("❌ Unbalanced brackets")

    # Check 3: SUM on ID column (common mistake)
    if re.search(r"SUM\s*\(\s*\w+\s*\[\s*\w*(?:Key|ID)\w*\s*\]", code):
        warnings.append("⚠️ SUM on ID column - use DISTINCTCOUNT")

    return warnings
```

### ValidationEngine (All Languages)

```python
# fabric_universal.py:846-900
def validate_code(self, generated_type: str, code: str):
    issues = []

    # Check 1: Empty code
    if not code.strip():
        issues.append("Generated code is empty.")

    # Check 2: Syntax balance
    if not _balanced(code):
        issues.append("Unbalanced brackets or parentheses.")

    # Check 3: DAX-specific
    if generated_type == "DAX":
        # Regex find all Table[Column] references
        refs = re.findall(r"(\w+)\[(\w+)\]", code)
        for table, column in refs:
            if table not in self.metadata["tables"]:
                issues.append(f"Table not found: {table}")
            if column not in self.metadata["tables"][table]["columns"]:
                issues.append(f"Column not found: {table}[{column}]")

        # Check for SUM on ID
        if "SUM(" in code and any("ID" in ref[1] or "Key" in ref[1] for ref in refs):
            issues.append("SUM on ID column detected.")

    return issues
```

---

## Performance Characteristics

### FormulaCorrector (DAX)

- **Schema parsing**: ~5ms
- **Intent detection**: <1ms
- **Column matching**: ~5-10ms
- **Template generation**: <1ms
- **Validation**: ~5ms
- **Total**: ~15-25ms (usually completes in 10-50ms)

### LLM Generation (SQL/PySpark)

- **Prompt building**: ~50-100ms
- **API call**: ~2-3 seconds (biggest bottleneck)
- **Response parsing**: ~5-10ms
- **Total**: ~2-3.5 seconds

### Fallback Templates

- **Column selection**: <1ms
- **Query building**: <1ms
- **Total**: <5ms (almost instant)

---

## Summary: Which Path Gets Used When?

| Language | Item Type | API Present? | Path Used                               |
| -------- | --------- | ------------ | --------------------------------------- |
| DAX      | measure   | Yes or No    | ✅ FormulaCorrector (semantic)          |
| DAX      | flag      | Yes or No    | ✅ FormulaCorrector (semantic)          |
| DAX      | column    | Yes or No    | ✅ FormulaCorrector (semantic)          |
| DAX      | table     | Yes or No    | ⚠️ UniversalAssistant → LLM or fallback |
| SQL      | \*        | Yes          | → UniversalAssistant → LLM → Fallback   |
| SQL      | \*        | No           | → UniversalAssistant → Fallback only    |
| PySpark  | \*        | Yes          | → UniversalAssistant → LLM → Fallback   |
| PySpark  | \*        | No           | → UniversalAssistant → Fallback only    |
| Python   | \*        | \*           | → UniversalAssistant → Generic template |

---

**Last Updated**: March 22, 2026  
**Version**: 1.0  
**Accuracy**: High (traced through actual code)
