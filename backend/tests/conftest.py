import os
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.environ.get("ENV") == "test" or os.environ.get("TESTING") == "true":
    os.environ["MAIL_PROVIDER"] = "mailpit"

from app.db.session import engine


@pytest.fixture(autouse=True)
def clean_database():
    """Reset the database before and after each test so test data does not leak."""
    if os.environ.get("ENV") != "test" and os.environ.get("TESTING") != "true":
        # Do not truncate development database
        yield
        return

    with Session(engine) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE;'))
        session.commit()

    yield

    with Session(engine) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE;'))
        session.commit()
