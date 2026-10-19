import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.pii_crypto import compute_blind_index
from app.core.security import get_password_hash
from app.models import Base
from app.models.intervention import InterventionPlan, InterventionTemplate
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User

async def main():
    tmp = Path(tempfile.mkdtemp())
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp / "p.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    import app.core.database as dbm
    dbm.AsyncSessionLocal = factory
    async with factory() as db:
        db.add(User(id=701, username="probe", email="p@t.com",
                    email_hash=compute_blind_index("p@t.com", "email"),
                    password_hash=get_password_hash("x"), role="user",
                    status="active", tenant_id=1))
        db.add(InterventionTemplate(template_name="bad", applicable_levels=[2,3,4],
                                    task_list=[], status="active"))
        db.add(RiskAssessment(user_id=701, risk_score=80.0, risk_level=3, assessment_type="fusion", is_latest=True))
        await db.commit()
    calls = []
    oc, orb = AsyncSession.commit, AsyncSession.rollback
    async def _c(self, *a, **k):
        calls.append("commit"); return await oc(self, *a, **k)
    async def _r(self, *a, **k):
        calls.append("rollback"); return await orb(self, *a, **k)
    AsyncSession.commit, AsyncSession.rollback = _c, _r
    from app.services.risk_service import _trigger_warning_and_intervention
    err = None
    try:
        await _trigger_warning_and_intervention(701, 1, 3)
    except Exception as exc:
        err = type(exc).__name__ + ": " + str(exc)
    print("[probe] raised =", err)
    print("[probe] session calls =", calls)
    async with factory() as db:
        w = (await db.execute(select(WarningNotification))).scalars().all()
        p = (await db.execute(select(InterventionPlan))).scalars().all()
    print("[probe] warnings =", len(w), " plans =", len(p))
    await engine.dispose()

asyncio.run(main())


