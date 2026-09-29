"""
risk.py
Rule-based screening risk calculator (diabetes, hypertension, heart disease).

Pure Python: no database, no FastAPI. Every risk gets points from a few
factors, capped at 100, then mapped to Low / Medium / High. Each point added
also records a human-readable reason so the doctor can see WHY.

This is a screening indication, NOT a diagnosis.
Thresholds follow common guidelines (ADA fasting sugar, AHA blood pressure).
"""


def bmi(height_cm: float, weight_kg: float) -> float:
    return round(weight_kg / (height_cm / 100) ** 2, 1)


def bmi_category(value: float) -> str:
    if value < 18.5:
        return "Underweight"
    if value < 25:
        return "Normal"
    if value < 30:
        return "Overweight"
    return "Obese"


def bp_stage(systolic: int, diastolic: int) -> int:
    """0 = normal, 1 = elevated, 2 = stage 1, 3 = stage 2."""
    if systolic >= 140 or diastolic >= 90:
        return 3
    if systolic >= 130 or diastolic >= 80:
        return 2
    if systolic >= 120:
        return 1
    return 0


def level(score: int) -> str:
    if score < 30:
        return "Low"
    if score < 60:
        return "Medium"
    return "High"


def _run(rules) -> dict:
    """rules = [(condition, points, reason), ...]"""
    total, reasons = 0, []
    for condition, points, reason in rules:
        if condition and points:
            total += points
            reasons.append(f"{reason} (+{points})")
    total = min(total, 100)
    return {"score": total, "level": level(total), "reasons": reasons}


def calculate_risk(*, age, gender, height_cm, weight_kg, systolic, diastolic,
                   sugar, cholesterol, smoker, drinker, exercises, family_history) -> dict:
    b = bmi(height_cm, weight_kg)
    stage = bp_stage(systolic, diastolic)
    age_band = 0 if age < 35 else 1 if age < 45 else 2 if age < 60 else 3

    diabetes = _run([
        (sugar >= 126,          45, f"Fasting sugar {sugar} mg/dL (diabetic range)"),
        (100 <= sugar < 126,    25, f"Fasting sugar {sugar} mg/dL (pre-diabetic range)"),
        (b >= 30,               20, f"BMI {b} (obese)"),
        (25 <= b < 30,          10, f"BMI {b} (overweight)"),
        (age_band > 0, [0, 5, 10, 15][age_band], f"Age {age}"),
        (family_history,        10, "Family history"),
        (not exercises,         10, "No regular exercise"),
    ])

    hypertension = _run([
        (stage > 0, [0, 15, 35, 50][stage], f"BP {systolic}/{diastolic} mmHg"),
        (b >= 30,               15, f"BMI {b} (obese)"),
        (25 <= b < 30,           8, f"BMI {b} (overweight)"),
        (age_band > 0, [0, 5, 10, 15][age_band], f"Age {age}"),
        (smoker,                 5, "Smoker"),
        (drinker,                5, "Alcohol use"),
        (family_history,        10, "Family history"),
    ])

    heart = _run([
        (stage > 0, [0, 5, 10, 20][stage], f"BP {systolic}/{diastolic} mmHg"),
        (cholesterol >= 240,    20, f"Cholesterol {cholesterol} mg/dL (high)"),
        (200 <= cholesterol < 240, 10, f"Cholesterol {cholesterol} mg/dL (borderline)"),
        (sugar >= 126,          10, f"Fasting sugar {sugar} mg/dL"),
        (100 <= sugar < 126,     5, f"Fasting sugar {sugar} mg/dL"),
        (smoker,                15, "Smoker"),
        (b >= 30,               10, f"BMI {b} (obese)"),
        (25 <= b < 30,           5, f"BMI {b} (overweight)"),
        (age_band > 0, [0, 5, 10, 20][age_band], f"Age {age}"),
        (gender == "Male",       5, "Male"),
        (family_history,        10, "Family history"),
        (not exercises,          5, "No regular exercise"),
    ])

    scores = [diabetes["score"], hypertension["score"], heart["score"]]
    # Weighted towards the worst risk so one very high risk isn't hidden by averaging.
    overall_score = round(0.6 * max(scores) + 0.4 * sum(scores) / 3)

    return {
        "bmi": b,
        "bmi_category": bmi_category(b),
        "bp_stage": stage,
        "diabetes": diabetes,
        "hypertension": hypertension,
        "heart": heart,
        "overall": {"score": overall_score, "level": level(overall_score)},
    }