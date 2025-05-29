from database import engine, Base

import schemas

print("[INIT] Creating all tables in the database...")
Base.metadata.create_all(bind=engine)
print("[INIT] Done.")
