from tawn.domains.wealth.schedule import SERVICE, TIMER, UNIT_NAME, write_units


def test_write_units_creates_service_and_timer(tmp_path):
    files = write_units("/usr/local/bin/tawn", "daily", unit_dir=tmp_path)
    names = {f.name for f in files}
    assert names == {f"{UNIT_NAME}.service", f"{UNIT_NAME}.timer"}
    service = (tmp_path / f"{UNIT_NAME}.service").read_text()
    timer = (tmp_path / f"{UNIT_NAME}.timer").read_text()
    assert "/usr/local/bin/tawn wealth snapshot" in service
    assert "OnCalendar=daily" in timer
    assert "Persistent=true" in timer


def test_units_are_templates_with_no_leftover_braces(tmp_path):
    write_units("/x/tawn", "hourly", unit_dir=tmp_path)
    for f in tmp_path.iterdir():
        assert "{" not in f.read_text()


def test_service_template_is_oneshot():
    assert "Type=oneshot" in SERVICE
    assert "WantedBy=timers.target" in TIMER
