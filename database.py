"""
Base de dades per gestionar configuració i ús del sistema.
Utilitza SQLite per persistència.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import json

DB_PATH = Path(__file__).parent / "data" / "menag.db"

# Preus per model (per 1M tokens)
MODEL_PRICING = {
    # Anthropic
    "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    # Google
    "gemini-3-flash-preview": {"input": 0.10, "output": 0.40},
    "gemini-3-pro-image-preview": {"input": 0.0, "output": 0.0, "per_image": 0.025},
}


def init_db():
    """Inicialitza la base de dades."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Taula de configuració (API keys)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Taula d'ús de tokens
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            images_generated INTEGER DEFAULT 0,
            cost_usd REAL,
            operation TEXT,
            chapter_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Taula de sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_cost_usd REAL DEFAULT 0,
            presentations_generated INTEGER DEFAULT 0
        )
    """)

    # Taula d'usuaris
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_cost_usd REAL DEFAULT 0,
            presentations_generated INTEGER DEFAULT 0
        )
    """)

    # Taula de presentacions generades (historial de descàrregues)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presentations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE,
            user_name TEXT,
            chapter_name TEXT,
            group_name TEXT,
            slides_count INTEGER,
            cost_usd REAL,
            pptx_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def get_config(key: str) -> Optional[str]:
    """Obté un valor de configuració."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_config(key: str, value: str):
    """Estableix un valor de configuració."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO config (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (key, value))
    conn.commit()
    conn.close()


def get_api_keys() -> Dict[str, str]:
    """Obté les API keys configurades."""
    anthropic_key = get_config("anthropic_api_key") or ""
    google_key = get_config("google_api_key") or ""
    return {
        "anthropic": anthropic_key.strip() if anthropic_key else "",
        "google": google_key.strip() if google_key else ""
    }


def set_api_keys(anthropic_key: str = None, google_key: str = None):
    """Estableix les API keys."""
    if anthropic_key is not None:
        # Netejar espais en blanc i validar
        anthropic_key = anthropic_key.strip()
        if anthropic_key:  # Només guardar si no és buit
            set_config("anthropic_api_key", anthropic_key)
    if google_key is not None:
        # Netejar espais en blanc i validar
        google_key = google_key.strip()
        if google_key:  # Només guardar si no és buit
            set_config("google_api_key", google_key)


def has_valid_keys() -> Dict[str, bool]:
    """Comprova si les API keys estan configurades."""
    keys = get_api_keys()
    return {
        "anthropic": bool(keys["anthropic"] and len(keys["anthropic"]) > 10),
        "google": bool(keys["google"] and len(keys["google"]) > 10)
    }


def log_usage(
    session_id: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    images_generated: int = 0,
    operation: str = "",
    chapter_name: str = ""
):
    """Registra l'ús de tokens i calcula el cost."""
    pricing = MODEL_PRICING.get(model, {"input": 0, "output": 0, "per_image": 0})

    # Calcular cost
    cost = (input_tokens * pricing.get("input", 0) / 1_000_000 +
            output_tokens * pricing.get("output", 0) / 1_000_000 +
            images_generated * pricing.get("per_image", 0))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Inserir registre d'ús
    cursor.execute("""
        INSERT INTO usage (session_id, model, input_tokens, output_tokens,
                          images_generated, cost_usd, operation, chapter_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, model, input_tokens, output_tokens, images_generated,
          cost, operation, chapter_name))

    # Actualitzar o crear sessió
    cursor.execute("""
        INSERT INTO sessions (id, total_cost_usd, presentations_generated)
        VALUES (?, ?, 0)
        ON CONFLICT(id) DO UPDATE SET
        total_cost_usd = total_cost_usd + ?
    """, (session_id, cost, cost))

    conn.commit()
    conn.close()

    return cost


def increment_presentations(session_id: str):
    """Incrementa el comptador de presentacions d'una sessió."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions SET presentations_generated = presentations_generated + 1
        WHERE id = ?
    """, (session_id,))
    conn.commit()
    conn.close()


def get_session_stats(session_id: str) -> Dict:
    """Obté les estadístiques d'una sessió."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Stats generals
    cursor.execute("""
        SELECT total_cost_usd, presentations_generated, created_at
        FROM sessions WHERE id = ?
    """, (session_id,))
    session = cursor.fetchone()

    if not session:
        conn.close()
        return {"exists": False}

    # Detall per model
    cursor.execute("""
        SELECT model,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(images_generated) as total_images,
               SUM(cost_usd) as total_cost
        FROM usage WHERE session_id = ?
        GROUP BY model
    """, (session_id,))
    by_model = cursor.fetchall()

    conn.close()

    return {
        "exists": True,
        "total_cost_usd": session[0],
        "presentations_generated": session[1],
        "created_at": session[2],
        "by_model": [
            {
                "model": row[0],
                "input_tokens": row[1],
                "output_tokens": row[2],
                "images_generated": row[3],
                "cost_usd": row[4]
            }
            for row in by_model
        ]
    }


def get_global_stats() -> Dict:
    """Obté estadístiques globals del sistema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Total global
    cursor.execute("""
        SELECT
            COUNT(DISTINCT session_id) as total_sessions,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(images_generated) as total_images,
            SUM(cost_usd) as total_cost
        FROM usage
    """)
    total = cursor.fetchone()

    # Per model
    cursor.execute("""
        SELECT model,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(images_generated) as total_images,
               SUM(cost_usd) as total_cost,
               COUNT(*) as calls
        FROM usage
        GROUP BY model
        ORDER BY total_cost DESC
    """)
    by_model = cursor.fetchall()

    # Últimes 10 operacions
    cursor.execute("""
        SELECT model, operation, chapter_name, input_tokens, output_tokens,
               images_generated, cost_usd, created_at
        FROM usage
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent = cursor.fetchall()

    # Presentacions totals
    cursor.execute("SELECT SUM(presentations_generated) FROM sessions")
    total_presentations = cursor.fetchone()[0] or 0

    conn.close()

    return {
        "total_sessions": total[0] or 0,
        "total_input_tokens": total[1] or 0,
        "total_output_tokens": total[2] or 0,
        "total_images_generated": total[3] or 0,
        "total_cost_usd": total[4] or 0,
        "total_presentations": total_presentations,
        "by_model": [
            {
                "model": row[0],
                "input_tokens": row[1],
                "output_tokens": row[2],
                "images_generated": row[3],
                "cost_usd": row[4],
                "api_calls": row[5]
            }
            for row in by_model
        ],
        "recent_operations": [
            {
                "model": row[0],
                "operation": row[1],
                "chapter_name": row[2],
                "input_tokens": row[3],
                "output_tokens": row[4],
                "images_generated": row[5],
                "cost_usd": row[6],
                "created_at": row[7]
            }
            for row in recent
        ]
    }


def register_user(name: str, email: str = None) -> int:
    """Registra o actualitza un usuari."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (name, email)
        VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET
        email = COALESCE(?, email)
    """, (name, email, email))

    cursor.execute("SELECT id FROM users WHERE name = ?", (name,))
    user_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()
    return user_id


def create_session_with_user(session_id: str, user_name: str):
    """Crea una sessió associada a un usuari."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO sessions (id, user_name, total_cost_usd, presentations_generated)
        VALUES (?, ?, 0, 0)
    """, (session_id, user_name))

    conn.commit()
    conn.close()


def update_user_stats(user_name: str, cost: float, presentations: int = 0):
    """Actualitza les estadístiques d'un usuari."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users SET
        total_cost_usd = total_cost_usd + ?,
        presentations_generated = presentations_generated + ?
        WHERE name = ?
    """, (cost, presentations, user_name))

    conn.commit()
    conn.close()


def get_user_stats(user_name: str) -> Dict:
    """Obté les estadístiques d'un usuari."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, email, created_at, total_cost_usd, presentations_generated
        FROM users WHERE name = ?
    """, (user_name,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return {"exists": False}

    # Historial de sessions
    cursor.execute("""
        SELECT id, created_at, total_cost_usd, presentations_generated
        FROM sessions WHERE user_name = ?
        ORDER BY created_at DESC LIMIT 10
    """, (user_name,))
    sessions = cursor.fetchall()

    conn.close()

    return {
        "exists": True,
        "name": user[0],
        "email": user[1],
        "created_at": user[2],
        "total_cost_usd": user[3],
        "presentations_generated": user[4],
        "recent_sessions": [
            {
                "id": s[0],
                "created_at": s[1],
                "cost_usd": s[2],
                "presentations": s[3]
            }
            for s in sessions
        ]
    }


def get_all_users_stats() -> List[Dict]:
    """Obté estadístiques de tots els usuaris."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, total_cost_usd, presentations_generated, created_at
        FROM users
        ORDER BY total_cost_usd DESC
    """)
    users = cursor.fetchall()
    conn.close()

    return [
        {
            "name": u[0],
            "total_cost_usd": u[1],
            "presentations_generated": u[2],
            "created_at": u[3]
        }
        for u in users
    ]


# ============================================================================
# FUNCIONS PER GESTIÓ DE PRESENTACIONS
# ============================================================================

def save_presentation(
    task_id: str,
    user_name: str,
    chapter_name: str,
    group_name: str,
    slides_count: int,
    cost_usd: float,
    pptx_path: str
):
    """Guarda una presentació generada."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO presentations
        (task_id, user_name, chapter_name, group_name, slides_count, cost_usd, pptx_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (task_id, user_name, chapter_name, group_name, slides_count, cost_usd, pptx_path))

    conn.commit()
    conn.close()


def get_user_presentations(user_name: str) -> List[Dict]:
    """Obté totes les presentacions d'un usuari."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT task_id, chapter_name, group_name, slides_count, cost_usd, pptx_path, created_at
        FROM presentations
        WHERE user_name = ? AND deleted = 0
        ORDER BY created_at DESC
    """, (user_name,))
    presentations = cursor.fetchall()
    conn.close()

    return [
        {
            "task_id": p[0],
            "chapter_name": p[1],
            "group_name": p[2],
            "slides_count": p[3],
            "cost_usd": p[4],
            "pptx_path": p[5],
            "created_at": p[6]
        }
        for p in presentations
    ]


def get_all_presentations() -> List[Dict]:
    """Obté totes les presentacions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT task_id, user_name, chapter_name, group_name, slides_count, cost_usd, pptx_path, created_at
        FROM presentations
        WHERE deleted = 0
        ORDER BY created_at DESC
    """)
    presentations = cursor.fetchall()
    conn.close()

    return [
        {
            "task_id": p[0],
            "user_name": p[1],
            "chapter_name": p[2],
            "group_name": p[3],
            "slides_count": p[4],
            "cost_usd": p[5],
            "pptx_path": p[6],
            "created_at": p[7]
        }
        for p in presentations
    ]


def delete_presentation(task_id: str) -> bool:
    """Marca una presentació com a eliminada."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE presentations SET deleted = 1 WHERE task_id = ?
    """, (task_id,))

    affected = cursor.rowcount
    conn.commit()
    conn.close()

    return affected > 0


def get_presentation_path(task_id: str) -> Optional[str]:
    """Obté el path d'una presentació pel task_id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pptx_path FROM presentations WHERE task_id = ? AND deleted = 0
    """, (task_id,))
    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None


# Inicialitzar BD al importar
init_db()
