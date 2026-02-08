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

# --- 2. 数据库逻辑 ---
DB_FILE = 'water_manager_v20.db'
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS records (
                    month TEXT, user_id TEXT, u_diff REAL, 
                    avg_error REAL, billing_q REAL, 
                    water_fee REAL, water_steps TEXT,
                    extra_total REAL, extra_desc TEXT, 
                    total REAL, PRIMARY KEY (month, user_id))''')
    conn.commit()
    conn.close()

# 字段映射表（用于历史记录显示）
COLUMN_MAP = {
    "month": "月份", "user_id": "房客/房间名", "u_diff": "实际用量",
    "avg_error": "分摊误差", "billing_q": "计费总量", "water_fee": "水费金额",
    "water_steps": "计算详情", "extra_total": "备注总计",
    "extra_desc": "备注明细", "total": "最终应缴"
}

init_db()

# --- 3. 状态管理 ---
if 'user_count' not in st.session_state:
    st.session_state.user_count = 10
if 'row_counts' not in st.session_state:
    st.session_state.row_counts = {}
if 'expander_states' not in st.session_state:
    st.session_state.expander_states = {}
if 'user_names' not in st.session_state:
    st.session_state.user_names = {}

# 动态补全状态
for i in range(1, st.session_state.user_count + 1):
    if i not in st.session_state.row_counts: st.session_state.row_counts[i] = 0
    if i not in st.session_state.expander_states: st.session_state.expander_states[i] = False
    if i not in st.session_state.user_names: st.session_state.user_names[i] = f"房客 {i:02d}"

# --- 4. 界面展示 ---
st.set_page_config(page_title="水电管家终极全功能版", layout="wide")
st.title("🏠 水电费核算系统 (全功能版)")

# 侧边栏：单价修正
st.sidebar.header("⚙️ 单价设置")
p1 = st.sidebar.number_input("第一档单价", value=3.2)
p2 = st.sidebar.number_input("第二档单价", value=4.3) 
p3 = st.sidebar.number_input("第三档单价", value=7.6)

# 第一步：总表
with st.container(border=True):
    st.subheader("📊 第一步：录入总表读数")
    c1, c2, c3 = st.columns(3)
    with c1: month_str = st.selectbox("月份", [f"2026-{i:02d}" for i in range(1, 13)])
    with c2: m_s = st.number_input("总表期初 (上月)", value=0.0)
    with c3: m_e = st.number_input("总表期末 (本月)", value=0.0)
    main_total = max(0.0, m_e - m_s)
    st.info(f"💡 总表实际消耗：**{main_total:.2f}** 吨")

st.divider()

# 第二步：房客录入
st.subheader("👤 第二步：录入房客数据")
user_inputs = []
for i in range(1, st.session_state.user_count + 1):
    current_name = st.session_state.user_names[i]
    with st.expander(f"🏠 {current_name}", expanded=st.session_state.expander_states[i]):
        new_name = st.text_input("编辑名称", value=current_name, key=f"name_{i}")
        st.session_state.user_names[i] = new_name
        
        col_s, col_e = st.columns(2)
        u_s = col_s.number_input("月初读数", key=f"s_{i}", value=0.0)
        u_e = col_e.number_input("月末读数", key=f"e_{i}", value=0.0)
        u_diff = max(0.0, u_e - u_s)
        
        st.write("📋 备注费用 (正数为增加，负数为扣除)：")
        extras = []
        for r in range(st.session_state.row_counts[i]):
            r_c1, r_c2 = st.columns([1, 2])
            ev = r_c1.number_input("金额", key=f"v_{i}_{r}")
            et = r_c2.text_input("说明", key=f"t_{i}_{r}")
            extras.append({"val": ev, "txt": et})
        
        b1, b2, _ = st.columns([1.5, 1, 2])
        if b1.button("➕ 增加备注", key=f"add_{i}"):
            st.session_state.row_counts[i] += 1
            st.session_state.expander_states[i] = True
            st.rerun()
        if st.session_state.row_counts[i] > 0:
            if b2.button("🗑️ 清空备注", key=f"clr_{i}"):
                st.session_state.row_counts[i] = 0
                st.session_state.expander_states[i] = True
                st.rerun()
        user_inputs.append({"id": new_name, "diff": u_diff, "extras": extras})

# 动态添加房客按钮
if st.button("➕ 添加一个房客名额", use_container_width=True):
    st.session_state.user_count += 1
    st.rerun()

# 第三步：计算
st.divider()
if st.button("🚀 核算并生成账单", type="primary", use_container_width=True):
    for k in st.session_state.expander_states: st.session_state.expander_states[k] = False
    
    active_users = [u for u in user_inputs if u['diff'] > 0]
    N = len(active_users)
    sum_reported = sum(u['diff'] for u in user_inputs)
    total_error = main_total - sum_reported
    
    # 分摊误差逻辑：若为负数则显示为0
    avg_error_val = max(0.0, total_error / N) if N > 0 else 0.0
    
    final_table_data = []
    conn = sqlite3.connect(DB_FILE)
    for idx, u in enumerate(user_inputs, 1): # 序号从1开始
        p_err = avg_error_val if u['diff'] > 0 else 0.0
        billing_q = u['diff'] + p_err
        w_fee, w_steps = calculate_stepped_fee_detailed(billing_q, N, p1, p2, p3)
        e_sum = sum(item['val'] for item in u['extras'])
        e_desc = " | ".join([f"{item['txt']}({item['val']})" for item in u['extras'] if item['val']!=0])
        grand_total = round(w_fee + e_sum, 2)
        
        conn.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (month_str, u['id'], u['diff'], p_err, billing_q, w_fee, w_steps, e_sum, e_desc, grand_total))
        
        final_table_data.append({
            "序号": idx, "房客/房间名": u['id'], "用量": f"{u['diff']:.1f}t",
            "误差分摊": f"{p_err:.2f}t", "计费量": f"{billing_q:.2f}t",
            "计算过程": w_steps, "水费": w_fee, "备注总计": e_sum, 
            "备注明细": e_desc if e_desc else "-", "应缴合计": grand_total
        })
    conn.commit()
    conn.close()
    
    st.table(pd.DataFrame(final_table_data))
    csv_now = pd.DataFrame(final_table_data).to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下载本月账单", data=csv_now, file_name=f"{month_str}账单.csv", use_container_width=True)

# --- 5. 历史记录 (完整保留并优化) ---
st.divider()
if st.checkbox("📜 查看/导出历史记录"):
    conn = sqlite3.connect(DB_FILE)
    try:
        h_df = pd.read_sql("SELECT * FROM records ORDER BY month DESC", conn)
        conn.close()
        if not h_df.empty:
            h_df_cn = h_df.rename(columns=COLUMN_MAP)
            sel_m = st.selectbox("筛选历史月份", h_df_cn['月份'].unique())
            st.dataframe(h_df_cn[h_df_cn['月份'] == sel_m], use_container_width=True)
            
            full_csv = h_df_cn.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 导出全量历史备份", data=full_csv, file_name="全量历史记录.csv")
        else:
            st.info("目前没有历史记录。")
    except Exception as e:
        st.error("历史数据读取出错，可能由于版本冲突。")
        if st.button("⚠️ 点击修复并初始化数据库"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()