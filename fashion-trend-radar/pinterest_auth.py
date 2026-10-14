"""
One-time Pinterest API v5 authorisation via the official quickstart
(C:\\Users\\User\\Documents\\GitHub\\api-quickstart). Reads PINTEREST_APP_ID /
PINTEREST_APP_SECRET from .env, opens the Pinterest "Allow" page in the
browser (the user clicks Allow -- no password passes through here) and saves
the token to data/secrets/ (git-ignored).
Redirect URI in the app settings must be exactly: http://localhost:8085/
Usage: .venv/Scripts/python.exe pinterest_auth.py
"""
import os
import runpy
import sys
from pathlib import Path

QUICKSTART = Path(r"C:\Users\User\Documents\GitHub\api-quickstart\python")
TOKEN_DIR = Path("data/secrets").resolve()
SCOPES = "user_accounts:read,ads:read"   # trends + related/suggested terms


def load_env():
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(("PINTEREST_APP_ID=", "PINTEREST_APP_SECRET=")):
            k, v = line.split("=", 1)
            os.environ[k] = v.strip()
    missing = [k for k in ("PINTEREST_APP_ID", "PINTEREST_APP_SECRET") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Нет в .env: {', '.join(missing)}")


def main():
    load_env()
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["PINTEREST_OAUTH_TOKEN_DIR"] = str(TOKEN_DIR)
    sys.path.insert(0, str(QUICKSTART / "src"))
    sys.argv = ["get_access_token.py", "-s", SCOPES, "-w"]   # -w: write token to file
    runpy.run_path(str(QUICKSTART / "scripts" / "get_access_token.py"), run_name="__main__")


if __name__ == "__main__":
    main()
