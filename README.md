# Maestro-OS
# Apex Console

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Deployed-FF4B4B.svg)](https://streamlit.io/)
[![Groq](https://img.shields.io/badge/Groq-API-F55036.svg)](https://groq.com/)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM-76B900.svg)](https://build.nvidia.com/)

One Streamlit app, two independent agent swarms, switchable per message:

- **🧠 General (Apex OS)** — open-ended research / strategy / app-building swarm (`apex_engine.py`)
- **🕵️ Market Intelligence (DealScout)** — B2B market & competitor intelligence swarm that outputs a structured dashboard (`dealscout_engine.py`)

The two engines are fully decoupled on purpose — `app.py` is just a shell that picks which one to call. Editing one never touches the other.

<!-- TODO: Add a screenshot of the Streamlit app here -->
<!-- ![Maestro-OS](docs/screenshot.png) -->

## Repo structure

```
.
├─ app.py                      # unified UI shell -- entry point for Streamlit
├─ apex_engine.py              # Apex OS swarm (independent)
├─ dealscout_engine.py         # DealScout swarm (independent)
├─ requirements.txt
├─ .gitignore
└─ .streamlit/
    └─ secrets.toml.example          # copy to secrets.toml locally, fill in real keys
```

## Prerequisites

You need API keys from both providers, since Short Context routes to Groq and Long Context routes to NVIDIA NIM, for **both** engines:

- **Groq**: console.groq.com → API Keys
- **NVIDIA NIM**: build.nvidia.com → get an API key (free tier available)

## Run locally

```bash
git clone <this-repo-url>
cd <this-repo>
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and paste in your real keys

streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (`secrets.toml` won't be included — it's gitignored, which is correct).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Pick this repo, the branch, and set the main file path to `app.py`.
4. Open **Advanced settings** and pick a Python version (3.12 works fine). \
   Don't rely on a `runtime.txt` file for this — as of mid-2026 there are open reports of Community Cloud ignoring it and using its own default regardless. The dropdown in Advanced settings is the only reliable way to set it right now.
5. In the **Secrets** field, paste the same flat content as `secrets.toml.example`, with real values:
   ```toml
   GROQ_API_KEY = "gsk_..."
   NVIDIA_API_KEY = "nvapi-..."
   ```
   Keep these at the root level with no `[section]` header — Streamlit only mirrors root-level secrets into `os.environ`, which is how both engines file read them.
6. Deploy. First build can take a few minutes; code changes after that redeploy automatically on push.

## Notes

- There's no login system and no payment/usage-purchase flow by design — usage is limited to 3 Long Context + 4 Short Context requests per 4-hour window, shared across both engines, tracked in Streamlit's session state. This resets if a visitor's session ends (closing the tab, etc.) — it's a soft anti-abuse measure, not a hard per-user limit. A real per-user cap would need a backend (e.g. a database keyed by an account or device ID), which isn't included here.
- If you see `packages.txt` mentioned in Streamlit's docs elsewhere — you don't need one here. That file is only for non-Python system packages (apt-get), and nothing in this app needs any.

## License

MIT — see [LICENSE](LICENSE).