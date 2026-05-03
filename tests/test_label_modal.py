"""pytest-qt tests for the LabelModal dialog."""

import pytest
from datetime import datetime, timezone

from models.database import open_db
from models.storage import Drive
from views.dashboard_view import LabelModal, _LABEL_PALETTE


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@pytest.fixture
def drive():
    return Drive(
        name="Test Drive",
        device="/dev/sda",
        mount_point="/",
        total_bytes=500_000_000_000,
        used_bytes=100_000_000_000,
        free_bytes=400_000_000_000,
        fs_type="ext4",
        device_id="ata-Test_Drive_XYZ",
    )


# ---------------------------------------------------------------------------
# Opens with current values
# ---------------------------------------------------------------------------

def test_modal_opens_empty_when_no_label(qtbot, drive):
    modal = LabelModal(drive)
    qtbot.addWidget(modal)
    assert modal._label_edit.text() == ""


def test_modal_opens_with_existing_label(qtbot, drive):
    drive.label = "Work Stuff"
    drive.color_hex = "#3498db"
    modal = LabelModal(drive)
    qtbot.addWidget(modal)
    assert modal._label_edit.text() == "Work Stuff"
    assert modal._selected_color == "#3498db"


def test_modal_defaults_to_first_palette_color_when_no_color(qtbot, drive):
    modal = LabelModal(drive)
    qtbot.addWidget(modal)
    assert modal._selected_color == _LABEL_PALETTE[0]


def test_modal_title_contains_drive_name(qtbot, drive):
    modal = LabelModal(drive)
    qtbot.addWidget(modal)
    assert drive.name in modal.windowTitle()


# ---------------------------------------------------------------------------
# Save persists to DB
# ---------------------------------------------------------------------------

def test_save_inserts_label_into_db(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)

    modal._label_edit.setText("My SSD")
    modal._selected_color = "#2ecc71"
    modal._save()

    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = ?",
            (drive.device_id,),
        ).fetchone()
    assert row is not None
    assert row["label"] == "My SSD"
    assert row["color_hex"] == "#2ecc71"


def test_save_updates_drive_object_in_memory(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)

    modal._label_edit.setText("Backup")
    modal._selected_color = "#e74c3c"
    modal._save()

    assert drive.label == "Backup"
    assert drive.color_hex == "#e74c3c"


def test_save_replaces_existing_label(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            (drive.device_id, "Old", "#e67e22", _now()),
        )
    drive.label = "Old"
    drive.color_hex = "#e67e22"

    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)
    modal._label_edit.setText("New")
    modal._selected_color = "#9b59b6"
    modal._save()

    with open_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = ?",
            (drive.device_id,),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["label"] == "New"


# ---------------------------------------------------------------------------
# Cancel discards changes
# ---------------------------------------------------------------------------

def test_cancel_does_not_modify_drive(qtbot, drive):
    drive.label = "Keep this"
    drive.color_hex = "#1abc9c"
    modal = LabelModal(drive)
    qtbot.addWidget(modal)

    modal._label_edit.setText("Changed")
    modal.reject()

    assert drive.label == "Keep this"
    assert drive.color_hex == "#1abc9c"


def test_cancel_does_not_write_to_db(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)

    modal._label_edit.setText("Should not save")
    modal.reject()

    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = ?",
            (drive.device_id,),
        ).fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# Empty label deletes row
# ---------------------------------------------------------------------------

def test_empty_label_deletes_db_row(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            (drive.device_id, "Removable", "#e74c3c", _now()),
        )
    drive.label = "Removable"
    drive.color_hex = "#e74c3c"

    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)
    modal._label_edit.setText("")
    modal._save()

    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = ?",
            (drive.device_id,),
        ).fetchone()
    assert row is None


def test_empty_label_clears_drive_fields(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    drive.label = "HasLabel"
    drive.color_hex = "#3498db"

    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)
    modal._label_edit.setText("")
    modal._save()

    assert drive.label is None
    assert drive.color_hex is None


def test_whitespace_only_label_treated_as_empty(qtbot, drive, tmp_path):
    db_path = tmp_path / "data.db"
    with open_db(db_path) as conn:
        conn.execute(
            "INSERT INTO drive_labels VALUES (?, ?, ?, ?)",
            (drive.device_id, "Existing", "#607d8b", _now()),
        )
    drive.label = "Existing"

    modal = LabelModal(drive, db_path=db_path)
    qtbot.addWidget(modal)
    modal._label_edit.setText("   ")
    modal._save()

    with open_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM drive_labels WHERE device_id = ?",
            (drive.device_id,),
        ).fetchone()
    assert row is None
