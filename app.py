import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import japanize_matplotlib

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷可視化システム")

# --------------------------------------------------------------------------
# 1. 接続 & データ取得 (Supabase)
# --------------------------------------------------------------------------
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_supabase(table):
    df = conn.query(f'SELECT * FROM "{table}";')
    # 文字列として扱うべき列の変換
    for col in ['商品ID', '倉庫ID', '業務区分ID', 'SET_ID', '品質区分ID']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('None', np.nan).replace('nan', np.nan)
    return df

@st.cache_data
def load_csv(path):
    try:
        return pd.read_csv(path, dtype={'商品ID': str, 'SET_ID': str})
    except:
        return pd.DataFrame()

# データ読み込み
with st.spinner('データを同期中...'):
    df_inv = load_supabase("在庫情報")   # 旧 CZ04003
    df_ship_w = load_supabase("T_9x07") # 旧 T_9x07
    df_ship_m = load_csv("T_9x30.csv")   # まだCSV
    df_pack = load_csv("PACK_Classification.csv")
    df_set = load_csv("SET_Class.csv")

# --------------------------------------------------------------------------
# 2. サイドバー：共通・出荷情報フィルタ
# --------------------------------------------------------------------------
st.sidebar.header(":blue[🚚 共通・出荷フィルタ]")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

# マスタの切り替え
df_m = df_pack.copy() if unit == "Pack" else df_set.copy().rename(columns={'SET_ID':'商品ID','セット構成名称':'商品名'})

# 基本データのマージ
ship_m_full = pd.merge(df_ship_m, df_m, on='商品ID', how='left') if not df_ship_m.empty else pd.DataFrame()
ship_w_full = pd.merge(df_ship_w, df_m, on='商品ID', how='left') if not df_ship_w.empty else pd.DataFrame()

# --- 検索・抽出機能の復活 ---
search_id = st.sidebar.text_input("🔍 商品ID検索 (完全一致):").strip()
search_name = st.sidebar.text_input("🔍 商品名検索 (曖昧):").strip()

if '大分類' in df_m.columns:
    sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m['大分類'].dropna().unique()))
    sel_chu = st.sidebar.multiselect("中分類:", options=sorted(df_m[df_m['大分類'].isin(sel_dai)]['中分類'].unique()) if sel_dai else [])
    sel_sho = st.sidebar.multiselect("小分類:", options=sorted(df_m[df_m['中分類'].isin(sel_chu)]['小分類'].unique()) if sel_chu else [])

# --------------------------------------------------------------------------
# 3. サイドバー：在庫情報フィルタ (復活！)
# --------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header(":orange[📦 在庫情報フィルタ]")
sel_souko = st.sidebar.multiselect("倉庫指定:", options=sorted(df_inv['倉庫ID'].unique()) if not df_inv.empty else [])
show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)

# --------------------------------------------------------------------------
# 4. データフィルタリング処理
# --------------------------------------------------------------------------
def apply_filter(df):
    if df.empty: return df
    tmp = df.copy()
    if search_id: tmp = tmp[tmp['商品ID'] == search_id]
    if search_name: tmp = tmp[tmp['商品名'].str.contains(search_name, na=False)]
    if '大分類' in tmp.columns and sel_dai: tmp = tmp[tmp['大分類'].isin(sel_dai)]
    if '中分類' in tmp.columns and sel_chu: tmp = tmp[tmp['中分類'].isin(sel_chu)]
    if '小分類' in tmp.columns and sel_sho: tmp = tmp[tmp['小分類'].isin(sel_sho)]
    return tmp

# 出荷データのフィルタ適用
ship_m_f = apply_filter(ship_m_full)
ship_w_f = apply_filter(ship_w_full)

# 在庫データのフィルタ適用（マスタ結合後）
inv_full = pd.merge(df_inv, df_pack, on='商品ID', how='left') if not df_inv.empty else pd.DataFrame()
inv_f = apply_filter(inv_full)
if sel_souko: inv_f = inv_f[inv_f['倉庫ID'].isin(sel_souko)]
if show_zero: inv_f = inv_f[inv_f['在庫数(引当数を含む)'] > 0]

# --------------------------------------------------------------------------
# 5. メイン表示部
# --------------------------------------------------------------------------
tab1, tab2 = st.tabs(["📝 出荷実績", "📊 在庫分析"])

with tab1:
    st.subheader("月間出荷実績 (ピボット)")
    if not ship_m_f.empty:
        piv = ship_m_f.pivot_table(index=['大分類','商品ID','商品名'], columns='month_code', values='合計出荷数', aggfunc='sum').fillna(0)
        st.dataframe(piv, use_container_width=True)
    else:
        st.info("条件に一致する出荷データがありません")

with tab2:
    st.subheader("現在の在庫状況")
    if not inv_f.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(inv_f[['倉庫ID','商品ID','商品名','在庫数(引当数を含む)','品質区分']].head(500))
        with col2:
            if '大分類' in inv_f.columns:
                stock_sum = inv_f.groupby('大分類')['在庫数(引当数を含む)'].sum()
                fig, ax = plt.subplots()
                ax.pie(stock_sum, labels=stock_sum.index, autopct='%1.1f%%', startangle=90)
                st.pyplot(fig)
