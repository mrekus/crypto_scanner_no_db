from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from conf import cfg

metadata = MetaData()
BaseModel = declarative_base(metadata=metadata)

database_url = 'postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}'.format(
            user=cfg.DATABASE['user'],
            password=cfg.DATABASE['password'],
            host=cfg.DATABASE['host'],
            port=cfg.DATABASE['port'],
            database=cfg.DATABASE['database'],
        )

def get_sync_db_engine():
    return create_engine(
        url=database_url,
        echo=cfg.debug,
        pool_size=5,
        max_overflow=10,
    )

def setup(app=None):
    engine = get_sync_db_engine()
    if app is not None:
        app.state.db_engine = engine
    return engine

def get_db():
    db = SessionLocal()
    try:
        yield db
    except:
        db.rollback()
        raise
    finally:
        db.close()


engine = get_sync_db_engine()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
