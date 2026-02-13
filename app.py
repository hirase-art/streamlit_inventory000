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
    # ID列は文字列に固定 (4 や 7 を確実に比較するため)
    for col in ['商品ID', '業務区分ID', '倉庫ID', 'SET_ID']:
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
# 2. タブ定義 (最初に行うことでサイドバーを動的に変える)
# --------------------------------------------------------------------------
tab_ship, tab_inv = st.tabs(["📝 出荷実績分析", "📊 在庫詳細分析"])

# --------------------------------------------------------------------------
# 3. サイドバー UI (タブの状態によって表示を切り替え)
# --------------------------------------------------------------------------
# 共通検索
st.sidebar.header("🔍 共通検索")
search_id = st.sidebar.text_input("商品ID検索:").strip()
search_name = st.sidebar.text_input("商品名検索:").strip()

# --- 出荷タブ用のサイドバー ---
# st.session_state や tab の変数で切り替えが難しいため、
# 共通項目として出しつつ、フィルタ関数側で「出荷のみ」「在庫のみ」に適用する
st.sidebar.markdown("---")
st.sidebar.header(":blue[🚚 出荷フィルタ]")
ship_type = st.sidebar.radio("出荷種別:", ["全て", "卸出荷 (4)", "通販出荷 (7)"], horizontal=True)

unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
df_m = df_pack.copy() if unit == "Pack" else df_set.copy().rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)

# 階層フィルタ
st.sidebar.markdown("---")
sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m['大分類'].dropna().unique()))
chu_opts = sorted(df_m[df_m['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else sorted(df_m['中分類'].dropna().unique())
sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)
sho_opts = sorted(df_m[df_m['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else sorted(df_m['小分類'].dropna().unique())
sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# --------------------------------------------------------------------------
# 4. 出荷実績タブ (ロジックと描画)
# --------------------------------------------------------------------------
with tab_ship:
    st.header("🚚 出荷実績分析")
    
    # フィルタ適用関数 (出荷専用)
    def apply_ship_filter(df, master):
        res = pd.merge(df, master[['商品ID', '大分類', '中分類', '小分類', '商品名']], on='商品ID', how='left', suffixes=('', '_m'))
        # 出荷種別フィルタ (業務区分ID 4 or 7)
        if ship_type == "卸出荷 (4)": res = res[res['業務区分ID'] == '4']
        elif ship_type == "通販出荷 (7)": res = res[res['業務区分ID'] == '7']
        # 共通検索・階層フィルタ
        if search_id: res = res[res['商品ID'] == search_id]
        if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
        if sel_dai: res = res[res['大分類'].isin(sel_dai)]
        if sel_chu: res = res[res['中分類'].isin(sel_chu)]
        if sel_sho: res = res[res['小分類'].isin(sel_sho)]
        return res

    ship_m_f = apply_ship_filter(df_ship_m, df_m)
    
    if not ship_m_f.empty:
        # ピボットテーブル作成
        idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        idx = idx[:["大分類", "中分類", "小分類", "商品ID"].index(agg_level) + 1]
        if agg_level == "商品ID": idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        
        piv = ship_m_f.pivot_table(index=idx, columns='month_code', values='合計出荷数', aggfunc='sum').fillna(0)
        
        if show_total == "あり":
            piv['合計'] = piv.sum(axis=1)
        st.dataframe(piv, use_container_width=True)
        
        # グラフ描画 (以前のシャープなスタイルを維持)
        chart_data = ship_m_f.pivot_table(index='month_code', columns=agg_level if agg_level != "商品ID" else "商品名", values='合計出荷数', aggfunc='sum').fillna(0).iloc[-12:]
        fig, ax = plt.subplots(figsize=(10, 4))
        chart_data.plot(kind='bar', stacked=True, ax=ax)
        ax.set_title(f"月間出荷推移 ({ship_type})")
        st.pyplot(fig)
    else:
        st.info("条件に一致する出荷データがありません。")

# --------------------------------------------------------------------------
# 5. 在庫分析タブ (ロジックと描画)
# --------------------------------------------------------------------------
with tab_inv:
    st.header("📦 在庫詳細分析")
    
    # 在庫専用サイドバー項目 (サイドバーの下部に追加される)
    st.sidebar.markdown("---")
    st.sidebar.header(":orange[📦 在庫専用設定]")
    sel_soko = st.sidebar.multiselect("倉庫絞り込み:", options=sorted(df_inv['倉庫名'].unique()) if '倉庫名' in df_inv.columns else [])
    show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)

    # フィルタ適用関数 (在庫専用)
    def apply_inv_filter(df, master):
        # 在庫は常にPackマスタで分類
        res = pd.merge(df, df_pack[['商品ID', '大分類', '中分類', '小分類', '商品名']], on='商品ID', how='left', suffixes=('', '_m'))
        # 共通検索・階層フィルタ (在庫には出荷種別フィルタはあえて適用しない)
        if search_id: res = res[res['商品ID'] == search_id]
        if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
        if sel_dai: res = res[res['大分類'].isin(sel_dai)]
        if sel_chu: res = res[res['中分類'].isin(sel_chu)]
        if sel_sho: res = res[res['小分類'].isin(sel_sho)]
        if sel_soko: res = res[res['倉庫名'].isin(sel_soko)]
        # 在庫数計算
        res['在庫数'] = pd.to_numeric(res['在庫数(引当数を含む)'], errors='coerce').fillna(0)
        if show_zero: res = res[res['在庫数'] > 0]
        return res

    inv_f = apply_inv_filter(df_inv, df_pack)

    if not inv_f.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(inv_f[['倉庫名', '商品ID', '商品名', '在庫数', '品質区分名', '大分類']], use_container_width=True)
        with col2:
            pie_data = inv_f.groupby('大分類')['在庫数'].sum()
            fig, ax = plt.subplots()
            ax.pie(pie_data, labels=pie_data.index, autopct='%1.1f%%')
            st.pyplot(fig)
    else:
        st.info("条件に一致する在庫データがありません。")
