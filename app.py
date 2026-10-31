import html
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).parent / "shopping_list.json"
EMPTY_NAME_MSG = "아이템 이름을 입력해주세요."
SAVE_FAIL_MSG = "저장하지 못했어요. 파일 권한이나 디스크 공간을 확인해주세요."
MAX_QTY = 999


@st.cache_resource
def get_lock():
    """세션(탭) 간 파일 접근을 직렬화하는 락. 스크립트가 재실행돼도 하나만 유지된다."""
    return threading.Lock()


def clamp_qty(value):
    return min(MAX_QTY, max(1, int(value)))


# ---------- 저장 / 불러오기 (F7) ----------
def load_items():
    """JSON 파일에서 목록을 읽는다. 파일이 없거나 깨져 있으면 빈 목록."""
    if not DATA_FILE.exists():
        return []
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []
    if not isinstance(data, list):
        return []
    items = []
    for d in data:
        try:
            items.append(
                {
                    "id": str(d["id"]),
                    "name": str(d["name"]),
                    "qty": clamp_qty(d["qty"]),
                    "done": bool(d["done"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue  # 형식이 맞지 않는 항목은 건너뜀
    return items


def write_items(items):
    """임시 파일에 쓴 뒤 교체한다. 쓰는 도중 중단돼도 기존 파일은 깨지지 않는다."""
    fd, tmp = tempfile.mkstemp(dir=DATA_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_error(msg, where="add"):
    """where: 'add'면 화면 상단, 'edit'면 수정 중인 행 아래에 표시."""
    st.session_state.error = msg
    st.session_state.error_where = where


def mutate(fn, where="add"):
    """파일을 다시 읽어 변경을 적용하고 저장한다. 성공 여부를 반환한다.

    다른 탭에서 바뀐 내용 위에 변경을 얹으므로 서로의 변경을 덮어쓰지 않는다.
    """
    with get_lock():
        items = load_items()
        fn(items)
        try:
            write_items(items)
        except OSError:
            set_error(SAVE_FAIL_MSG, where)
            return False
    set_error("")
    return True


def init_state():
    if "editing" not in st.session_state:
        st.session_state.editing = None  # 수정 중인 항목 id
        st.session_state.error = ""
        st.session_state.error_where = "add"
    # 매 실행마다 파일에서 읽어 다른 탭의 변경도 반영한다
    st.session_state.shopping_items = load_items()


# ---------- 콜백 ----------
def add_item():  # F1
    name = st.session_state.new_name.strip()
    if not name:
        set_error(EMPTY_NAME_MSG, "add")
        return
    qty = clamp_qty(st.session_state.new_qty)
    mutate(lambda items: items.append(
        {"id": uuid.uuid4().hex, "name": name, "qty": qty, "done": False}
    ))


def start_edit(item_id):  # F2
    st.session_state.editing = item_id
    set_error("")


def cancel_edit():
    st.session_state.editing = None
    set_error("")


def save_edit(item_id):  # F2
    name = st.session_state[f"edit_name_{item_id}"].strip()
    if not name:
        set_error(EMPTY_NAME_MSG, "edit")
        return
    qty = clamp_qty(st.session_state[f"edit_qty_{item_id}"])

    def apply(items):
        for it in items:
            if it["id"] == item_id:
                it["name"], it["qty"] = name, qty

    if mutate(apply, "edit"):
        st.session_state.editing = None


def delete_item(item_id):  # F3
    mutate(lambda items: items.__setitem__(
        slice(None), [i for i in items if i["id"] != item_id]
    ))
    if st.session_state.editing == item_id:
        st.session_state.editing = None


def toggle_item(item_id):  # F4
    checked = st.session_state[f"chk_{item_id}"]

    def apply(items):
        for it in items:
            if it["id"] == item_id:
                it["done"] = checked

    mutate(apply)


def clear_done():  # F6
    mutate(lambda items: items.__setitem__(
        slice(None), [i for i in items if not i["done"]]
    ))
    if st.session_state.editing not in {i["id"] for i in load_items()}:
        st.session_state.editing = None


# ---------- 화면 ----------
CSS = """
<style>
/* 밝은/어두운 테마 모두에서 읽히도록 currentColor와 반투명 회색만 사용 */
.block-container { max-width: 640px; padding-top: 2.5rem; }
.app-sub { opacity: .65; margin: -0.6rem 0 1.2rem; font-size: .95rem; }

/* 모바일에서도 한 줄 유지 (Streamlit 기본은 좁으면 세로로 쌓임) */
[class*="st-key-row_"] [data-testid="stHorizontalBlock"],
[class*="st-key-add_form"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; gap: .4rem; align-items: center;
}
[class*="st-key-row_"] [data-testid="stColumn"],
[class*="st-key-add_form"] [data-testid="stColumn"] {
    min-width: 0 !important;
}

/* 항목 카드 */
[class*="st-key-row_"] { border-radius: 12px; }
[class*="st-key-row_"] [data-testid="stVerticalBlock"],
[class*="st-key-row_done_"] [data-testid="stVerticalBlock"] { gap: 0; }
[class*="st-key-row_"] [data-testid="stColumn"] p,
[class*="st-key-row_done_"] [data-testid="stColumn"] p { margin: 0; }
[class*="st-key-row_done_"] { opacity: .55; }

/* 수량 배지 */
.qty-wrap { text-align: center; line-height: 1; margin: 0; }
[class*="st-key-row_"] [data-testid="stMarkdownContainer"],
[class*="st-key-row_done_"] [data-testid="stMarkdownContainer"] { margin: 0; }
[class*="st-key-row_"] [data-testid="stColumn"] [data-testid="stElementContainer"],
[class*="st-key-row_done_"] [data-testid="stColumn"] [data-testid="stElementContainer"] { margin: 0; }
.qty-badge {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    background: rgba(128,128,128,.2); font-size: .85rem; font-weight: 600;
    white-space: nowrap; max-width: 100%; overflow: hidden;
    text-overflow: ellipsis; vertical-align: middle;
}

/* 아이템 이름 (긴 이름은 줄바꿈, 완료는 취소선) */
.item-name { overflow-wrap: anywhere; line-height: 1.35; }
.item-name.done { text-decoration: line-through; }

/* 수정/삭제 아이콘 버튼은 작고 눈에 덜 띄게 */
[class*="st-key-row_"] button[kind="tertiary"],
[class*="st-key-row_done_"] button[kind="tertiary"] {
    opacity: .55; padding: 2px 6px; min-height: 0; transition: opacity .15s;
}
[class*="st-key-row_"] button[kind="tertiary"]:hover,
[class*="st-key-row_done_"] button[kind="tertiary"]:hover { opacity: 1; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def render_add_form():
    with st.container(key="add_form"):
        with st.form("add_form_inner", clear_on_submit=True, border=True):
            c1, c2, c3 = st.columns([6, 2.4, 2.4], vertical_alignment="center")
            c1.text_input(
                "아이템 이름", key="new_name", placeholder="사야 할 물건을 입력하세요",
                label_visibility="collapsed",
            )
            c2.number_input(
                "수량", min_value=1, max_value=MAX_QTY, step=1, key="new_qty",
                label_visibility="collapsed",
            )
            c3.form_submit_button(
                "추가", on_click=add_item, type="primary", use_container_width=True,
            )


def render_progress():  # F5
    items = st.session_state.shopping_items
    total = len(items)
    done = sum(1 for i in items if i["done"])
    if total == 0:
        st.markdown("&nbsp;")
        st.info("🧺 장바구니가 비어 있어요. 위에서 첫 아이템을 추가해보세요!")
    else:
        st.progress(done / total, text=f"{done} / {total} 완료")
        if done == total:
            st.success("🎉 모두 담았어요! 장보기 끝!")
    return done


def render_item(it):
    iid = it["id"]
    prefix = "row_done_" if it["done"] and st.session_state.editing != iid else "row_"
    with st.container(key=f"{prefix}{iid}", border=True):
        if st.session_state.editing == iid:
            c1, c2, c3, c4 = st.columns([5, 2, 1.2, 1.2], vertical_alignment="center")
            c1.text_input("이름", value=it["name"], key=f"edit_name_{iid}",
                          label_visibility="collapsed")
            c2.number_input("수량", min_value=1, max_value=MAX_QTY, value=it["qty"],
                            step=1, key=f"edit_qty_{iid}", label_visibility="collapsed")
            c3.button("💾", key=f"save_{iid}", help="저장", type="tertiary",
                      on_click=save_edit, args=(iid,))
            c4.button("✖️", key=f"cancel_{iid}", help="취소", type="tertiary",
                      on_click=cancel_edit)
            if st.session_state.error and st.session_state.error_where == "edit":
                st.warning(st.session_state.error)
        else:
            c0, c1, c2, c3, c4 = st.columns([0.9, 7, 2, 1.2, 1.2],
                                            vertical_alignment="center")
            # 체크박스 라벨은 마크다운으로 해석되므로 화면에는 보이지 않게 두고(접근성용),
            # 이름은 이스케이프한 HTML 블록으로 따로 표시한다.
            c0.checkbox(it["name"], value=it["done"], key=f"chk_{iid}",
                        label_visibility="collapsed",
                        on_change=toggle_item, args=(iid,))
            # 블록 HTML 안의 내용은 마크다운/수식/이모지 코드로 해석되지 않는다
            cls = "item-name done" if it["done"] else "item-name"
            c1.markdown(f'<div class="{cls}">{html.escape(it["name"], quote=False)}</div>',
                        unsafe_allow_html=True)
            c2.markdown(f'<div class="qty-wrap"><span class="qty-badge">x{it["qty"]}</span></div>',
                        unsafe_allow_html=True)
            c3.button("✏️", key=f"edit_{iid}", help="수정", type="tertiary",
                      on_click=start_edit, args=(iid,))
            c4.button("🗑️", key=f"del_{iid}", help="삭제", type="tertiary",
                      on_click=delete_item, args=(iid,))


def main():
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")
    init_state()
    inject_css()
    st.title("🛒 쇼핑 리스트")
    st.markdown('<div class="app-sub">살 물건을 적고, 담을 때마다 체크하세요.</div>',
                unsafe_allow_html=True)
    render_add_form()
    if st.session_state.error and st.session_state.error_where == "add":
        st.warning(st.session_state.error)
    done = render_progress()
    for it in st.session_state.shopping_items:
        render_item(it)
    if done > 0:
        st.button("🧹 완료 항목 삭제", on_click=clear_done)


main()
