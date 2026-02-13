import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import japanize_matplotlib
import matplotlib.gridspec as gridspec
import logging

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム")

# --------------------------------------------------------------------------
# 1. Supabase 接続 & データ取得関数
# --------------------------------------------------------------------------
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_supabase(table_name):
    """Supabaseからデータを取得し、ID列などを文字列に固定する"""
    try:
        query = f'SELECT * FROM "{table_name}";'
        df = conn.query(query)
        str_cols = ['商品ID', '倉庫ID', '業務区分ID', 'SET_ID', '品質区分ID', 'month_code', 'week_code', '品質区分']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('None', np.nan).replace('nan', np.nan)
        return df
    except Exception as e:
        st.error(f"テーブル '{table_name}' の取得失敗: {e}")
        return pd.DataFrame()

# 全データを一括ロード
with st.spinner('Supabaseから最新データを同期中...'):
    df_inv    = load_supabase("在庫情報")
    df_ship_m = load_supabase("T_9x30")
    df_ship_w = load_supabase("T_9x07")
    df_pack   = load_supabase("Pack_Classification")
    df_set    = load_supabase("SET_Class")

# --------------------------------------------------------------------------
# 2. 補助関数 (グラフ用)
# --------------------------------------------------------------------------
def add_labels_to_stacked_bar(ax, data_df):
    """以前のアプリで使用していた、積み上げ棒グラフへの数値ラベル追加ロジック"""
    bottom = pd.Series([0.0] * len(data_df), index=data_df.index)
    for col in data_df.columns:
        values = data_df[col].fillna(0)
        y_pos = bottom + values / 2
        for i, val in enumerate(values):
            if val > (data_df.sum(axis=1).max() * 0.03): # 一定以上の大きさのみ表示
                ax.text(i, y_pos.iloc[i], f'{int(val)}', ha='center', va='center', fontsize=6, color='white', fontweight='bold')
        bottom += values

@st.cache_data
def convert_df(df):
    return df.to_csv(encoding='utf-8-sig').encode('utf-8-sig')

# --------------------------------------------------------------------------
# 3. サイドバー・共通フィルタ UI
# --------------------------------------------------------------------------
st.sidebar.header(":blue[🚚 出荷・検索フィルタ]")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
df_master = df_pack.copy() if unit == "Pack" else df_set.copy().rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

# 基本情報フィルタ
agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)

st.sidebar.markdown("---")
# 連動型分類フィルタ
daibun_opts = sorted(df_master['大分類'].dropna().unique())
sel_dai = st.sidebar.multiselect("大分類:", options=daibun_opts)

chu_opts = sorted(df_master[df_master['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else sorted(df_master['中分類'].dropna().unique())
sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)

sho_opts = sorted(df_master[df_master['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else sorted(df_master['小分類'].dropna().unique())
sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# 自由入力検索
search_id = st.sidebar.text_input("🔍 商品ID検索 (完全一致):").strip()
search_name = st.sidebar.text_input("🔍 商品名検索 (あいまい):").strip()

# 期間スライダー
num_months = st.sidebar.slider("月間表示期間（ヶ月）", min_value=3, max_value=26, value=12)
num_weeks = st.sidebar.slider("週間表示期間（週）", min_value=3, max_value=20, value=12)

# --------------------------------------------------------------------------
# 4. フィルタリングロジック
# --------------------------------------------------------------------------
def get_filtered_df(target_df, m_df):
    if target_df.empty: return target_df
    # マスタ結合
    res = pd.merge(target_df, m_df[['商品ID', '商品名', '大分類', '中分類', '小分類']], on='商品ID', how='left', suffixes=('', '_m'))
    # フィルタ適用
    if sel_dai: res = res[res['大分類'].isin(sel_dai)]
    if sel_chu: res = res[res['中分類'].isin(sel_chu)]
    if sel_sho: res = res[res['小分類'].isin(sel_sho)]
    if search_id: res = res[res['商品ID'] == search_id]
    if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
    return res

# --------------------------------------------------------------------------
# 5. メイン表示 (タブ構成)
# --------------------------------------------------------------------------
st.title('📊 在庫・出荷データの可視化アプリ')
tab_ship, tab_inv = st.tabs(["📝 出荷実績分析", "📊 在庫詳細分析"])

# --- タブ1: 出荷実績 ---
with tab_ship:
    # 月間出荷
    st.subheader(f"📅 月間出荷実績 (直近 {num_months} ヶ月)")
    m_f = get_filtered_df(df_ship_m, df_master)
    
    if not m_f.empty:
        idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        idx = idx[:["大分類", "中分類", "小分類", "商品ID"].index(agg_level) + 1]
        if agg_level == "商品ID": idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        
        pivot_m = m_f.pivot_table(index=idx, columns='month_code', values='合計出荷数', aggfunc='sum').fillna(0)
        display_m = pivot_m.iloc[:, -num_months:]
        
        if show_total == "あり":
            display_m['合計'] = display_m.sum(axis=1)
            total_row = display_m.sum().to_frame().T
            total_row.index = [("合計",) * len(idx)]
            display_m = pd.concat([display_m, total_row])

        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(display_m, use_container_width=True)
        with col2:
            chart_df = m_f.pivot_table(index='month_code', columns=agg_level if agg_level != "商品ID" else "商品名", values='合計出荷数', aggfunc='sum').fillna(0).iloc[-num_months:]
            if not chart_df.empty:
                fig = plt.figure(figsize=(10, 6))
                gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
                ax = fig.add_subplot(gs[0])
                ax.set_facecolor('#f0f0f0')
                chart_df.plot(kind='bar', stacked=True, ax=ax, legend=False)
                add_labels_to_stacked_bar(ax, chart_df)
                ax_leg = fig.add_subplot(gs[1]); ax_leg.axis('off')
                handles, labels = ax.get_legend_handles_labels()
                ax_leg.legend(handles, labels, loc='center', ncol=3, fontsize=7)
                st.pyplot(fig)

    # 週間出荷
    st.markdown("---")
    st.subheader(f"📅 週間出荷実績 (直近 {num_weeks} 週)")
    w_f = get_filtered_df(df_ship_w, df_master)
    if not w_f.empty:
        pivot_w = w_f.pivot_table(index=idx, columns='week_code', values='合計出荷数', aggfunc='sum').fillna(0)
        display_w = pivot_w.iloc[:, -num_weeks:]
        st.dataframe(display_w, use_container_width=True)

# --- タブ2: 在庫詳細 ---
with tab_inv:
    st.sidebar.markdown("---")
    st.sidebar.header(":orange[📦 在庫専用フィルタ]")
    sel_soko = st.sidebar.multiselect("倉庫絞り込み:", options=sorted(df_inv['倉庫名'].unique()) if '倉庫名' in df_inv.columns else [])
    show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)

    st.header("📦 在庫状況分析")
    inv_f = get_filtered_df(df_inv, df_pack) # 在庫はPackマスタ固定
    if sel_soko: inv_f = inv_f[inv_f['倉庫名'].isin(sel_soko)]
    if show_zero: inv_f = inv_f[inv_f['在庫数(引当数を含む)'].astype(float) > 0]

    if not inv_f.empty:
        col1, col2 = st.columns([3, 2])
        with col1:
            disp_cols = ['倉庫名', '商品ID', '商品名', '在庫数(引当数を含む)', '品質区分名', '大分類']
            st.dataframe(inv_f[[c for c in disp_cols if c in inv_f.columns]], use_container_width=True)
            st.download_button("在庫CSVをDL", data=convert_df(inv_f), file_name="inventory.csv")
        with col2:
            if '大分類' in inv_f.columns:
                stock_pie = inv_f.groupby('大分類')['在庫数(引当数を含む)'].sum()
                fig, ax = plt.subplots()
                ax.pie(stock_pie, labels=stock_pie.index, autopct='%1.1f%%', startangle=90)
                st.pyplot(fig)
    else:
        st.info("条件に一致する在庫データがありません。")

st.sidebar.success("✅ Supabaseデータ同期中")
