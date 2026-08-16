from app.db.session import engine
from sqlmodel import Session, text

with Session(engine) as session:
    session.exec(text("TRUNCATE TABLE notification, decision, evaluation, application, candidateprofile CASCADE;"))
    session.commit()
    print("All CV records and applications have been cleared!")
