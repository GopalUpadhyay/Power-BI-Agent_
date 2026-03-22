# NEW FEATURE: Custom Item Name for Generated Content

## What's New ✨

**Item Name field is now REQUIRED and used as the name for all generated content!**

Instead of letting the system auto-generate names or extract names from descriptions, you now have **full control** over what generated content is named.

## How It Works

### Before ❌
```
1. User enters: "Calculate average order value"
2. User enters Item Name: (optional)
3. System generates content
4. System auto-names it or extracts name from description
5. Result: May not match what user intended
```

### After ✅
```
1. User enters Item Name: "Average Order Value"
2. User enters Description: "Calculate the average value of all orders"
3. System generates content
4. Content is saved with name: "Average Order Value"
5. Result: Exactly what user wanted!
```

## Feature Details

### Item Name Field is Now Required

```
┌─────────────────────────────────────────────────────┐
│ Generate New Item                                   │
│                                                     │
│ 💡 Item Name is used as the name for all          │
│    generated content (DAX, SQL, PySpark, etc.)     │
│                                                     │
│ Item Type: [measure ▼]                              │
│ Output Language: [DAX ▼]                            │
│ Where will this be used: [Semantic Model ▼]        │
│                                                     │
│ Item Name (Required - will be the name of ✓         │
│ generated content)                                  │
│ [_________________________________]                │
│  e.g. Total Sales, Customer Count...               │
│                                                     │
│ Description                                        │
│ [_________________________________]                │
│  Create month over month sales growth              │
│                                                     │
│ Conditions (optional)                              │
│ [_________________________________]                │
│  where Sales > 1000                                │
│                                                     │
│ [✓] Auto-register item                             │
│                                                     │
│ [    Generate    ]                                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Item Name field | Optional | Required ✓ |
| Used for naming? | Sometimes | Always ✓ |
| Auto-naming fallback | Yes | No ✓ |
| User control | Partial | Full ✓ |
| Works for all languages | Yes | Yes ✓ |

## Use Cases

### Example 1: Measure Generation
```
Item Name: "Total Monthly Revenue"
Description: "Sum of all sales amounts grouped by month"
Item Type: measure
Output Language: DAX
Usage Target: Semantic Model

Result: Generated measure saved as "Total Monthly Revenue"
```

### Example 2: SQL Table Generation
```
Item Name: "Customer Sales Summary"
Description: "Create a table with customer names and total order amounts"
Item Type: table
Output Language: SQL
Usage Target: Warehouse

Result: SQL table saved as "Customer Sales Summary"
```

### Example 3: PySpark Code Generation
```
Item Name: "Denormalized Sales Analysis"
Description: "Join Sales, Customer, and Product tables"
Item Type: table
Output Language: PySpark
Usage Target: Notebook

Result: PySpark code saved as "Denormalized Sales Analysis"
```

## Validation

The system now validates:

✅ Description is required
✅ **Item Name is required** (NEW!)
✅ Item Name cannot be empty
✅ Item Name must contain at least one character

### Error Messages

If you forget Item Name:
```
❌ Item Name is required - it will be used as the name 
   for the generated content.
```

If you forget Description:
```
❌ Description is required.
```

## Generation Workflow

### Step-by-Step

```
1. Enter Item Name
   ├─ This will be the name of your generated content
   ├─ Example: "Average Customer Lifetime Value"
   └─ Required: No empty values allowed

2. Enter Description
   ├─ What do you want to create?
   ├─ Example: "Calculate avg total spent per customer"
   └─ Required: Must fill this

3. Select Item Type
   ├─ measure (for metrics/KPIs)
   ├─ flag (for true/false indicators)
   ├─ column (for new columns)
   └─ table (for new tables)

4. Select Output Language
   ├─ DAX (for Power BI)
   ├─ SQL (for databases)
   ├─ PySpark (for distributed computing)
   └─ Python (for notebooks)

5. Select Usage Target
   ├─ Semantic Model
   ├─ Warehouse
   ├─ Notebook
   └─ Python Script

6. Optional: Add Conditions
   ├─ Filter criteria (e.g., "where Sales > 1000")
   └─ Not required

7. Click Generate
   └─ Content generated and saved with Item Name

8. See Success Message
   └─ "✓ Saved to Created Items as 'Your Item Name' (measure)"
```

## Success Messages

After generating, you'll see:

### DAX Generation
```
✓ Saved to Created Items as 'Total Sales' (measure)
```

### Non-DAX Generation
```
✓ Saved to Created Items as 'Customer Summary' (table)
```

Both messages confirm that your content is saved with the exact name you provided.

## In the "Created Items" Tab

After generation, you'll see your content in the Created Items tab:

```
NAME: Total Sales              ← Uses your Item Name
TYPE: measure
STATUS: Generated
CREATED BY: AI Generation
LANGUAGE: DAX
DESCRIPTION: Sum of all sales...
```

## Finding Your Generated Content

Since generated content uses your Item Name:

✅ Easy to find later
✅ Easy to remember what each item does
✅ No confusing auto-generated names
✅ Professional organization

Example search:
```
Looking for: "Customer Retention Rate"
Result: Found immediately (not "measure_20260322_143012")
```

## Benefits

### ✓ Full Control
- You choose the name
- No guessing what auto-generated content is called
- Meaningful, professional names

### ✓ Better Organization
- Generated content is named logically
- Easy to find later
- Clean, organized workspace

### ✓ Team Communication
- Names are clear and descriptive
- Team members understand what each item is
- Better documentation

### ✓ Consistency
- Same naming convention for all content types
- Works for DAX, SQL, PySpark equally
- Predictable behavior

## Examples

### Good Item Names ✅
- "Total Sales by Month"
- "Customer Purchase Frequency"
- "Product Profit Margin"
- "Orders Over 1000"
- "Regional Revenue Growth"
- "Year-to-Date Sales"
- "Top 10 Customers by Revenue"
- "Inventory Turnover Ratio"

### Less Helpful Item Names ⚠️
- "Measure" (too generic)
- "Data" (not descriptive)
- "Query" (vague)
- "Test" (unclear purpose)

## Technical Details

### What Changed in Code

**Before:**
```python
if item_name.strip():
    final_item_name = item_name.strip()
else:
    # Extract from description or auto-generate
    final_item_name = extracted_or_auto_name
```

**After:**
```python
# Item Name is required, so always use it
final_item_name = item_name.strip()

# Validation ensures it's not empty
if not item_name.strip():
    st.error("Item Name is required...")
```

### Applies To All Paths

✅ DAX + Semantic Model path
✅ Non-DAX languages (SQL, PySpark, Python)
✅ All item types (measure, flag, column, table)
✅ All output targets
✅ Both manual form and auto-registration

## Support

### Questions?

**Q: What if I don't know what to name the content?**
A: Think about what the content does. For example:
- "Total Revenue" for a sum measure
- "Monthly Average" for an average calculation
- "Active Customers" for a count of unique customers

**Q: Can I change the name after generation?**
A: Yes! Go to "Created Items" tab, find your item, and you can edit its properties.

**Q: Do I need a unique name for each item?**
A: It's recommended, but not required. The system allows duplicates.

**Q: What happens if I use special characters?**
A: Most characters are fine. Avoid: / \ | : * ? " < > 

**Q: Is this required for all generation?**
A: Yes, Item Name is required for ALL content generation (DAX, SQL, PySpark, etc.)

## Deployment Status

✅ **Feature deployed and live!**

- Commit: `2b73ce9`
- Status: All tests passing
- Available: Live on Streamlit Cloud
- Timeline: 2-3 minutes to see changes

### Check It Out

1. Go to your app
2. Hard refresh: Ctrl+Shift+R
3. Go to "Generate" tab
4. See the new required Item Name field
5. Try generating content with a custom name

---

## Summary

**What changed:**
- Item Name is now required for all content generation
- Whatever you write in Item Name is used to name the generated content
- Works for all languages (DAX, SQL, PySpark, Python)
- Applies to all item types (measure, flag, column, table)

**Why:**
- You have full control over naming
- Generated content is organized and professional
- Easy to find and manage later
- Better team communication

**How to use:**
1. Enter Item Name (required)
2. Enter Description
3. Select options
4. Click Generate
5. Content saved with your custom name!

---

**Status:** ✅ Ready to use!  
**Deployment:** Live on Streamlit Cloud  
**Last Updated:** March 2026
