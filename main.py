import streamlit as st
import pandas as pd
import sqlite3
import os

# --- 1. 核心计费函数 ---
def calculate_stepped_fee_detailed(usage, N, p1, p2, p3):
    if N <= 0 or usage <= 0: return 0.0, "未使用"
    t1_limit = 18 / N
    t2_limit = 40 / N
    fee, steps = 0.0, []
    u1 = min(usage, t1_limit)
    fee += u1 * p1
    steps.append(f"一档:{u1:.2f}t×{p1}")
    if usage > t1_limit:
        u2 = min(usage, t2_limit) - t1_limit
        fee += u2 * p2
        steps.append(f"二档:{u2:.2f}t×{p2}")
    if usage > t2_limit:
        u3 = usage - t2_limit
        fee += u3 * p3
        steps.append(f"三档:{u3:.2f}t×{p3}")
    return round(fee, 2), " + ".join(steps)

# --- 2. 数据库与持久化逻辑 ---
DB_FILE = 'utility_manager_v25.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS records (
                    month TEXT, user_id TEXT, u_diff REAL, 
                    avg_error REAL, billing_q REAL, 
                    water_fee REAL, water_steps TEXT,
                    extra_total REAL, extra_desc TEXT, 
                    total REAL, PRIMARY KEY (month, user_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS drafts (
                    key TEXT PRIMARY KEY, val TEXT)''')
    conn.commit()
    conn.close()

# 中文表头映射表
COLUMN_MAP = {
    "month": "核算月份",
    "user_id": "名称",
    "u_diff": "表内用量",
    "avg_error": "误差分摊",
    "billing_q": "计费总量",
    "water_fee": "费用金额",
    "water_steps": "计算过程",
    "extra_total": "备注总计",
    "extra_desc": "备注明细",
    "total": "应缴合计"
}

def save_draft(key, val):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT OR REPLACE INTO drafts VALUES (?, ?)", (str(key), str(val)))
    conn.commit()
    conn.close()

def load_drafts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.execute("SELECT key, val FROM drafts")
    data = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return data

init_db()
draft_data = load_drafts()

# --- 3. 状态管理 ---
if 'user_count' not in st.session_state:
    st.session_state.user_count = int(draft_data.get('user_count', 10))
if 'row_counts' not in st.session_state:
    st.session_state.row_counts = {int(i): int(v) for i, v in draft_data.items() if i.isdigit()}
if 'user_names' not in st.session_state:
    st.session_state.user_names = {int(k.split('_')[1]): v for k, v in draft_data.items() if k.startswith('un_')}

# --- 4. 界面展示 ---
st.set_page_config(page_title="家庭水电燃气费用核算系统", layout="wide")
st.title("🏠 家庭水电燃气费用核算系统")

with st.container(border=True):
    st.subheader("📊 第一步：设置单价与录入总表")
    cp1, cp2, cp3 = st.columns(3)
    p1 = cp1.number_input("第一档单价", value=float(draft_data.get('p1', 3.2)), on_change=lambda: save_draft('p1', st.session_state.p1_in), key="p1_in")
    p2 = cp2.number_input("第二档单价", value=float(draft_data.get('p2', 4.3)), on_change=lambda: save_draft('p2', st.session_state.p2_in), key="p2_in")
    p3 = cp3.number_input("第三档单价", value=float(draft_data.get('p3', 7.6)), on_change=lambda: save_draft('p3', st.session_state.p3_in), key="p3_in")
    st.caption("📢 说明：水电燃气总表分别设置三档，各个用户在档内分摊可用数额。")
    st.write("---")
    c1, c2, c3 = st.columns(3)
    month_str = c1.selectbox("当前核算月份", [f"2026-{i:02d}" for i in range(1, 13)])
    m_s = c2.number_input("总表期初 (上月读数)", value=float(draft_data.get('m_s', 0.0)), on_change=lambda: save_draft('m_s', st.session_state.ms_in), key="ms_in")
    m_e = c3.number_input("总表期末 (本月读数)", value=float(draft_data.get('m_e', 0.0)), on_change=lambda: save_draft('m_e', st.session_state.me_in), key="me_in")
    main_total = max(0.0, m_e - m_s)
    st.info(f"💡 总表本月实际总消耗：**{main_total:.2f}**")

st.divider()

# 第二步：数据录入
st.subheader("👤 第二步：录入各表数据")
user_inputs = []
for i in range(1, st.session_state.user_count + 1):
    if i not in st.session_state.row_counts: st.session_state.row_counts[i] = 0
    if i not in st.session_state.user_names: st.session_state.user_names[i] = f"房客 {i:02d}"
    
    cur_name = st.session_state.user_names[i]
    with st.expander(f"🏠 {cur_name}"):
        new_name = st.text_input("名称", value=cur_name, key=f"ni_{i}", on_change=lambda i=i: save_draft(f'un_{i}', st.session_state[f"ni_{i}"]))
        st.session_state.user_names[i] = new_name
        
        col_s, col_e = st.columns(2)
        u_s = col_s.number_input("上月读数", value=float(draft_data.get(f"s_{i}", 0.0)), key=f"si_{i}", on_change=lambda i=i: save_draft(f's_{i}', st.session_state[f"si_{i}"]))
        u_e = col_e.number_input("本月读数", value=float(draft_data.get(f"e_{i}", 0.0)), key=f"ei_{i}", on_change=lambda i=i: save_draft(f'e_{i}', st.session_state[f"ei_{i}"]))
        u_diff = max(0.0, u_e - u_s)
        
        extras = []
        for r in range(st.session_state.row_counts[i]):
            r_c1, r_c2 = st.columns([1, 2])
            ev = r_c1.number_input("金额", key=f"vi_{i}_{r}", value=float(draft_data.get(f"v_{i}_{r}", 0.0)), on_change=lambda i=i, r=r: save_draft(f'v_{i}_{r}', st.session_state[f"vi_{i}_{r}"]))
            et = r_c2.text_input("说明", key=f"ti_{i}_{r}", value=draft_data.get(f"t_{i}_{r}", ""), on_change=lambda i=i, r=r: save_draft(f't_{i}_{r}', st.session_state[f"ti_{i}_{r}"]))
            extras.append({"val": ev, "txt": et})
        
        if st.button("➕ 增加备注", key=f"btn_add_{i}"):
            st.session_state.row_counts[i] += 1
            save_draft(i, st.session_state.row_counts[i])
            st.rerun()
        user_inputs.append({"id": new_name, "diff": u_diff, "extras": extras})

col_add, col_clear = st.columns([1, 1])
if col_add.button("➕ 添加名额", use_container_width=True):
    st.session_state.user_count += 1
    save_draft('user_count', st.session_state.user_count)
    st.rerun()

if col_clear.button("🧹 清空所有草稿数据", use_container_width=True):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM drafts")
    conn.commit()
    conn.close()
    st.rerun()

# 第三步：核算
st.divider()
if st.button("🚀 生成详细账单", type="primary", use_container_width=True):
    active_users = [u for u in user_inputs if u['diff'] > 0]
    N = len(active_users)
    avg_error_val = max(0.0, (main_total - sum(u['diff'] for u in user_inputs)) / N) if N > 0 else 0.0
    
    final_table_data = []
    conn = sqlite3.connect(DB_FILE)
    for idx, u in enumerate(user_inputs, 1):
        p_err = avg_error_val if u['diff'] > 0 else 0.0
        billing_q = u['diff'] + p_err
        w_fee, w_steps = calculate_stepped_fee_detailed(billing_q, N, p1, p2, p3)
        e_sum = sum(item['val'] for item in u['extras'])
        e_desc = " | ".join([f"{item['txt']}({item['val']})" for item in u['extras'] if item['val']!=0])
        grand_total = round(w_fee + e_sum, 2)
        
        conn.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (month_str, u['id'], u['diff'], p_err, billing_q, w_fee, w_steps, e_sum, e_desc, grand_total))
        
        final_table_data.append({
            "序号": idx, "名称": u['id'], "表内用量": f"{u['diff']:.1f}", 
            "误差分摊": f"{p_err:.2f}", "计费总量": f"{billing_q:.2f}", 
            "费用金额": w_fee, "计算过程": w_steps, "备注总计": e_sum, 
            "备注明细": e_desc if e_desc else "-", "应缴合计": grand_total
        })
    conn.commit()
    conn.close()
    st.table(pd.DataFrame(final_table_data))
    st.success("账单已生成并存入历史记录！")

# 历史记录 (表头中文化)
st.divider()
if st.checkbox("📜 查看/导出历史记录"):
    conn = sqlite3.connect(DB_FILE)
    try:
        h_df = pd.read_sql("SELECT * FROM records ORDER BY month DESC", conn)
        conn.close()
        if not h_df.empty:
            # 应用中文表头映射
            h_df_cn = h_df.rename(columns=COLUMN_MAP)
            
            sel_m = st.selectbox("筛选月份", h_df_cn['核算月份'].unique())
            display_df = h_df_cn[h_df_cn['核算月份'] == sel_m]
            
            st.dataframe(display_df, use_container_width=True)
            
            # 导出 CSV (包含中文表头)
            csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 导出 {sel_m} 账单 (中文表头)",
                data=csv_data,
                file_name=f"{sel_m}_账单.csv",
                mime='text/csv',
                use_container_width=True
            )
    except Exception as e:
        st.info("暂无历史记录或数据读取异常")