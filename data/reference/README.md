# UrbanMart classification reference data

`categories.json` contains the nine approved UrbanMart category labels and their
definitions. `business_rules.json` contains only the supplied business context,
channels, delivery promise, service response goal, management guidance, decision
authority, and classification label definitions.

Category entries use this shape:

```json
{
  "categories": [
    {"name": "Exact category label from the brief", "description": "Brief-grounded meaning"}
  ]
}
```

The business-rules document requires these top-level fields:

- `business`
- `main_customer_channels`
- `rules`
- `management_priority`
- `improvement_approach`
- `decision_authority`
- `classification_guidance`, containing the three exact sentiment labels and three
  exact severity labels

Each operational rule has `id`, `category`, and `rule`. See
`business_rules.json` for the complete valid structure. An empty `rules` list is
valid when a future brief contains no applicable operational rules.

Every business-rule category must match a category name exactly. The application
also rejects duplicate category names, unknown fields, and an empty category list.

`urbanmart_dataset_manifest.json` is the source-of-truth used to build and test the
workbook. Its shape is:

```json
{
  "expected_rows": 30,
  "records": [
    {
      "feedback_id": "F001",
      "submitted_at": "01-Sep-2026",
      "rating": 2,
      "feedback_text": "Original wording",
      "source": "Online Survey"
    }
  ]
}
```

The shortened example above illustrates the structure; the committed manifest
contains all 30 supplied records.
