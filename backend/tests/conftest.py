import asyncio
import sys

if sys.platform == "win32":
    # psycopg async requiere SelectorEventLoop; el ProactorEventLoop por defecto
    # de pytest-asyncio en Windows no es compatible (ver app/main.py).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
