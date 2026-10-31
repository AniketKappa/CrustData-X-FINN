"""Deploy FINN to a Hugging Face Space (Docker) from this folder.

Needs a Hugging Face *write* token in .env as HF_TOKEN=... (huggingface.co -> Settings -> Access Tokens).
Creates the Space if it doesn't exist, uploads the code (never .env, the database or PDFs), and copies
GROQ_API_KEY / OPENROUTER_API_KEY / TAVILY_API_KEY from .env into the Space's private secrets.

    pip install huggingface_hub
    python deploy_hf.py                 # Space name: <your-username>/finn
    python deploy_hf.py --space finn-demo
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECRETS = ["GROQ_API_KEY", "OPENROUTER_API_KEY", "TAVILY_API_KEY"]
IGNORE = [".env", ".env.*", ".git/*", "**/__pycache__/*", "**/.pytest_cache/*", "data/*.db", "data/*.json", "*.zip",
          "design/prototype/shots/*", "design/prototype/archive/*", "*.pdf", ".vscode/*", "node_modules/*"]


def read_env() -> dict:
    out = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default="finn")
    a = ap.parse_args()
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("Run: pip install huggingface_hub")
        return 1
    env = read_env()
    token = env.get("HF_TOKEN")
    if not token:
        print("Add HF_TOKEN=<your write token> to .env (huggingface.co -> Settings -> Access Tokens -> New token, type Write).")
        return 1
    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo = f"{user}/{a.space}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    print(f"Uploading to https://huggingface.co/spaces/{repo} ...")
    api.upload_folder(repo_id=repo, repo_type="space", folder_path=str(ROOT), ignore_patterns=IGNORE,
                      commit_message="Deploy FINN")
    for k in SECRETS:
        if env.get(k):
            api.add_space_secret(repo, k, env[k])
            print(f"  secret set: {k}")
        else:
            print(f"  secret missing in .env: {k} (that feature will be off)")
    print(f"\nBuilding now. App URL (ready in ~3-5 min): https://{user.lower()}-{a.space.lower()}.hf.space")
    print(f"Build logs: https://huggingface.co/spaces/{repo}?logs=build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
