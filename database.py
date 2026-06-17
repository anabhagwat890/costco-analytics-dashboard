import os
from typing import Dict, Any
import streamlit as st

def get_db_config() -> Dict[str, Any]:
    """Read database config from Streamlit secrets or environment variables.

    For local pg_hba.conf trust authentication, password can be omitted or blank.
    """
    if "postgres" in st.secrets:
        cfg = dict(st.secrets["postgres"])
    else:
        cfg = {
            "host": os.getenv("PGHOST", "localhost"),
            "port": os.getenv("PGPORT", "5432"),
            "database": os.getenv("PGDATABASE", "zava"),
            "user": os.getenv("PGUSER", "postgres"),
            "password": os.getenv("PGPASSWORD", "YOUR_PASSWORD"),
        }
    cfg.setdefault("host", "localhost")
    cfg.setdefault("port", "5432")
    cfg.setdefault("database", "zava")    # <--- CHANGE THIS to zava
    cfg.setdefault("user", "postgres")    # <--- Corrected this from "zava" to "postgres"
    cfg.setdefault("password", "YOUR_PASSWORD") # <--- ADD YOUR PASSWORD HERE
    return cfg