<!-- Registry change. CI (`validate`) must pass before merge. -->

## What changed
<!-- New record / edit / deprecation / new category. One line. -->

## Record(s) touched
- id(s):
- type(s): <!-- Tool / Agent / Pseudo-Agent -->

## Checklist
- [ ] Filename stem equals the record `id`
- [ ] `id` is a new, never-reused slug (for new records)
- [ ] Capability statements are problem-shaped and have `support` + `data_sensitivity`
- [ ] `last_verified` is today's date (or the real verification date)
- [ ] Ran `python tools/validate_registry.py` locally and it passed
- [ ] If a new `category` was added, updated BOTH the schema enum and `vocabularies.yaml`

## Notes
<!-- Anything a reviewer should know. -->
