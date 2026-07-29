"""D1 特征契约验证脚本 (离线, 不依赖 pytest)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from unittest.mock import MagicMock
from app.core.model_engine import ModelEngine
from app.core.feature_maps import DEFAULTS, STR_TO_NUM

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"PASS: {name}")
        passed += 1
    else:
        print(f"FAIL: {name} {detail}")
        failed += 1

# 1. Mappings
check("SleepDurationOrdinal mapping",
      STR_TO_NUM["Sleep Duration"] == {"Less than 5 hours": 0, "5-6 hours": 1, "7-8 hours": 2, "More than 8 hours": 3})
check("DietaryHabitsOrdinal mapping",
      STR_TO_NUM["Dietary Habits"] == {"Unhealthy": 0, "Moderate": 1, "Healthy": 2})
check("AgeGroup mapping",
      STR_TO_NUM["AgeGroup"] == {"<=18": 0, "19-25": 1, "26-35": 2, "36-45": 3, "46-60": 4, "60+": 5})
check("WPS mapping",
      STR_TO_NUM["Working Professional or Student"] == {"Working Professional": 0, "Student": 1})

# 2. Defaults
for col in ["SleepDurationOrdinal", "DietaryHabitsOrdinal", "AgeGroup", "Working Professional or Student"]:
    check(f"DEFAULTS[{col}]", col in DEFAULTS)

# 3. _build_structured_input generates derived columns
raw = {"age": 20, "gender": 1, "sleep_duration": 4.0, "stress_level": 2,
       "academic_pressure": 2, "financial_pressure": 2, "family_history": 0, "cgpa": 3.0}
feat_names = ["Age", "Gender", "Sleep Duration", "Dietary Habits",
              "SleepDurationOrdinal", "DietaryHabitsOrdinal", "AgeGroup",
              "Working Professional or Student"]
mock = MagicMock()
mock.named_steps = {}
result = ModelEngine._build_structured_input(raw, feat_names, mock)
check("sleep=4.0 -> SleepDurationOrdinal=0", result.get("SleepDurationOrdinal") == 0, f"got {result.get('SleepDurationOrdinal')}")
check("age=20 -> AgeGroup=1", result.get("AgeGroup") == 1, f"got {result.get('AgeGroup')}")
check("WPS from age=20 -> Student=1", result.get("Working Professional or Student") == 1, f"got {result.get('Working Professional or Student')}")

raw2 = {"age": 50, "gender": 1, "sleep_duration": 7.5, "stress_level": 2,
        "academic_pressure": 2, "financial_pressure": 2, "family_history": 0, "cgpa": 3.0}
result2 = ModelEngine._build_structured_input(raw2, feat_names, mock)
check("sleep=7.5 -> SleepDurationOrdinal=2", result2.get("SleepDurationOrdinal") == 2, f"got {result2.get('SleepDurationOrdinal')}")
check("age=50 -> AgeGroup=4", result2.get("AgeGroup") == 4, f"got {result2.get('AgeGroup')}")

# 4. v1.23 not polluted
v123 = ["age", "gender", "cgpa", "stress_level", "sleep_duration", "social_support",
        "financial_pressure", "family_history", "academic_pressure", "exercise_frequency",
        "anxiety", "panic_attack"]
result3 = ModelEngine._build_structured_input(raw, v123, mock)
polluted = [c for c in ["SleepDurationOrdinal", "DietaryHabitsOrdinal", "AgeGroup", "Working Professional or Student"] if c in result3]
check("v1.23 not polluted by derived", len(polluted) == 0, f"polluted: {polluted}")

print(f"\n{'='*40}")
print(f"D1 contract: {passed} passed, {failed} failed")
print(f"{'='*40}")
sys.exit(1 if failed else 0)
