import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import japanize_matplotlib
import matplotlib.gridspec as gridspec
import logging

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷可視化システム")

# --------------------------------------------------------------------------
# 1. Supabase 接続 & データ取得
# --------------------------------------------------------------------------
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_supabase(table_name):
    """Supabaseからデータを取得し、ID列を文字列に固定する"""
    try:
        query = f'SELECT * FROM "{table_name}";'
        df = conn.query(query)
        # ID関連の列を文字列に変換
        str_cols = ['商品ID', '倉庫ID', '業務区分ID', 'SET_ID', '品質区分ID', 'month_code', 'week_code']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('None', np.nan).replace('nan', np.nan)
        return df
    except Exception as e:
        st.error(f"テーブル '{table_name}' の取得に失敗しました: {e}")
        return pd.DataFrame()

# 全データをSupabaseから一気にロード
with st.spinner('Supabaseから最新データを同期中...'):
    df_inv   = load_supabase("在庫情報")            # 在庫
    df_ship_m = load_supabase("T_9x30")            # 月間出荷
    df_ship_w = load_supabase("T_9x07")            # 週間出荷
    df_pack  = load_supabase("Pack_Classification") # マスタ
    df_set   = load_supabase("SET_Class")           # セットマスタ

# --------------------------------------------------------------------------
# 2. サイドバー：共通フィルタロジック (シャープなUIの復活)
# --------------------------------------------------------------------------
st.sidebar.header(":blue[🚚 共通出荷・検索フィルタ]")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

# マスタの切り替えと整形
if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.copy().rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

# 検索機能 (曖昧検索・ID検索)
search_id = st.sidebar.text_input("🔍 商品ID検索 (完全一致):").strip()
search_name = st.sidebar.text_input("🔍 商品名検索 (あいまい):").strip()

# 大・中・小分類の連動フィルタ
if not df_m.empty:
    st.sidebar.markdown("---")
    agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
    
    sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m['大分類'].dropna().unique()))
    
    # 大分類が選ばれたら中分類を絞り込む
    chu_opts = sorted(df_m[df_m['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else sorted(df_m['中分類'].dropna().unique())
    sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)
    
    # 中分類が選ばれたら小分類を絞り込む
    sho_opts = sorted(df_m[df_m['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else sorted(df_m['小分類'].dropna().unique())
    sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# --------------------------------------------------------------------------
# 3. フィルタ適用関数
# --------------------------------------------------------------------------
def apply_filters(df, master_df):
    if df.empty: return df
    # マスタと結合して分類情報を付与
    res = pd.merge(df, master_df[['商品ID', '商品名', '大分類', '中分類', '小分類']], on='商品ID', how='left', suffixes=('', '_m'))
    
    # フィルタ条件の適用
    if search_id: res = res[res['商品ID'] == search_id]
    if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
    if sel_dai: res = res[res['大分類'].isin(sel_dai)]
    if sel_chu: res = res[res['中分類'].isin(sel_chu)]
    if sel_sho: res = res[res['小分類'].isin(sel_sho)]
    return res

# --------------------------------------------------------------------------
# 4. タブ表示部
# --------------------------------------------------------------------------
tab_ship, tab_inv = st.tabs(["📝 出荷情報分析", "📊 在庫詳細分析"])

with tab_ship:
    st.header("🚚 出荷実績分析")
    ship_f = apply_filters(df_ship_m, df_m)
    
    if not ship_f.empty:
        # 集計粒度に応じたピボット
        idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        if agg_level == "大分類": idx = ["大分類"]
        elif agg_level == "中分類": idx = ["大分類", "中分類"]
        elif agg_level == "小分類": idx = ["大分類", "中分類", "小分類"]
        
        pivot = ship_f.pivot_table(index=idx, columns='month_code', values='合計出荷数', aggfunc='sum').fillna(0)
        st.subheader(f"月間出荷ピボット ({agg_level}単位)")
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("条件に一致する出荷データがありません。")

with tab_inv:
    st.header("📦 在庫状況分析")
    # 在庫フィルタ設定
    st.sidebar.markdown("---")
    st.sidebar.header(":orange[在庫専用設定]")
    show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)
    
    inv_f = apply_filters(df_inv, df_pack) # 在庫は常にPackマスタ基準
    if show_zero: inv_f = inv_f[inv_f['在庫数(引当数を含む)'].astype(float) > 0]
    
    if not inv_f.empty:
        col1, col2 = st.columns([3, 2])
        with col1:
            st.subheader("在庫一覧")
            display_cols = ['倉庫名', '商品ID', '商品名', '在庫数(引当数を含む)', '品質区分名', '大分類']
            st.dataframe(inv_f[[c for c in display_cols if c in inv_f.columns]], use_container_width=True)
        
        with col2:
            st.subheader("在庫構成比")
            if '大分類' in inv_f.columns:
                pie_data = inv_f.groupby('大分類')['在庫数(引当数を含む)'].sum()
                fig, ax = plt.subplots()
                ax.pie(pie_data, labels=pie_data.index, autopct='%1.1f%%', startangle=90)
                st.pyplot(fig)
    else:
        st.info("条件に一致する在庫データがありません。")

st.sidebar.success("✅ Supabase同期完了")
