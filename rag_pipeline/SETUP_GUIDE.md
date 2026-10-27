# CyberAware Cameroon — setup guide

## 1. Install (once)
```
cd rag_pipeline
python -m venv .venv
.venv\Scripts\activate            (Windows PowerShell may need: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force)
pip install -r requirements.txt
```

## 2. Settings: the `.env` file (never commit it, never share it)
```
GROQ_API_KEY=...            your Groq key (the chatbot's language model)
TOKEN_SECRET=...            long random text; signs subscription tokens
ACCESS_CODES=CYB-XXXX-XXXX,CYB-YYYY-YYYY       codes you sell (comma separated)
ADMIN_ACCESS_CODE=...       your own demo code: unlocks everything for 7 days
PAYMENT_NUMBER=+237 6XX XXX XXX                 MoMo / Orange Money number shown to customers
```
`python make_codes.py 20` prints new random codes and a new `TOKEN_SECRET`.

## 3. Build the search index (whenever knowledge_base/ changes)
```
python ingest.py
```
It validates every knowledge-base file (it stops with a clear message if one is incomplete)
and rebuilds the index from scratch.

## 4. Run
```
uvicorn app:app --reload
```
Open http://127.0.0.1:8000 (not 0.0.0.0).  Interactive API list: http://127.0.0.1:8000/docs

## 5. Check everything
```
python -m unittest discover -s tests -t .      all automated tests (about 135)
python evaluate.py                             retrieval quality on evaluation/benchmark.csv
python check_deployment.py http://127.0.0.1:8000     health + security check of a running site
python check_deployment.py https://YOUR-APP.onrender.com
```

## 6. Where things are
| File | Job |
|---|---|
| `app.py` | the web server: the 8 routes of Table 4.9, safety headers, rate limits |
| `rag.py` | the chatbot brain: search, prompt, model call, fallback, degraded answer |
| `embedder.py` | turns text into numbers (TF-IDF) |
| `ingest.py` | reads `knowledge_base/` and fills the search index |
| `language.py` | guesses English / French / Pidgin when the visitor has not chosen |
| `access.py` | codes, signed tokens, certificate reference |
| `lessons.py` + `lessons.json` | the 10 lessons, kept on the server and marked there |
| `ratelimit.py` | stops one visitor from sending too many requests |
| `config.py` | all settings in one place |
| `templates/index.html` | the whole front end (one file) |
| `evaluate.py`, `evaluation/` | measures retrieval quality |
| `tests/` | automated tests |

## Honest limits (say these yourself before the examiners do)
* The knowledge base has English and French passages only. Pidgin questions search the
  English passages and the model writes the answer in Pidgin.
* Search is lexical (TF-IDF): a question must share words with the passages. Questions that
  share only one common word can slip through the similarity threshold; the model's rules
  then make it say it does not know.
* Subscription codes are checked on the server, but they are reusable until you change the
  list; a database would be needed for one-time codes.
* Payment is by code after Mobile Money transfer; there is no automatic payment verification.
