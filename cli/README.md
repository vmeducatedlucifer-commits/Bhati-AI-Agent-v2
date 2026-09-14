# bhati CLI

Terminal client for Bhati AI Agent v2.

```bash
pip install httpx
chmod +x cli/bhati.py
sudo ln -s "$PWD/cli/bhati.py" /usr/local/bin/bhati   # optional

export BHATI_API=http://localhost:8000

bhati "summarise this repo and list the risky parts"
bhati --auto "clone X, fix failing tests, open a PR"
bhati --profile operator "open chrome and download my invoices"
bhati                     # interactive REPL
```

REPL commands: `/auto`, `/chat`, `/profile <name>`, `/session`, `/exit`.
