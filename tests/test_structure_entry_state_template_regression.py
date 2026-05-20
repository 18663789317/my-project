import ast
import copy
from pathlib import Path
from typing import Any, Dict


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8-sig")


def _between(source: str, start: str, end: str) -> str:
    start_idx = source.index(start)
    end_idx = source.index(end, start_idx)
    return source[start_idx:end_idx]


def _load_scope_helpers() -> Dict[str, Any]:
    source = _app_source()
    tree = ast.parse(source, filename=str(APP_PATH))
    target_names = {
        "_structure_entry_state_scope_index",
        "_structure_entry_state_key_in_scope",
        "_replace_structure_entry_state_scope",
    }
    found = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.FunctionDef) and node.name in target_names:
            found.append(copy.deepcopy(node))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    module = ast.Module(body=found, type_ignores=[])
    ast.fix_missing_locations(module)
    env: Dict[str, Any] = {"__builtins__": __builtins__, "Any": Any}
    exec(compile(module, str(APP_PATH), "exec"), env)
    return env


def test_structure_entry_scope_matching_checks_both_boundaries() -> None:
    ns = _load_scope_helpers()
    in_scope = ns["_structure_entry_state_key_in_scope"]

    assert in_scope("struct_code_G001__col1", "G001__col1")
    assert in_scope("struct_code_G001__col1__pending", "G001__col1")
    assert not in_scope("struct_code_AG001__col1", "G001__col1")
    assert not in_scope("struct_code_G001__col10", "G001__col1")


def test_structure_entry_scope_replace_skips_embedded_substrings() -> None:
    ns = _load_scope_helpers()
    replace_scope = ns["_replace_structure_entry_state_scope"]

    key = "mirrorXG001__col1_struct_code_G001__col1__pending"
    assert replace_scope(key, "G001__col1", "G001__col2") == "mirrorXG001__col1_struct_code_G001__col2__pending"


def test_batch_confirm_rebuilds_latest_payloads_and_table_confirm_reuses_pending_rows() -> None:
    source = _app_source()
    batch_block = _between(
        source,
        "struct_entry_batch_confirm_",
        "with confirm_cols[1]:",
    )
    assert "_collect_structure_entry_payloads(entry_results)" in batch_block
    assert "[dict(item) for item in pending_batch_payloads" not in batch_block

    table_block = _between(
        source,
        "struct_table_confirm_btn_",
        "with tc2:",
    )
    assert "pending_update_rows" in table_block
    assert "_prepare_structure_update_rows" not in table_block


def test_batch_save_defers_structure_code_widget_refresh_until_next_rerun() -> None:
    source = _app_source()
    refresh_block = _between(
        source,
        "def _refresh_entry_codes_after_batch_save",
        "def _collect_structure_entry_payloads",
    )

    assert 'st.session_state[f"{sid_key_now}__pending"] = new_code' in refresh_block
    assert "st.session_state[sid_key_now] = new_code" not in refresh_block


def test_relative_price_rewrite_does_not_rerun_before_save_button() -> None:
    source = _app_source()
    helper_block = _between(source, "def render_relative_price_text_input", "def render_numeric_text_input")
    spec_block = _between(source, "def render_spec_fields", "def render_phoenix_acc_fields")

    assert "_schedule_relative_price_rewrite(key, raw_txt, value, fmt=fmt)" in helper_block
    assert "st.rerun()" not in helper_block
    assert "_schedule_relative_price_rewrite(key, txt, val, fmt=widget_fmt)" in spec_block
    assert "if _schedule_relative_price_rewrite(key, txt, val, fmt=widget_fmt):" not in spec_block


def test_inline_field_hint_wraps_long_relative_price_text() -> None:
    source = _app_source()
    style_block = _between(source, ".otc-inline-field-hint {", ".otc-inline-field-hint-empty")

    assert "white-space: normal;" in style_block
    assert "overflow: visible;" in style_block
    assert "text-overflow: clip;" in style_block
    assert "overflow-wrap: anywhere;" in style_block
    assert "white-space: nowrap;" not in style_block
    assert "text-overflow: ellipsis;" not in style_block


def test_single_structure_save_commits_active_input_before_button_click() -> None:
    source = _app_source()
    save_block = _between(source, "if not compact_layout:", "pending_struct_payload = st.session_state.get")
    helper_block = _between(source, "def inject_data_editor_commit_before_button_click", "def hide_empty_structure_editor_columns")

    assert "inject_data_editor_commit_before_button_click" in save_block
    assert '"双击保存结构"' in save_block
    assert 'st.button("保存结构"' not in save_block
    assert '"确认保存结构（存在终止风险）"' in save_block
    assert '"当前表单另存为模板"' in save_block


    assert '[data-testid="stTextInput"] input' in helper_block
    assert '[data-testid="stTextArea"] textarea' in helper_block
    assert '[data-testid="stNumberInput"] input' in helper_block
    assert "incomingIntentMap" in helper_block
    assert "markButtonIntent(btn)" in helper_block
    assert "setNativeInputValue(intentInput, token)" in helper_block
    assert "__otcPendingCommittedButtonClick" in helper_block
    assert "event.preventDefault()" in helper_block
    assert "btn.click()" in helper_block
    assert "struct_save_intent_" in save_block
    assert "_consume_structure_entry_save_intent()" in save_block


def test_batch_structure_save_commits_active_inputs_and_reports_feedback() -> None:
    source = _app_source()
    batch_block = _between(source, "if compact_layout:", "quote_payloads_for_entry =")
    persist_batch_block = _between(source, "def _persist_structure_payloads_batch", "def _refresh_entry_codes_after_batch_save")
    feedback_block = _between(source, "def _toast_structure_entry_batch_message", "def _clear_structure_entry_batch_pending_state")

    assert "inject_data_editor_commit_before_button_click" in batch_block
    assert "struct_entry_batch_save_" in batch_block
    assert "struct_entry_batch_confirm_" in batch_block
    assert "struct_batch_save_intent_" in batch_block
    assert "_consume_structure_entry_batch_save_intent()" in batch_block
    assert 'batch_save_intent_action == "批量保存全部结构"' in batch_block
    assert 'batch_save_intent_action == "确认批量保存（存在终止风险）"' in batch_block
    assert "disabled=bool(duplicate_code_messages)" not in batch_block
    assert "_show_structure_entry_batch_error" in batch_block
    assert "st.toast(msg)" in feedback_block
    assert "_toast_structure_entry_batch_message(batch_error_msg)" in persist_batch_block


def test_single_structure_save_persists_termination_risk_without_second_click() -> None:
    source = _app_source()
    save_click_block = _between(source, "if save_clicked:", "pending_struct_payload = st.session_state.get")

    assert "_persist_structure_payload(" in save_click_block
    assert "success_message=" in save_click_block
    assert "st.session_state[struct_save_pending_key] = payload" not in save_click_block
    assert "为防止误录入，请二次确认是否继续保存" not in save_click_block


def test_single_structure_save_reports_success_and_failure_visibly() -> None:
    source = _app_source()
    feedback_block = _between(source, "def _toast_structure_entry_message", "strategy_cn_key =")
    persist_block = _between(source, "def _persist_structure_payload", "if not compact_layout:")
    save_click_block = _between(source, "if save_clicked:", "pending_struct_payload = st.session_state.get")

    assert "st.toast(msg)" in feedback_block
    assert "st.success(success_msg)" in feedback_block
    assert "_toast_structure_entry_message(success_msg)" in feedback_block
    assert "st.error(msg)" in feedback_block
    assert "_show_structure_save_error(" in persist_block
    assert "_show_structure_save_error(" in save_click_block
    assert "当前表单参数校验未通过" in save_click_block


def test_template_rules_can_be_added_and_json_failure_is_explicit() -> None:
    source = _app_source()
    template_block = _between(source, "rule_label_map = {", "struct_template_edit_save_")

    assert "st.multiselect(" in template_block
    assert "struct_template_rule_fields_" in template_block
    assert "available_rule_fields = list(STRUCTURE_TEMPLATE_PRICE_FIELDS)" in template_block

    save_block = _between(source, "struct_template_edit_save_", "tab_new, tab_active")
    assert "st.warning(" in save_block
    assert "edited_params_json = None" in save_block
    assert "upsert_structure_template" in save_block


def test_structure_update_validates_entry_price_and_avoids_gid_shadowing() -> None:
    source = _app_source()
    update_block = _between(source, "def _prepare_structure_update_rows", "def _apply_structure_update_rows")
    assert "entry_price is None" in update_block
    assert "np.isfinite(float(entry_price))" in update_block
    assert "entry_price = float(entry_price)" in update_block

    render_block = _between(source, "def _render_structure_entry_column", "def _clone_structure_entry_column_state")
    assert "entry_scope_gid = f\"{actual_gid}__{_safe_cache_name(entry_column_id)}\"" in render_block
    assert "\n            gid = f\"{actual_gid}__{_safe_cache_name(entry_column_id)}\"" not in render_block
    assert "actual_gid: str = str(gid)" in render_block


def test_structure_entry_keeps_current_transient_button_click_before_render() -> None:
    source = _app_source()
    render_block = _between(source, "def _render_structure_entry_column", "sid_key = f\"struct_code_{entry_scope_gid}\"")

    assert "if st.session_state.get(state_key) is True:" in render_block
    assert "continue\n                    st.session_state.pop(state_key, None)" in render_block
