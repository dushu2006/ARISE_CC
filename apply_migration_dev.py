import asyncio
from alembic.config import Config
from alembic import command
from core.config import load_config

# Use the config's database URL
cfg = load_config()
print(f'Config DB URL: {cfg.database.url}')

# Create alembic config and set the URL
alembic_cfg = Config('core/database/migrations/alembic.ini')
# Override the URL with the config's URL
alembic_cfg.set_main_option('sqlalchemy.url', cfg.database.url)

# Run migration
command.upgrade(alembic_cfg, 'head')
print('Migration applied successfully to dev database')

# Verify
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def verify():
    engine = create_async_engine(cfg.database.url, poolclass=None)
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT * FROM alembic_version'))
        rows = result.fetchall()
        print('alembic_version after:', rows)

        result = await conn.execute(text('PRAGMA table_info(agent_executions)'))
        columns = result.fetchall()
        print('\nagent_executions columns after:')
        for col in columns:
            print(f'  {col}')
    await engine.dispose()

asyncio.run(verify())