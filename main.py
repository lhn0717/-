import streamlit as st
import pandas as pd
import sqlite3

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

# --- 2. 数据库初始化 ---
DB_FILE = 'water_manager_v17.db' # 升级版本号以匹配新单价逻辑
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

# 中英文字段对照表
COLUMN_MAP = {
    "month": "月份", "user_id": "房客/房间名", "u_diff": "实际读数用量",
    "avg_error": "分摊误差", "billing_q": "计费总量", "water_fee": "水费金额",
    "water_steps": "水费计算详情", "extra_total": "备注费用总计",
    "extra_desc": "备注明细", "total": "总合计"
}

init_db()

# --- 3. 状态管理 ---
if 'row_counts' not in st.session_state:
    st.session_state.row_counts = {i: 0 for i in range(1, 11)}
if 'expander_states' not in st.session_state:
    st.session_state.expander_states = {i: False for i in range(1, 11)}
if 'user_names' not in st.session_state:
    st.session_state.user_names = {i: f"房客 {i:02d}" for i in range(1, 11)}

# --- 4. 界面展示 ---
st.set_page_config(page_title="水电管家-调价版", layout="wide")
st.title("💧 水费核算系统 ")

# 侧边栏：已更新默认单价
st.sidebar.header("⚙️ 计费单价设置")
p1 = st.sidebar.number_input("第一档单价", value=3.2)
p2 = st.sidebar.number_input("第二档单价", value=5.3)
p3 = st.sidebar.number_input("第三档单价", value=7.6)

# 第一步：总表信息
with st.container(border=True):
    st.subheader("📊 第一步：总表读数")
    c1, c2, c3 = st.columns(3)
    with c1: month_str = st.selectbox("选择月份", [f"2026-{i:02d}" for i in range(1, 13)])
    with c2: m_s = st.number_input("总表期初", value=0.0, step=0.1)
    with c3: m_e = st.number_input("总表期末", value=0.0, step=0.1)
    main_total = max(0.0, m_e - m_s)
    st.info(f"💡 总表实际消耗：**{main_total:.2f}** 吨")

st.divider()

# 第二步：房客录入
st.subheader("👤 第二步：房客数据")
user_inputs = []
for i in range(1, 11):
    current_name = st.session_state.user_names[i]
    with st.expander(f"🏠 {current_name}", expanded=st.session_state.expander_states[i]):
        # 修改名字
        new_name = st.text_input("编辑名称", value=current_name, key=f"name_in_{i}")
        st.session_state.user_names[i] = new_name
        
        col_s, col_e = st.columns(2)
        u_s = col_s.number_input("月初读数", key=f"s_{i}", value=0.0)
        u_e = col_e.number_input("月末读数", key=f"e_{i}", value=0.0)
        u_diff = max(0.0, u_e - u_s)
        
        st.write("📋 备注费用项目：")
        extras = []
        for r in range(st.session_state.row_counts[i]):
            r_c1, r_c2 = st.columns([1, 2])
            ev = r_c1.number_input("金额", key=f"v_{i}_{r}", min_value=0.0)
            et = r_c2.text_input("项目说明", key=f"t_{i}_{r}")
            extras.append({"val": ev, "txt": et})
        
        b1, b2, _ = st.columns([1.5, 1, 2])
        if b1.button("➕ 增加备注项", key=f"add_{i}"):
            st.session_state.row_counts[i] += 1
            st.session_state.expander_states[i] = True
            st.rerun()
        if st.session_state.row_counts[i] > 0:
            if b2.button("🗑️ 清空备注", key=f"clr_{i}"):
                st.session_state.row_counts[i] = 0
                st.session_state.expander_states[i] = True
                st.rerun()
        
        user_inputs.append({"id": new_name, "diff": u_diff, "extras": extras})

# 第三步：核算与展示
st.divider()
if st.button("🚀 生成详细账单并保存", type="primary", use_container_width=True):
    for k in st.session_state.expander_states: st.session_state.expander_states[k] = False
    
    active_users = [u for u in user_inputs if u['diff'] > 0]
    N = len(active_users)
    sum_reported = sum(u['diff'] for u in user_inputs)
    total_error = main_total - sum_reported
    avg_error_val = total_error / N if N > 0 else 0.0
    
    final_data = []
    conn = sqlite3.connect(DB_FILE)
    for u in user_inputs:
        p_err = avg_error_val if u['diff'] > 0 else 0.0
        billing_q = u['diff'] + p_err
        w_fee, w_steps = calculate_stepped_fee_detailed(billing_q, N, p1, p2, p3)
        e_sum = sum(item['val'] for item in u['extras'])
        e_desc = " | ".join([f"{item['txt']}({item['val']})" for item in u['extras'] if item['val']>0])
        grand_total = round(w_fee + e_sum, 2)
        
        conn.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (month_str, u['id'], u['diff'], p_err, billing_q, w_fee, w_steps, e_sum, e_desc, grand_total))
        
        final_data.append({
            "房客/房间名": u['id'], "实际用量": f"{u['diff']:.1f}t",
            "分摊误差": f"{p_err:.2f}t", "计费总量": f"{billing_q:.2f}t",
            "水费详情": w_steps, "水费金额": w_fee,
            "备注总额": e_sum, "备注明细": e_desc if e_desc else "无",
            "总合计": grand_total
        })
    conn.commit()
    conn.close()
    
    df_res = pd.DataFrame(final_data)
    st.table(df_res)
    
    csv_data = df_res.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下载本月中文账单 (.csv)", data=csv_data, 
                       file_name=f"{month_str}水费账单_新单价.csv", use_container_width=True)

# 历史记录
st.divider()
if st.checkbox("📜 查看/导出历史全量报表"):
    conn = sqlite3.connect(DB_FILE)
    try:
        h_df = pd.read_sql("SELECT * FROM records ORDER BY month DESC", conn)
        conn.close()
        if not h_df.empty:
            h_df_cn = h_df.rename(columns=COLUMN_MAP)
            sel_m = st.selectbox("选择月份查询", h_df_cn['月份'].unique())
            st.dataframe(h_df_cn[h_df_cn['月份'] == sel_m], use_container_width=True)
            full_csv = h_df_cn.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 导出全量历史数据", data=full_csv, file_name="水电费历史记录.csv")
    except:
        st.warning("如遇到数据读取错误，可尝试修复数据库。")
        if st.button("修复数据库"):
            import os
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()