import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO

# --- 1. 数据库设置 ---
DB_FILE = 'water_system_v6.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records (
                    month TEXT, user_id TEXT, 
                    user_usage REAL, water_fee REAL, 
                    note1 REAL, note2 REAL, total REAL,
                    PRIMARY KEY (month, user_id))''')
    conn.commit()
    conn.close()

init_db()

# --- 2. 核心计费逻辑 ---
def calculate_stepped_fee(usage, N, p1, p2, p3):
    if N <= 0 or usage <= 0: return 0.0
    t1_limit = 18 / N
    t2_limit = 40 / N
    if usage <= t1_limit:
        return round(usage * p1, 2)
    elif usage <= t2_limit:
        return round((t1_limit * p1) + (usage - t1_limit) * p2, 2)
    else:
        return round((t1_limit * p1) + ((t2_limit - t1_limit) * p2) + (usage - t2_limit) * p3, 2)

# --- 3. 界面 ---
st.set_page_config(page_title="水费收缴助手", layout="centered")
st.title("💧 水费收缴助手 (手机版)")

# 计费规则设置 (侧边栏)
st.sidebar.header("⚙️ 单价自定义")
p1 = st.sidebar.number_input("一档单价", value=2.2)
p2 = st.sidebar.number_input("二档单价", value=3.3)
p3 = st.sidebar.number_input("三档单价", value=6.6)

# 显示规则
with st.expander("📖 计费规则说明"):
    st.write(f"当前模式：按人数 N 分摊 18/40 吨额度")
    st.write(f"价格：{p1}元 / {p2}元 / {p3}元")

# --- 总表区 ---
st.subheader("📊 表1：总表读数")
with st.container(border=True):
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        month_str = st.selectbox("月份", [f"2026-{i:02d}" for i in range(1, 13)])
    with c2:
        main_s = st.number_input("总表期初", min_value=0.0)
    with c3:
        main_e = st.number_input("总表期末", min_value=0.0)
    total_main = max(0.0, main_e - main_s)
    st.info(f"本月总消耗：{total_main:.1f} 吨")

# --- 房客录入区 ---
st.subheader("👤 表2：房客用量")
user_inputs = []
# 手机端建议使用列表形式，更易点击
for i in range(1, 11):
    with st.expander(f"房客 {i:02d} 的数据"):
        col_u, col_n1, col_n2 = st.columns(3)
        with col_u:
            u_usage = st.number_input("用水量", key=f"u{i}", min_value=0.0)
        with col_n1:
            n1 = st.number_input("房租", key=f"n1{i}", value=0.0)
        with col_n2:
            n2 = st.number_input("备注", key=f"n2{i}", value=0.0)
        user_inputs.append({"id": f"房客 {i:02d}", "usage": u_usage, "n1": n1, "n2": n2})

# --- 计算与保存 ---
active_users = [u for u in user_inputs if u['usage'] > 0]
N = len(active_users)
sum_reported = sum(u['usage'] for u in user_inputs)
avg_err = (total_main - sum_reported) / N if N > 0 else 0.0

if st.button("🚀 生成并存为本月记录", type="primary", use_container_width=True):
    conn = sqlite3.connect(DB_FILE)
    results = []
    for u in user_inputs:
        err = avg_err if u['usage'] > 0 else 0.0
        final_q = u['usage'] + err
        fee = calculate_stepped_fee(final_q, N, p1, p2, p3)
        total_p = round(fee + u['n1'] + u['n2'], 2)
        
        conn.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?)",
                     (month_str, u['id'], u['usage'], fee, u['n1'], u['n2'], total_p))
        results.append({"房客": u['id'], "用量": u['usage'], "合计": total_p})
    conn.commit()
    conn.close()
    st.success("数据已存入手机本地缓存")
    st.table(pd.DataFrame(results))

# --- 查看历史 ---
st.divider()
st.subheader("📜 历史数据查看")
conn = sqlite3.connect(DB_FILE)
history_df = pd.read_sql(f"SELECT * FROM records ORDER BY month DESC", conn)
conn.close()

if not history_df.empty:
    target_m = st.selectbox("筛选历史月份", history_df['month'].unique())
    st.dataframe(history_df[history_df['month'] == target_m], use_container_width=True)
    
    # 导出按钮 (防止云端丢失数据)
    csv = history_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 导出全量历史数据(CSV)", data=csv, file_name="water_backup.csv", mime="text/csv")
else:
    st.write("暂无历史记录")