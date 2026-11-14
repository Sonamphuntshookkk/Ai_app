# AgriAdvisor

AI-powered agriculture advisory agent (DAT404 Assignment D) for paddy, maize, potato and apple.
Plans tool use (weather, knowledge retrieval, symptom diagnosis, fertiliser calculator), remembers the farm during a session, applies safety guardrails, and adapts when answers are rated poorly.

## Run locally
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy (Streamlit Community Cloud)
Main file: `streamlit_app.py`. Optional secret: `GEMINI_API_KEY` to enable the LLM (rule-based fallback otherwise).

## Notes
The knowledge base and fertiliser rates are sample data. Advice is general guidance: confirm with a local extension officer.
