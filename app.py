from flask import (Flask, render_template, request, Response,
                   stream_with_context, redirect, url_for, flash, session)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests
import json
import database as db
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = 'errllama-change-this-to-something-random-in-production'
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://"
)
OLLAMA_URL       = 'http://localhost:11434/api/chat'
AVAILABLE_MODELS = ['llama3.1:8b', 'llama3.1:70b']
DEFAULT_MODEL    = 'llama3.1:8b'

SYSTEM_PROMPT = {
    "role": "system",
    "content": "You are Errllama, a helpful and thoughtful local AI assistant. Be concise, direct, and genuinely useful."
}

db.init_db()
db.init_contact_table()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        if len(username) < 3:
            flash('Username must be at least 3 characters.')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.')
            return render_template('register.html')
        success = db.create_user(username, generate_password_hash(password))
        if not success:
            flash('That username is already taken.')
            return render_template('register.html')
        user = db.get_user_by_username(username)
        session['user_id']  = user['id']
        session['username'] = user['username']
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")

def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        user     = db.get_user_by_username(username)
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid username or password.')
            return render_template('login.html')
        session['user_id']  = user['id']
        session['username'] = user['username']
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    conversations = db.get_conversations(session['user_id'])
    return render_template('index.html',
                           conversations=conversations,
                           models=AVAILABLE_MODELS,
                           default_model=DEFAULT_MODEL,
                           username=session['username'])


@app.route('/conversation/new', methods=['POST'])
@login_required
def new_conversation():
    data    = request.get_json()
    model   = data.get('model', DEFAULT_MODEL)
    conv_id = db.create_conversation(session['user_id'], 'New conversation', model)
    return {'id': conv_id}


@app.route('/conversation/<int:conv_id>')
@login_required
def load_conversation(conv_id):
    conv = db.get_conversation(conv_id, session['user_id'])
    if not conv:
        return {'error': 'Not found'}, 404
    return {'id': conv['id'], 'title': conv['title'],
            'model': conv['model'], 'messages': db.get_messages(conv_id)}


@app.route('/conversation/<int:conv_id>/delete', methods=['POST'])
@login_required
def delete_conversation(conv_id):
    db.delete_conversation(conv_id, session['user_id'])
    return {'status': 'ok'}


@app.route('/conversations')
@login_required
def list_conversations():
    convs = db.get_conversations(session['user_id'])
    return {'conversations': [
        {'id': c['id'], 'title': c['title'], 'updated_at': c['updated_at']}
        for c in convs
    ]}


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data         = request.get_json()
    user_message = data.get('message', '').strip()
    model        = data.get('model', DEFAULT_MODEL)
    conv_id      = data.get('conversation_id')

    if not user_message:
        return {'error': 'Empty message'}, 400

    if not conv_id:
        title   = user_message[:45] + ('…' if len(user_message) > 45 else '')
        conv_id = db.create_conversation(session['user_id'], title, model)
        is_new  = True
    else:
        if not db.get_conversation(conv_id, session['user_id']):
            return {'error': 'Conversation not found'}, 404
        is_new = False

    db.save_message(conv_id, 'user', user_message)
    db.touch_conversation(conv_id)

    messages = [SYSTEM_PROMPT] + db.get_messages(conv_id)

    def generate():
        yield f"data: {json.dumps({'conv_id': conv_id, 'is_new': is_new})}\n\n"
        full_response = ''
        try:
            resp = requests.post(OLLAMA_URL,
                json={'model': model, 'messages': messages, 'stream': True},
                stream=True, timeout=120)
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if 'message' in chunk:
                        token = chunk['message'].get('content', '')
                        full_response += token
                        yield f"data: {json.dumps({'token': token})}\n\n"
                    if chunk.get('done'):
                        db.save_message(conv_id, 'assistant', full_response)
                        db.touch_conversation(conv_id)
                        yield f"data: {json.dumps({'done': True, 'conv_id': conv_id})}\n\n"
        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'error': 'Cannot connect to Ollama.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')




# ── Static pages ──────────────────────────────────────────────

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        subject  = request.form.get('subject', '')
        message  = request.form.get('message', '').strip()
        if not message:
            flash('Please enter a message.', 'error')
            return render_template('contact.html')
        conn = db.get_db()
        conn.execute(
            'INSERT INTO contact_messages (username, subject, message) VALUES (?, ?, ?)',
            (username, subject, message)
        )
        conn.commit()
        conn.close()
        flash('Message received. We will follow up within 7 days.', 'success')
        return render_template('contact.html')
    return render_template('contact.html')


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5001)
