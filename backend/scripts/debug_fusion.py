import traceback, asyncio
from app.core.model_engine import model_engine


async def main():
    try:
        result = await model_engine.predict_fusion(
            features={"age": 20, "gender": 1, "cgpa": 7.5, "stress_level": 3},
            text="最近压力大",
        )
        print("OK:", result)
    except Exception:
        traceback.print_exc()


asyncio.run(main())
