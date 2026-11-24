import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def apply_migration():
    engine = create_async_engine("sqlite+aiosqlite:///./arise_dev.db", poolclass=None)

    async with engine.connect() as conn:
        # Check current alembic version
        result = await conn.execute(text('SELECT * FROM alembic_version'))
        rows = result.fetchall()
        print('Current alembic_version:', rows)

        # Check if columns already exist
        result = await conn.execute(text('PRAGMA table_info(agent_executions)'))
        columns = [row[1] for row in result.fetchall()]
        print('Current columns:', columns)

        if 'created_at' not in columns:
            print('Adding created_at column...')
            await conn.execute(text('ALTER TABLE agent_executions ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP'))

        if 'updated_at' not in columns:
            print('Adding updated_at column...')
            await conn.execute(text('ALTER TABLE agent_executions ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP'))

        # Update alembic version
        print('Updating alembic_version to 0fda01743d48...')
        await conn.execute(text("UPDATE alembic_version SET version_num = '0fda01743d48'"))

        await conn.commit()

        # Verify
        result = await conn.execute(text('SELECT * FROM alembic_version'))
        rows = result.fetchall()
        print('New alembic_version:', rows)

        result = await conn.execute(text('PRAGMA table_info(agent_executions)'))
        columns = result.fetchall()
        print('\nagent_executions columns after:')
        for col in columns:
            print(f'  {col}')

    await engine.dispose()

asyncio.run(apply_migration())