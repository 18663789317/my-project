from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8-sig")


def _between(source: str, start: str, end: str) -> str:
    start_idx = source.index(start)
    end_idx = source.index(end, start_idx)
    return source[start_idx:end_idx]


def test_hard_delete_explicitly_removes_position_adjustments_before_structure_rows() -> None:
    source = _app_source()
    block = _between(source, "def hard_delete_structures_with_related_records", "def upsert_structure_record_payload")

    gid_delete = "DELETE FROM structure_position_adjustment WHERE group_id=? AND structure_id IN"
    gid_structure_delete = "DELETE FROM structure WHERE group_id=? AND structure_id IN"
    plain_delete = "DELETE FROM structure_position_adjustment WHERE structure_id IN"
    plain_structure_delete = "DELETE FROM structure WHERE structure_id IN"

    assert gid_delete in block
    assert plain_delete in block
    assert block.index(gid_delete) < block.index(gid_structure_delete)
    assert block.index(plain_delete) < block.index(plain_structure_delete)


def test_structure_id_migration_updates_position_adjustments_before_source_delete() -> None:
    source = _app_source()
    block = _between(
        source,
        "def migrate_structure_related_records_to_target_id",
        "def save_structure_payload_with_optional_rename",
    )

    update_sql = "UPDATE structure_position_adjustment SET structure_id=?, group_id=? WHERE structure_id=?"
    delete_sql = "DELETE FROM structure WHERE structure_id=?"

    assert update_sql in block
    assert block.index(update_sql) < block.index(delete_sql)


def test_fixed_subsidy_uses_shared_melt_trigger_strategy_set() -> None:
    source = _app_source()
    monitor_block = _between(source, "def is_monitor_melt_strategy", "def choose_monitor_barrier_or_melt_price")

    assert 'MELT_TRIGGER_PRICE_STRATEGY_CODES = {"FLOAT_KO", "FIXED_SUBSIDY", "MELT_RANGE_SUBSIDY"}' in source
    assert "melt_strategy_codes = set(MELT_TRIGGER_PRICE_STRATEGY_CODES)" in source
    assert '| {"FIXED_SUBSIDY"}' not in monitor_block


def test_single_structure_confirm_rechecks_latest_payload_before_persisting() -> None:
    source = _app_source()
    block = _between(source, "struct_save_confirm_btn_", "with cf2:")

    recheck = "will_terminate_now, hit_dt_now, hit_status_now = detect_structure_termination_on_prices"
    persist = "_persist_structure_payload(latest_payload)"

    assert recheck in block
    assert persist in block
    assert block.index(recheck) < block.index(persist)


def test_vanilla_template_import_sets_option_type_and_side_state() -> None:
    source = _app_source()
    block = _between(source, "def apply_structure_template_to_form_state", "underlying_name =")

    assert "if strategy_code == VANILLA_OPTION_CODE:" in block
    assert 'option_type = normalize_vanilla_option_type(payload.get("option_type"), "put")' in block
    assert "vanilla_option_type_cn(option_type)" in block
    assert 'side = normalize_vanilla_side(payload.get("side"), "sell")' in block
    assert "vanilla_side_cn(side)" in block
