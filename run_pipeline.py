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


VALID_STEPS = ["fetch_emails", "fetch_api", "snapshot_csv", "snapshot_import", "import", "process", "summary", "reset"]

# Module-Notation (-m) statt Dateipfad: Projektwurzel bleibt in sys.path,
# dadurch funktionieren "from src.xyz import ..." Importe in den Scripts korrekt.
STEP_SCRIPTS = {
    "fetch_emails":    "src.get_flexquery_emails",
    "fetch_api":       "src.get_flexquery_api",
    "snapshot_csv":    "src.import_csv_snapshots",
    "snapshot_import": "src.import_flexquery_snapshot",
    "import":          "src.import_ibkr_trades",
    "process":         "src.process_ibkr_trades",
    "summary":         "src.xml_append_summary",
    "reset":           "src.reset_IBKR_DB",
}


def load_config(config_path: Path) -> dict:
    """Laedt pipeline.toml und gibt das Config-Dict zurueck."""
    if not config_path.exists():
        print(f"FEHLER: Konfigurationsdatei nicht gefunden: {config_path}")
        sys.exit(1)
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def build_task_list(config: dict, filter_users: list[str], filter_envs: list[str],
                    filter_steps: list[str], from_summary: bool = False) -> list[dict]:
    """
    Erstellt die geordnete Liste aller auszufuehrenden Tasks.
    Jeder Task ist ein Dict mit: step, user (optional), env (optional), args.
    """
    # filter_steps kommt entweder aus --steps (CLI) oder aus pipeline.toml.
    # Nicht nochmals gegen die TOML-Liste filtern — sonst fallen explizit
    # uebergebene Steps wie "reset" heraus, die bewusst nicht in den Default-Steps stehen.
    steps_to_run = filter_steps
    users_cfg = config.get("users", {})

    # Aktive User filtern
    active_users = {
        name: cfg for name, cfg in users_cfg.items()
        if not filter_users or name in filter_users
    }

    tasks = []

    for step in steps_to_run:
        if step in ("fetch_emails", "fetch_api", "snapshot_csv", "snapshot_import", "process", "summary"):
            # Laufen einmal ohne Args — Scripts iterieren intern ueber pipeline.toml
            tasks.append({"step": step, "label": step, "args": []})

        elif step == "import":
            # Pro User x Env (import bleibt pro-User, wegen from_summary-Modus)
            for user, ucfg in active_users.items():
                envs = [e for e in ucfg["environments"] if not filter_envs or e in filter_envs]
                for env in envs:
                    args = [env, ucfg["prefix"]]
                    if from_summary:
                        args.append("from_summary")
                    label_suffix = " [from_summary]" if from_summary else ""
                    tasks.append({
                        "step": step,
                        "label": f"import{label_suffix} [{user} / {env}]",
                        "args": args,
                    })

        elif step == "reset":
            # Pro User x Env — Prefix wird mitgegeben (DESTRUKTIV: loescht und legt Tabellen neu an)
            for user, ucfg in active_users.items():
                envs = [e for e in ucfg["environments"] if not filter_envs or e in filter_envs]
                for env in envs:
                    tasks.append({
                        "step": step,
                        "label": f"reset [{user} / {env}]",
                        "args": [env, ucfg["prefix"]],
                        "destructive": True,
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
  python run_pipeline.py                              # alles ausfuehren (ohne reset)
  python run_pipeline.py --users mike                 # nur mike
  python run_pipeline.py --envs money                 # alle User, nur money
  python run_pipeline.py --steps import process       # nur Import + Verarbeitung
  python run_pipeline.py --steps summary              # Summaries fuer alle Envs
  python run_pipeline.py --steps reset --users mike   # DB-Reset fuer alle Envs von mike
  python run_pipeline.py --steps reset --force        # DB-Reset ohne Rueckfrage
  python run_pipeline.py --steps import --from-summary              # Import aus summary.xml
  python run_pipeline.py --users mike --from-summary                # nur mike, aus summary.xml
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
    parser.add_argument("--from-summary", action="store_true",
                        help="Import aus summary.xml statt einzelner XML-Dateien (nur fuer 'import'-Step)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Steps anzeigen ohne auszufuehren")
    parser.add_argument("--force", action="store_true",
                        help="Sicherheitsabfrage bei 'reset' ueberspringen")
    parser.add_argument("--config", default="pipeline.toml", metavar="FILE",
                        help="Pfad zur TOML-Konfiguration (Standard: pipeline.toml)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))

    filter_steps = args.steps if args.steps else config["settings"]["steps"]
    filter_users = args.users or []
    filter_envs = args.envs or []

    tasks = build_task_list(config, filter_users, filter_envs, filter_steps,
                            from_summary=args.from_summary)

    if not tasks:
        print("Keine Tasks gefunden — Filter pruefen (--users, --envs, --steps).")
        sys.exit(0)

    modus = "[DRY-RUN]" if args.dry_run else ""
    print(f"\nTrading Journal 3.0 — Pipeline {modus}")
    print(f"Konfiguration: {args.config}")
    print(f"Tasks: {len(tasks)}")

    # Sicherheitsabfrage bei destruktiven Steps (reset)
    destructive_tasks = [t for t in tasks if t.get("destructive")]
    if destructive_tasks and not args.dry_run and not args.force:
        print(f"\n  WARNUNG: {len(destructive_tasks)} destruktiver Step(s) enthalten:")
        for t in destructive_tasks:
            print(f"    - {t['label']}")
        print("\n  Alle Tabellen werden GELOESCHT und neu erstellt (Datenverlust!).")
        antwort = input("  Fortfahren? [ja/NEIN]: ").strip().lower()
        if antwort != "ja":
            print("  Abgebrochen.")
            sys.exit(0)

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
