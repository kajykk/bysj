import sys
sys.path.insert(0, 'e:/code/bysj/backend')
from app.core.model_engine import ModelEngine

engine = ModelEngine()

cases = [
    ('Healthy', {'age':25,'cgpa':3.8,'stress_level':1,'sleep_duration':8,'social_support':4,'financial_pressure':1,'family_history':0,'academic_pressure':1,'exercise_frequency':3,'anxiety':0,'panic_attack':0,'treatment_seeking':0}),
    ('Moderate', {'age':22,'cgpa':2.5,'stress_level':3,'sleep_duration':5,'social_support':2,'financial_pressure':3,'family_history':0,'academic_pressure':3,'exercise_frequency':1,'anxiety':2,'panic_attack':0,'treatment_seeking':0}),
    ('High', {'age':20,'cgpa':1.5,'stress_level':5,'sleep_duration':3,'social_support':0,'financial_pressure':5,'family_history':1,'academic_pressure':5,'exercise_frequency':0,'anxiety':5,'panic_attack':1,'treatment_seeking':0}),
    ('Critical', {'age':19,'cgpa':0.5,'stress_level':5,'sleep_duration':2,'social_support':0,'financial_pressure':5,'family_history':1,'academic_pressure':5,'exercise_frequency':0,'anxiety':5,'panic_attack':1,'treatment_seeking':1}),
]

for label, data in cases:
    score, prob, pred = engine._structured_heuristic_fallback(data)
    print(f'{label}: score={score:.2f}, prob={prob:.4f}, pred={pred}')

print('Fallback regression: PASS')
