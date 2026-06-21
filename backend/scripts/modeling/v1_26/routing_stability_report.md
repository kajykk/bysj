# v1.26 Routing Stability Report

- Test cases: 8
- Issues found: 1
- Result: ⚠️ ISSUES FOUND

## Family Distribution
- structured: 2 (0.25)
- lite: 1 (0.125)
- anxiety_only: 4 (0.5)
- insufficient: 1 (0.125)

## Issues
- lite_text_20_chars: expected family='lite', got 'anxiety_only'

## Edge Cases
- lite_text_20_chars: expected lite, actual anxiety_only