# v1.24 Adapter Selection Report

## Pareto Frontier

| Multiplier | Mean Abs Delta | AUC Loss |
|------------|---------------|----------|
| 0.3 | 4.37 | 0.0196 |
| 0.5 | 4.43 | 0.0196 |
| 0.7 | 4.48 | 0.0196 |
| 0.9 | 4.51 | 0.0195 |

## Selected Configuration

| Parameter | Value |
|-----------|-------|
| Multiplier | 0.3 |
| Mean Abs Delta | 4.37 |
| AUC Original | 0.9131 |
| AUC Adjusted | 0.8934 |
| AUC Loss | 0.0196 |

## Acceptance Criteria

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Mean Abs Delta | < 15 | 4.37 | ✅ |
| AUC Loss | ≤ 0.02 | 0.0196 | ✅ |

## Segment Configuration

```json
{
  "version": "v1.24",
  "type": "piecewise_monotonic",
  "segments": [
    {
      "range": [
        0,
        17
      ],
      "slope": 0.2
    },
    {
      "range": [
        18,
        34
      ],
      "slope": 0.2
    },
    {
      "range": [
        35,
        54
      ],
      "slope": 0.708
    },
    {
      "range": [
        55,
        71
      ],
      "slope": 0.31
    },
    {
      "range": [
        72,
        99
      ],
      "slope": 0.2
    }
  ],
  "clamp": 20,
  "smooth": 3,
  "training_date": "2026-05-02"
}
```
