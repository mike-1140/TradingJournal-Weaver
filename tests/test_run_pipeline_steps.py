# Tests fuer die Step-Konfiguration in run_pipeline.py — jeder Step muss auf ein
# existierendes Modul zeigen (Hintergrund: snapshot_import/import_flexquery_snapshot
# wurde 2026-10-17 entfernt; ein vergessener Eintrag wuerde erst zur Laufzeit scheitern)
import importlib.util

import pytest

from run_pipeline import STEP_SCRIPTS, VALID_STEPS


def test_valid_steps_und_step_scripts_sind_deckungsgleich():
    assert set(VALID_STEPS) == set(STEP_SCRIPTS)


@pytest.mark.parametrize("step, module", sorted(STEP_SCRIPTS.items()))
def test_jeder_step_zeigt_auf_existierendes_modul(step, module):
    # find_spec prueft nur die Existenz, fuehrt das Modul nicht aus
    assert importlib.util.find_spec(module) is not None, f"{step}: Modul {module} fehlt"


def test_entfernter_snapshot_import_step_ist_nicht_mehr_waehlbar():
    assert "snapshot_import" not in VALID_STEPS
