"""
Trading Journal 3.0 — Unified Pipeline Runner
Ausfuehrung: python run_pipeline.py [--users U] [--envs E] [--steps S] [--dry-run]
Konfiguration: pipeline.toml
"""

import argparse
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path


VALID_STEPS = ["fetch_emails", "import", "process", "summary"]

# Module-Notation (-m) statt Dateipfad: Projektwurzel bleibt in sys.path,
# dadurch funktionieren "from src.xyz import ..." Importe in den Scripts korrekt.
STEP_SCRIPTS = {
    "fetch_emails": "src.get_flexquery_emails",
    "import":       "src.import_ibkr_trades",
    "process":      "src.process_ibkr_trades",
    "summary":      "src.xml_append_summary",
}


def load_config(config_path: Path) -> dict:
    """Laedt pipeline.toml und gibt das Config-Dict zurueck."""
    if not config_path.exists():
        print(f"FEHLER: Konfigurationsdatei nicht gefunden: {config_path}")
        sys.exit(1)
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def build_task_list(config: dict, filter_users: list[str], filter_envs: list[str],
                    filter_steps: list[str]) -> list[dict]:
    """
    Erstellt die geordnete Liste aller auszufuehrenden Tasks.
    Jeder Task ist ein Dict mit: step, user (optional), env (optional), args.
    """
    steps_to_run = [s for s in config["settings"]["steps"] if s in filter_steps]
    users_cfg = config.get("users", {})

    # Aktive User filtern
    active_users = {
        name: cfg for name, cfg in users_cfg.items()
        if not filter_users or name in filter_users
    }

    tasks = []

    for step in steps_to_run:
        if step == "fetch_emails":
            # Laeuft einmal, keine User/Env-Parameter
            tasks.append({"step": step, "label": "fetch_emails", "args": []})

        elif step in ("import", "process"):
            # Pro User x Env
            for user, ucfg in active_users.items():
                envs = [e for e in ucfg["environments"] if not filter_envs or e in filter_envs]
                for env in envs:
                    tasks.append({
                        "step": step,
                        "label": f"{step} [{user} / {env}]",
                        "args": [env, ucfg["prefix"]],
                    })

        elif step == "summary":
            # Pro eindeutigem Env (ueber alle aktiven User)
            seen_envs: set[str] = set()
            for ucfg in active_users.values():
                for env in ucfg["environments"]:
                    if (not filter_envs or env in filter_envs) and env not in seen_envs:
                        seen_envs.add(env)
                        tasks.append({
                            "step": step,
                            "label": f"summary [{env}]",
                            "args": [env],
                        })

    return tasks


def run_task(task: dict, dry_run: bool) -> bool:
    """Fuehrt einen einzelnen Task aus. Gibt True bei Erfolg zurueck."""
    script = STEP_SCRIPTS[task["step"]]
    cmd = [sys.executable, "-m", script] + task["args"]
    label = task["label"]

    start = datetime.now()
    print(f"\n{'='*60}")
    print(f"  START  {label}")
    display_cmd = ["python", "-m", script] + task["args"]
    print(f"  Befehl: {' '.join(display_cmd)}")
    print(f"  Zeit:   {start.strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    if dry_run:
        print("  [DRY-RUN] uebersprungen")
        return True

    try:
        subprocess.run(cmd, check=True)
        dauer = (datetime.now() - start).seconds
        print(f"\n  OK  {label}  ({dauer}s)")
        return True
    except subprocess.CalledProcessError as e:
        dauer = (datetime.now() - start).seconds
        print(f"\n  FEHLER  {label}  (Exit-Code {e.returncode}, {dauer}s)")
        return False


def print_summary(results: list[tuple[str, bool]]) -> None:
    """Gibt eine Zusammenfassung aller ausgefuehrten Tasks aus."""
    print(f"\n{'='*60}")
    print("  PIPELINE-ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    ok = sum(1 for _, success in results if success)
    for label, success in results:
        status = "OK    " if success else "FEHLER"
        print(f"  {status}  {label}")
    print(f"{'='*60}")
    print(f"  {ok}/{len(results)} Steps erfolgreich\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trading Journal 3.0 — Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python run_pipeline.py                              # alles ausfuehren
  python run_pipeline.py --users mike                 # nur mike
  python run_pipeline.py --envs money                 # alle User, nur money
  python run_pipeline.py --steps import process       # nur Import + Verarbeitung
  python run_pipeline.py --dry-run                    # zeige Steps ohne Ausfuehrung
        """,
    )
    parser.add_argument("--users", nargs="+", metavar="USER",
                        help="Nur diese User verarbeiten (z.B. mike karola)")
    parser.add_argument("--envs", nargs="+", metavar="ENV",
                        help="Nur diese Environments (z.B. money paper)")
    parser.add_argument("--steps", nargs="+", metavar="STEP",
                        choices=VALID_STEPS,
                        help=f"Nur diese Steps: {' | '.join(VALID_STEPS)}")
    parser.add_argument("--dry-run", action="store_true",
                        help="Steps anzeigen ohne auszufuehren")
    parser.add_argument("--config", default="pipeline.toml", metavar="FILE",
                        help="Pfad zur TOML-Konfiguration (Standard: pipeline.toml)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))

    filter_steps = args.steps if args.steps else config["settings"]["steps"]
    filter_users = args.users or []
    filter_envs = args.envs or []

    tasks = build_task_list(config, filter_users, filter_envs, filter_steps)

    if not tasks:
        print("Keine Tasks gefunden — Filter pruefen (--users, --envs, --steps).")
        sys.exit(0)

    modus = "[DRY-RUN]" if args.dry_run else ""
    print(f"\nTrading Journal 3.0 — Pipeline {modus}")
    print(f"Konfiguration: {args.config}")
    print(f"Tasks: {len(tasks)}")

    results: list[tuple[str, bool]] = []
    for task in tasks:
        success = run_task(task, dry_run=args.dry_run)
        results.append((task["label"], success))
        if not success and not args.dry_run:
            print("\nABBRUCH: Fehler im Step. Nachfolgende Steps werden nicht ausgefuehrt.")
            # Verbleibende Tasks als nicht ausgefuehrt markieren
            remaining = tasks[len(results):]
            for t in remaining:
                results.append((t["label"], False))
            break

    print_summary(results)

    # Exit-Code 1 wenn mindestens ein Step fehlgeschlagen
    if not all(s for _, s in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
