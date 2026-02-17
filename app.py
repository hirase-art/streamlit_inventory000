import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import japanize_matplotlib
import matplotlib.gridspec as gridspec

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム")

# --------------------------------------------------------------------------
# 1. データ取得 (Supabase)
# --------------------------------------------------------------------------
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_supabase(table_name):
    query = f'SELECT * FROM "{table_name}";'
    df = conn.query(query)
    # ID列は文字列に固定
    str_cols = ['商品ID', '業務区分ID', '倉庫ID', 'SET_ID', '品質区分']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace('nan', np.nan)
    return df

with st.spinner('最新データを取得中...'):
    df_inv = load_supabase("在庫情報")
    df_ship_m = load_supabase("T_9x30")
    df_ship_w = load_supabase("T_9x07")
    df_pack = load_supabase("Pack_Classification")
    df_set = load_supabase("SET_Class")

# --------------------------------------------------------------------------
# 2. 補助関数
# --------------------------------------------------------------------------
def add_labels_to_stacked_bar(ax, data_df):
    """積み上げ棒グラフに数値ラベルを追加"""
    bottom = pd.Series([0.0] * len(data_df), index=data_df.index)
    for col in data_df.columns:
        values = data_df[col].fillna(0)
        y_pos = bottom + values / 2
        for i, val in enumerate(values):
            if val > (data_df.sum(axis=1).max() * 0.05):
                ax.text(i, y_pos.iloc[i], f'{int(val)}', ha='center', va='center', fontsize=6, color='white', fontweight='bold')
        bottom += values

# --------------------------------------------------------------------------
# 3. サイドバー構成
# --------------------------------------------------------------------------
st.sidebar.header("🔍 共通検索")
# ★改修：カンマ区切りで複数IDをOR検索できるように修正
search_id_input = st.sidebar.text_input("商品ID検索 (カンマ区切りで複数可):", placeholder="例: 2039,2040,2041").strip()
search_name = st.sidebar.text_input("商品名検索 (あいまい):").strip()

# タブ定義
tab_ship, tab_inv = st.tabs(["📝 出荷実績分析", "📊 在庫詳細分析"])

# 出荷用サイドバー
st.sidebar.markdown("---")
st.sidebar.header(":blue[🚚 出荷フィルタ]")
ship_type = st.sidebar.radio("出荷種別:", ["全て", "卸出荷 (4)", "通販出荷 (7)"], horizontal=True)
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
df_m = df_pack.copy() if unit == "Pack" else df_set.copy().rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)

num_months = st.sidebar.slider("月間表示期間（ヶ月）", 3, 26, 12)
num_weeks = st.sidebar.slider("週間表示期間（週）", 3, 20, 12)

# 分類連動フィルタ
sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m['大分類'].dropna().unique()))
chu_opts = sorted(df_m[df_m['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else sorted(df_m['中分類'].dropna().unique())
sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)
sho_opts = sorted(df_m[df_m['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else sorted(df_m['小分類'].dropna().unique())
sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# 在庫用サイドバー
st.sidebar.markdown("---")
st.sidebar.header(":orange[📦 在庫フィルタ]")
sel_soko = st.sidebar.multiselect("倉庫絞り込み:", options=sorted(df_inv['倉庫名'].unique()) if '倉庫名' in df_inv.columns else [])
show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)

# --------------------------------------------------------------------------
# 4. 共通フィルタロジック (複数ID対応)
# --------------------------------------------------------------------------
def apply_filters(df, master):
    if df.empty: return df
    res = pd.merge(df, master[['商品ID', '大分類', '中分類', '小分類', '商品名']], on='商品ID', how='left', suffixes=('', '_m'))
    
    # ★複数ID検索のORロジック
    if search_id_input:
        id_list = [i.strip() for i in search_id_input.split(',') if i.strip()]
        if id_list:
            res = res[res['商品ID'].isin(id_list)]
            
    if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
    if sel_dai: res = res[res['大分類'].isin(sel_dai)]
    if sel_chu: res = res[res['中分類'].isin(sel_chu)]
    if sel_sho: res = res[res['小分類'].isin(sel_sho)]
    return res

# --------------------------------------------------------------------------
# 5. 出荷タブ
# --------------------------------------------------------------------------
with tab_ship:
    st.header(f"🚚 出荷実績分析 ({ship_type})")
    
    def get_ship_pivot(df, code_col, period):
        f_df = apply_filters(df, df_m)
        if ship_type == "卸出荷 (4)": f_df = f_df[f_df['業務区分ID'] == '4']
        elif ship_type == "通販出荷 (7)": f_df = f_df[f_df['業務区分ID'] == '7']
        if f_df.empty: return pd.DataFrame(), pd.DataFrame()
        
        idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        idx = idx[:["大分類", "中分類", "小分類", "商品ID"].index(agg_level) + 1]
        if agg_level == "商品ID": idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        
        piv = f_df.pivot_table(index=idx, columns=code_col, values='合計出荷数', aggfunc='sum').fillna(0).iloc[:, -period:]
        if show_total == "あり":
            piv['合計'] = piv.sum(axis=1)
            total_row = piv.sum().to_frame().T
            total_row.index = [("合計",) * len(idx)]
            piv = pd.concat([piv, total_row])
        return piv, f_df

    st.subheader("🗓️ 月間推移")
    p_m, f_m = get_ship_pivot(df_ship_m, 'month_code', num_months)
    if not p_m.empty:
        c_t, c_g = st.columns([3, 2])
