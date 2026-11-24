import asyncio
from core.database.base import get_engine
from sqlalchemy import text

async def check():
    engine = get_engine()
    async with engine.connect() as conn:
        # Check tables
        result = await conn.execute(text('SELECT name FROM sqlite_master WHERE type="table"'))
        tables = [row[0] for row in result.fetchall()]
        print('Tables:', tables)

        # Check alembic_version
        if 'alembic_version' in tables:
            result = await conn.execute(text('SELECT * FROM alembic_version'))
            rows = result.fetchall()
            print('alembic_version:', rows)
        else:
            print('alembic_version table does NOT exist')

    await engine.dispose()

asyncio.run(check())