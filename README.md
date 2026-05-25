# LeadFinder

Streamlit-app om bedrijven zonder eigen website te vinden via Google Maps.

## Lokaal starten

```bash
pip install -r requirements.txt
python -m playwright install chromium
streamlit run app.py --server.address 0.0.0.0
```

Open daarna:

```text
http://localhost:8501
```

## Online zetten

Deze app gebruikt Playwright/Chromium. Gebruik daarom bij voorkeur een platform dat Docker ondersteunt, zoals Render, Railway, Fly.io of een VPS.

Build/start command zit in de `Dockerfile`.
