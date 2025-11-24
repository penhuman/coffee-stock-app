import streamlit as st
import sqlite3
import pandas as pd
import datetime

# --- 設定網頁標題與佈局 ---
st.set_page_config(page_title="☁️ 雲端咖啡生豆庫存", layout="wide")

# --- 資料庫連線函式 ---
# 使用 st.cache_resource 確保資料庫連線不會因為網頁重新整理而重連過多次
@st.cache_resource
def get_connection():
    conn = sqlite3.connect('cloud_coffee.db', check_same_thread=False)
    return conn

conn = get_connection()

# --- 初始化資料表 ---
def init_db():
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS beans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            origin TEXT,
            process TEXT,
            stock_weight REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bean_id INTEGER,
            action_type TEXT,
            amount_change REAL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(bean_id) REFERENCES beans(id)
        )
    ''')
    conn.commit()

init_db()

# --- 側邊欄選單 ---
st.sidebar.title("☕ 選單")
menu = st.sidebar.radio("請選擇功能", ["📊 現存量儀表板", "📦 進豆入庫", "🔥 烘豆取出", "📝 盤點修正", "📜 異動紀錄"])

# --- 功能 1: 現存量儀表板 ---
if menu == "📊 現存量儀表板":
    st.title("📊 咖啡生豆現存量")
    
    # 讀取資料
    df = pd.read_sql("SELECT name as '豆名', origin as '產地', process as '處理法', stock_weight as '庫存(kg)', updated_at as '更新時間' FROM beans", conn)
    
    if not df.empty:
        # 顯示漂亮的數據指標
        total_stock = df['庫存(kg)'].sum()
        col1, col2 = st.columns(2)
        col1.metric("總庫存重量", f"{total_stock:.2f} kg")
        col2.metric("豆種數量", f"{len(df)} 款")
        
        # 顯示表格
        st.dataframe(df, use_container_width=True)
    else:
        st.info("目前沒有庫存資料，請先到「進豆入庫」新增。")

# --- 功能 2: 進豆入庫 ---
elif menu == "📦 進豆入庫":
    st.title("📦 進豆入庫")
    
    with st.form("inbound_form"):
        name = st.text_input("豆名 (必填)")
        col1, col2 = st.columns(2)
        origin = col1.text_input("產地")
        process = col2.text_input("處理法")
        weight = st.number_input("入庫重量 (kg)", min_value=0.0, step=0.1)
        
        submitted = st.form_submit_button("確認入庫")
        
        if submitted:
            if not name:
                st.error("請輸入豆名")
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT id, stock_weight FROM beans WHERE name=?", (name,))
                existing = cursor.fetchone()
                
                if existing:
                    bean_id, current_stock = existing
                    new_stock = current_stock + weight
                    cursor.execute("UPDATE beans SET stock_weight=?, origin=?, process=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", 
                                   (new_stock, origin, process, bean_id))
                    cursor.execute("INSERT INTO transactions (bean_id, action_type, amount_change, note) VALUES (?, ?, ?, ?)",
                                   (bean_id, 'INBOUND', weight, '進豆入庫'))
                    st.success(f"✅ 已更新 {name}，目前庫存: {new_stock:.2f} kg")
                else:
                    cursor.execute("INSERT INTO beans (name, origin, process, stock_weight) VALUES (?, ?, ?, ?)", 
                                   (name, origin, process, weight))
                    bean_id = cursor.lastrowid
                    cursor.execute("INSERT INTO transactions (bean_id, action_type, amount_change, note) VALUES (?, ?, ?, ?)",
                                   (bean_id, 'INBOUND', weight, '新豆建檔'))
                    st.success(f"✅ 已新增 {name}，庫存: {weight:.2f} kg")
                conn.commit()

# --- 功能 3: 烘豆取出 ---
elif menu == "🔥 烘豆取出":
    st.title("🔥 烘豆消耗登記")
    
    # 取得豆單
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM beans ORDER BY name")
    bean_list = [row[0] for row in cursor.fetchall()]
    
    if not bean_list:
        st.warning("目前沒有豆子可烘。")
    else:
        selected_bean = st.selectbox("選擇生豆", bean_list)
        roast_weight = st.number_input("投入生豆重 (kg)", min_value=0.0, step=0.1)
        
        if st.button("確認扣庫"):
            cursor.execute("SELECT id, stock_weight FROM beans WHERE name=?", (selected_bean,))
            bean_id, current_stock = cursor.fetchone()
            
            new_stock = current_stock - roast_weight
            
            # 警告但不阻止 (依需求可改)
            if new_stock < 0:
                st.warning(f"⚠️ 注意！庫存變為負數 ({new_stock} kg)")
            
            cursor.execute("UPDATE beans SET stock_weight=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_stock, bean_id))
            cursor.execute("INSERT INTO transactions (bean_id, action_type, amount_change, note) VALUES (?, ?, ?, ?)",
                           (bean_id, 'ROAST', -roast_weight, '烘豆消耗'))
            conn.commit()
            st.success(f"✅ 登記完成，{selected_bean} 剩餘庫存: {new_stock:.2f} kg")

# --- 功能 4: 盤點修正 ---
elif menu == "📝 盤點修正":
    st.title("📝 庫存盤點與修正")
    
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM beans ORDER BY name")
    bean_list = [row[0] for row in cursor.fetchall()]
    
    if bean_list:
        selected_bean = st.selectbox("選擇生豆", bean_list)
        
        # 顯示目前系統庫存
        cursor.execute("SELECT id, stock_weight FROM beans WHERE name=?", (selected_bean,))
        bean_id, current_stock = cursor.fetchone()
        st.info(f"💻 系統目前記錄: **{current_stock} kg**")
        
        actual_weight = st.number_input("⚖️ 實際盤點重量 (kg)", min_value=0.0, step=0.1, value=current_stock)
        
        if st.button("更新庫存數據"):
            diff = actual_weight - current_stock
            if diff == 0:
                st.toast("庫存無差異，未變更。")
            else:
                cursor.execute("UPDATE beans SET stock_weight=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (actual_weight, bean_id))
                cursor.execute("INSERT INTO transactions (bean_id, action_type, amount_change, note) VALUES (?, ?, ?, ?)",
                               (bean_id, 'STOCKTAKE', diff, f'盤點修正 ({current_stock}->{actual_weight})'))
                conn.commit()
                st.success(f"✅ 盤點完成，庫存已修正為 {actual_weight} kg")

# --- 功能 5: 異動紀錄 ---
elif menu == "📜 異動紀錄":
    st.title("📜 庫存異動紀錄")
    
    query = '''
        SELECT t.created_at as '時間', b.name as '豆名', t.action_type as '動作', t.amount_change as '變動量', t.note as '備註'
        FROM transactions t
        JOIN beans b ON t.bean_id = b.id
        ORDER BY t.created_at DESC
        LIMIT 100
    '''
    df_logs = pd.read_sql(query, conn)
    st.dataframe(df_logs, use_container_width=True)
