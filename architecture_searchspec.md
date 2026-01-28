# SearchSpec Schema (Authoritative)

## Purpose
Defines the canonical SearchSpec schema used by the parser, ranking, alerts, and UI.

## Schema version
- schema_version: v1

## Canonical SearchSpec
```
{
  "schema_version": "v1",
  "search_spec_id": "uuid",
  "created_at": "timestamp",
  "raw_prompt": "string",
  "hard": {
    "price_max": 0,
    "price_min": 0,
    "beds_min": 0,
    "baths_min": 0,
    "neighborhoods_include": ["string"],
    "neighborhoods_exclude": ["string"],
    "commute_max": [
      { "target_label": "string", "mode": "transit" | "walk" | "bike" | "drive", "max_min": 0 }
    ],
    "must_have": ["string"],
    "exclude": ["string"],
    "available_now": true,
    "move_in_after": "date"
  },
  "soft": {
    "weights": { "string": 0.0 },
    "nice_to_have": ["string"],
    "vibe": ["string"]
  },
  "exploration": {
    "pct": 0,
    "rules": ["string"]
  }
}
```

## Validation rules
- schema_version must equal v1.
- price_min and price_max must be non-negative; price_min <= price_max when both provided.
- beds_min and baths_min are non-negative.
- commute_max entries must include target_label, mode, and max_min.
- neighborhoods arrays may be empty but must not include unknown values; parser normalizes aliases.
- must_have and exclude entries are normalized to canonical feature identifiers.
- available_now and move_in_after are mutually exclusive if both would conflict; reject with field-level error.

## Normalization rules
- trim whitespace, normalize casing on string fields.
- map neighborhood aliases to canonical names.
- canonicalize must_have and exclude to internal identifiers.

## Backward compatibility
- Only v1 is accepted; any other version returns a version error.
