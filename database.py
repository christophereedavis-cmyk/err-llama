import sqlite3
import os

# The database lives in the same folder as app.py
DB_PATH = os.path.join(os.path.dirname(__file__), 'errllama.db')


def get_db():
    """Open a database connection. row_factory lets us access columns by name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist yet. Safe to call every startup."""
    conn = get_db()
    c = conn.cursor()

    # One row per registered user
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # One row per conversation (belongs to a user)
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            title      TEXT NOT NULL DEFAULT 'New conversation',
            model      TEXT NOT NULL DEFAULT 'llama3.1:8b',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # One row per message (belongs to a conversation)
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    ''')

    conn.commit()
    conn.close()


# ── User helpers ──────────────────────────────────────────────

def create_user(username, password_hash):
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            (username, password_hash)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # username already taken
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    conn.close()
    return user


# ── Conversation helpers ──────────────────────────────────────

def create_conversation(user_id, title, model):
    conn = get_db()
    cursor = conn.execute(
        'INSERT INTO conversations (user_id, title, model) VALUES (?, ?, ?)',
        (user_id, title, model)
    )
    conv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return conv_id


def get_conversations(user_id):
    """Return all conversations for a user, newest first."""
    conn = get_db()
    rows = conn.execute(
        '''SELECT * FROM conversations
           WHERE user_id = ?
           ORDER BY updated_at DESC''',
        (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_conversation(conv_id, user_id):
    """Get one conversation — user_id check prevents accessing others' chats."""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM conversations WHERE id = ? AND user_id = ?',
        (conv_id, user_id)
    ).fetchone()
    conn.close()
    return row


def touch_conversation(conv_id):
    """Update the updated_at timestamp when a new message arrives."""
    conn = get_db()
    conn.execute(
        'UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (conv_id,)
    )
    conn.commit()
    conn.close()


def delete_conversation(conv_id, user_id):
    conn = get_db()
    conn.execute(
        'DELETE FROM messages WHERE conversation_id = ?', (conv_id,)
    )
    conn.execute(
        'DELETE FROM conversations WHERE id = ? AND user_id = ?',
        (conv_id, user_id)
    )
    conn.commit()
    conn.close()


# ── Message helpers ───────────────────────────────────────────

def save_message(conv_id, role, content):
    conn = get_db()
    conn.execute(
        'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conv_id, role, content)
    )
    conn.commit()
    conn.close()


def get_messages(conv_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id',
        (conv_id,)
    ).fetchall()
    conn.close()
    return [{'role': r['role'], 'content': r['content']} for r in rows]
