# 🚀 Power BI AI Assistant - Setup & Deployment Guide

## Table of Contents

1. [Quick Setup (5 minutes)](#quick-setup)
2. [Full Configuration](#full-configuration)
3. [Interactive Mode](#interactive-mode)
4. [Advanced Integration](#advanced-integration)
5. [Troubleshooting](#troubleshooting)

---

## Quick Setup

### Step 1: Prerequisites

- ✅ Microsoft Fabric Workspace (or Python 3.8+)
- ✅ OpenAI API Key (free trial available)
- ✅ Access to your Lakehouse/Delta tables

### Step 2: Set API Key

```bash
# macOS/Linux
export OPENAI_API_KEY='sk-proj-***REMOVED***'

# Windows PowerShell
$env:OPENAI_API_KEY='sk-proj-***REMOVED***'

# Windows Command Prompt
set OPENAI_API_KEY= 'sk-proj-***REMOVED***'
```

### Step 3: Open Notebook

1. Go to Microsoft Fabric Workspace
2. Create new Notebook
3. Upload or paste content from `PowerBI_AI_Assistant.ipynb`
4. Attach to your Lakehouse

### Step 4: Run All Cells

Execute cells in order:

```
Cell 1:  Setup & Dependencies ✓
Cell 2:  Environment Config ✓
Cell 3:  Spark Data Loader ✓
Cell 4:  Metadata Extractor ✓
Cell 5:  Context Builder ✓
Cell 6:  DAX Generation ✓
Cell 7:  Validation Engine ✓
Cell 8:  Duplicate Detection ✓
Cell 9:  Explanation Module ✓
Cell 10: Interactive Agent ✓
```

### Step 5: Launch Assistant

In the "Interactive Mode" cell, uncomment:

```python
pbi_assistant.run_interactive_loop()
```

Then run it!

---

## Full Configuration

### Customize for Your Model

#### 1. Update Table Metadata

Edit `SparkDataLoader.get_available_tables()`:

```python
def get_available_tables(self) -> List[str]:
    # These will be auto-loaded from Spark
    # For Fabric: automatically reads from Lakehouse
    tables = self.spark.catalog.listTables()
    return [t.name for t in tables]
```

#### 2. Define Relationships

Edit `SemanticModelMetadata._build_metadata()`:

```python
self.metadata["relationships"] = [
    {
        "name": "Sales_Product",
        "from_table": "Sales",
        "from_column": "ProductKey",
        "to_table": "Product",
        "to_column": "ProductKey"
    },
    # Add your relationships HERE
    {
        "name": "Sales_Customer",
        "from_table": "Sales",
        "from_column": "CustomerKey",
        "to_table": "Customer",
        "to_column": "CustomerKey"
    }
]
```

#### 3. Add Existing Measures

```python
self.metadata["measures"] = {
    "Total_Sales": {
        "expression": "SUM(Sales[Amount])",
        "description": "Total sum of sales amount"
    },
    # Add your MEASURES HERE
    "YoY_Growth": {
        "expression": "...",
        "description": "..."
    }
}
```

#### 4. Set Business Rules

Edit `AIContextBuilder._build_base_prompt()`:

```python
prompt += "\nBUSINESS RULES:\n"
prompt += "• Use OrderDate for time-based calculations\n"
prompt += "• Sales is the fact table (most granular)\n"
prompt += "• Product, Customer, Region are dimensions\n"
# Add your BUSINESS RULES HERE
```

---

## Interactive Mode

### Start the Assistant

```python
pbi_assistant.run_interactive_loop()
```

### Sample Commands

**Measure Creation:**

```
🤖 You> create measure average order value
⏳ Generating...
✨ Generated Measure: Average_Order_Value
   Expression: SUM(Sales[Amount]) / COUNTA(Sales[OrderID])
   Explanation: This measure calculates the average value...
   Save to registry? (y/n): y
```

**Validation:**

```
🤖 You> validate SUM(Sales[InvalidColumn])
❌ Validation: FAILED
   ⚠️  Column 'Sales[InvalidColumn]' not found in model
   → Use one of these columns: Amount, OrderID, OrderDate...
```

**Check Model:**

```
🤖 You> schema
📊 SEMANTIC MODEL SUMMARY
   Tables: Sales, Product, Region, Customer (4 total)
   Relationships: 5
   Measures: 8
```

**Export Registry:**

```
🤖 You> export dax
-- Power BI Semantic Model DAX Script
-- Generated: 2026-03-18T10:30:00

Average_Order_Value =
SUM(Sales[Amount]) / COUNTA(Sales[OrderID])
```

### All Commands

| Command                                 | Purpose                | Example                        |
| --------------------------------------- | ---------------------- | ------------------------------ |
| `create [measure\|flag\|column] [desc]` | Create new item        | `create measure total revenue` |
| `schema`                                | View model structure   | `schema`                       |
| `registry`                              | List all measures      | `registry`                     |
| `validate [dax]`                        | Validate DAX syntax    | `validate SUM(Sales[Amount])`  |
| `explain [dax]`                         | Explain DAX            | `explain SUM(Sales[Amount])`   |
| `suggest [dax]`                         | Get optimization tips  | `suggest SUM(Sales[x])`        |
| `export [json\|dax]`                    | Export registry        | `export dax`                   |
| `docs [measure]`                        | Generate documentation | `docs Total_Sales`             |
| `status`                                | Session status         | `status`                       |
| `help`                                  | Show all commands      | `help`                         |
| `exit`                                  | Quit assistant         | `exit`                         |

---

## Advanced Integration

### Connect to Power BI REST API

Add model update capability:

```python
from powerbi_rest_api import PowerBIClient

def apply_measure_to_model(measure_name: str, expression: str,
                          dataset_id: str, workspace_id: str):
    """Apply generated measure to actual Power BI model"""
    client = PowerBIClient(auth_token=your_token)

    # Add measure to dataset
    client.add_measure(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        measure_name=measure_name,
        dax_expression=expression
    )

    logger.info(f"✓ Applied {measure_name} to Power BI model")
```

### Version Control with Git

```python
def commit_measure(name: str, expression: str, commit_msg: str):
    """Track measure creation in Git"""
    with open(f"measures/{name}.dax", "w") as f:
        f.write(expression)

    os.system(f'git add measures/{name}.dax')
    os.system(f'git commit -m "{commit_msg}"')
```

### Approval Workflow

```python
def request_approval(measure_name: str, expression: str) -> bool:
    """Send measure for approval before applying"""
    approval_request = {
        "measure": measure_name,
        "expression": expression,
        "created_by": current_user,
        "status": "pending"
    }

    # Send to approval system (email, Teams, etc.)
    send_for_approval(approval_request)

    # Wait for approval
    return wait_for_approval(measure_name)
```

### Azure DevOps Integration

```python
def create_work_item(measure_name: str, description: str):
    """Create Azure DevOps task for new measure"""
    from azure.devops.connection import Connection
    from azure.identity import DefaultAzureCredential

    organization_url = 'https://dev.azure.com/your-org'
    credentials = DefaultAzureCredential()
    connection = Connection(base_url=organization_url, creds=credentials)

    work_item_client = connection.clients.get_work_item_tracking_client()

    work_item_client.create_work_item(
        document=[/* patch document */],
        project='YourProject',
        type='Task'
    )
```

---

## Troubleshooting

### Issue: "OPENAI_API_KEY not found"

**Check if environment variable is set:**

```bash
echo $OPENAI_API_KEY  # macOS/Linux
echo %OPENAI_API_KEY%  # Windows
```

**Solution:**

```bash
export OPENAI_API_KEY='sk-proj-***REMOVED***'
```

**Alternative - Set in notebook:**

```python
import os
os.environ['OPENAI_API_KEY'] = 'sk-proj-***REMOVED***'
```

---

### Issue: "Table 'Sales' not found"

**Cause:** Table name mismatch with Lakehouse

**Check available tables:**

```python
tables = spark_loader.get_available_tables()
print(tables)
```

**Verify table exists in Lakehouse:**

```python
spark.sql("SELECT * FROM Sales LIMIT 1").show()
```

**Solution:**

- Update table names in `SemanticModelMetadata`
- Ensure exact case match (Sales ≠ sales)

---

### Issue: "Column 'OrderDate' not found"

**Cause:** Column name doesn't exist in table

**Check table schema:**

```python
schema = spark_loader.get_table_schema("Sales")
print(schema)
```

**Common fixes:**

- Use underscore_case: `order_date` not `OrderDate`
- Check exact column names
- Update metadata with correct names

---

### Issue: DAX Generation Returns "Fallback Mode"

**Cause:** OpenAI API not available or API key invalid

**Check API key validity:**

```python
from openai import OpenAI

try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "test"}]
    )
    print("✓ API key is valid")
except Exception as e:
    print(f"✗ API error: {e}")
```

**Solutions:**

- Verify API key is correct
- Check API credits/billing
- Try different model: `gpt-3.5-turbo`

---

### Issue: "Validation failed: Unbalanced brackets"

**Cause:** DAX expression has mismatched parentheses

**Check bracket count:**

```python
expr = "SUM(Sales[Amount)]"  # Missing closing paren
print(f"Open: {expr.count('(')}, Close: {expr.count(')')}")  # 1, 0
```

**Solution:**

```python
expr = "SUM(Sales[Amount])"  # Fixed
```

---

### Issue: Performance is slow

**Cause:** Too many rows being analyzed

**Solutions:**

```python
# Limit sample data
spark_loader.get_sample_data("Sales", limit=1000)

# Simplify expressions
# Avoid: FILTER with complex logic
# Prefer: CALCULATE with simple filters

# Use aggregation tables
# Pre-aggregate at source if possible
```

---

## Performance Optimization

### Optimize DAX Generation

```python
# Use temperature=0.2 for consistent outputs
def fast_generate(request: str):
    return dax_engine.client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,  # Lower = faster, more consistent
        max_tokens=500,   # Limit token usage
        messages=[...]
    )
```

### Cache Metadata

```python
# Pre-load and cache metadata
metadata_cache = {
    "tables": metadata.metadata["tables"],
    "relationships": metadata.metadata["relationships"],
    "measures": metadata.metadata["measures"]
}

# Reuse instead of reloading
def get_cached_schema(table_name):
    return metadata_cache["tables"].get(table_name)
```

### Batch Processing

```python
# Generate multiple measures at once
measures_to_create = [
    ("Total_Sales", "Sum all sales"),
    ("Total_Quantity", "Count items sold"),
    ("Average_Price", "Average product price")
]

for name, description in measures_to_create:
    result = dax_engine.generate_dax(description, "measure")
    measure_registry.register_measure(name, result['expression'])
```

---

## Testing

### Unit Tests

```python
def test_validation():
    dax = "SUM(Sales[Amount])"
    is_valid, errors = validator.validate_dax(dax)
    assert is_valid
    assert len(errors) == 0

def test_duplicate_detection():
    assert measure_registry.measure_exists("Total_Sales")

def test_dax_generation():
    result = dax_engine.generate_dax("Create total sales", "measure")
    assert result['name'] is not None
    assert result['expression'] is not None
```

### Integration Tests

```python
# Test full pipeline
def test_end_to_end():
    # 1. Generate
    result = dax_engine.generate_dax("Average sales", "measure")

    # 2. Validate
    is_valid, _ = validator.validate_dax(result['expression'])
    assert is_valid

    # 3. Register
    success = measure_registry.register_measure(
        result['name'],
        result['expression']
    )
    assert success
```

---

## Next Steps

1. ✅ Set up environment variables
2. ✅ Run notebook cells
3. ✅ Launch interactive mode
4. ✅ Test with example requests
5. ✅ Customize for your model
6. ✅ Integrate with Power BI API (optional)
7. ✅ Share with team

---

## Support Resources

- **Power BI DAX Syntax:** https://learn.microsoft.com/en-us/dax/
- **Microsoft Fabric Docs:** https://learn.microsoft.com/fabric/
- **OpenAI API:** https://platform.openai.com/docs/
- **GitHub Issues:** Post questions in project repo

---

**Last Updated:** March 18, 2026  
Version: 1.0 ✅ Production-Ready

Happy creating! 🚀
