import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

load_dotenv(Path(__file__).parents[1] / ".env")

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def check_connection() -> bool:
    try:
        get_driver().verify_connectivity()
        return True
    except Exception:
        return False
