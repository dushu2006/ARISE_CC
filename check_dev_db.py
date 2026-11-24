import asyncio
from core.database.base import get_engine
from sqlalchemy import text

async def check():
    # Use the dev database URL directly
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine("sqlite+aiosqlite:///./arise_dev.db", poolclass=None)

    async with engine.connect() as conn:
        # Check tables
        result = await conn.execute(text('SELECT name FROM sqlite_master WHERE type="table"'))
        tables = [row[0] for row in result.fetchall()]
        print('Tables in arise_dev.db:', len(tables))
        for t in sorted(tables):
            print(f'  {t}')

        # Check alembic_version
        if 'alembic_version' in tables:
            result = await conn.execute(text('SELECT * FROM alembic_version'))
            rows = result.fetchall()
            print('alembic_version:', rows)
        else:
            print('alembic_version table does NOT exist')

        # Check agent_executions columns
        result = await conn.execute(text('PRAGMA table_info(agent_executions)'))
        columns = result.fetchall()
        print('\nagent_executions columns:')
        for col in columns:
            print(f'  {col}')

    await engine.dispose()

asyncio.run(check())