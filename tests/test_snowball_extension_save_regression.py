from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8-sig")


def _snowball_extension_save_block() -> str:
    source = _app_source()
    start = source.index("struct_sb_ext_save_")
    end = source.index("with tab_terminated:", start)
    return source[start:end]


def test_snowball_extension_save_uses_explicit_write_tx_and_clears_runtime_caches() -> None:
    block = _snowball_extension_save_block()

    assert 'conn.execute("BEGIN IMMEDIATE")' in block
    assert "conn.commit()" in block
    assert "clear_runtime_caches_after_db_write()" in block
    assert "except Exception as exc:" in block
    assert "conn.rollback()" in block
    assert "st.error(" in block
    assert "humanize_db_write_error(exc)" in block

    assert block.index("conn.commit()") < block.index("clear_runtime_caches_after_db_write()")
    assert block.index("clear_runtime_caches_after_db_write()") < block.index("st.success(")
    assert block.index("st.success(") < block.index("st.rerun()")


def test_snowball_extension_save_keeps_runtime_price_columns_in_sync() -> None:
    block = _snowball_extension_save_block()
    update_block = block[block.index("UPDATE structure") : block.index("conn.commit()")]

    assert "entry_price=?" in update_block
    assert "strike_price=?" in update_block
    assert "gen_price=?" in update_block
    assert "ko_strike_price=?" in update_block
    assert update_block.count("float(sb_entry_price_new)") >= 4


def test_snowball_create_payload_reuses_resolved_floor_flag() -> None:
    source = _app_source()
    payload_start = source.index("def _build_structure_payload")
    snowball_start = source.index('if strategy_code == "SNOWBALL":', payload_start)
    floor_end = source.index('"sb_discount_enabled"', snowball_start)
    block = source[snowball_start:floor_end]

    assert 'floor_on = bool(snowball_form.get("floor_enabled", False))' in block
    assert '"sb_floor_enabled": bool(floor_on)' in block
    assert '"sb_floor_enabled": bool(snowball_form.get("floor_enabled", True))' not in block
