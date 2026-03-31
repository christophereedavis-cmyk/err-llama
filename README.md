# Errllama

Local AI chat interface powered by Ollama.

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Make sure Ollama is running with at least one model
ollama pull llama3.1:8b
ollama pull llama3.1:70b   # optional, needs ~28GB RAM

# Run the app
python app.py
```

Then open http://localhost:5001 in your browser.

## Desktop App (future)

To wrap this as a native desktop window:
```bash
pip install pywebview
```
Then swap `app.run()` for a pywebview window — see pywebview docs.

## Production (Nginx)

When deploying behind Nginx:
- Use `gunicorn` instead of Flask dev server
- Set a strong `secret_key` in app.py
- Add auth if exposing publicly
