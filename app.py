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
    # ID列は文字列に固定 (比較精度のため)
    str_cols = ['商品ID', '業務区分ID', '倉庫ID', 'SET_ID']
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
# 2. 補助関数 (グラフ・CSV)
# --------------------------------------------------------------------------
def add_labels_to_stacked_bar(ax, data_df):
    """積み上げ棒グラフに数値ラベルを追加 (以前のロジック復旧)"""
    bottom = pd.Series([0.0] * len(data_df), index=data_df.index)
    for col in data_df.columns:
        values = data_df[col].fillna(0)
        y_pos = bottom + values / 2
        for i, val in enumerate(values):
            if val > (data_df.sum(axis=1).max() * 0.05): # 5%以上の厚みがある場合のみ表示
                ax.text(i, y_pos.iloc[i], f'{int(val)}', ha='center', va='center', fontsize=6, color='white', fontweight='bold')
        bottom += values

@st.cache_data
def convert_df(df):
    return df.to_csv(encoding='utf-8-sig').encode('utf-8-sig')

# --------------------------------------------------------------------------
# 3. サイドバー構成 (出荷・在庫の独立性を維持)
# --------------------------------------------------------------------------
# A. 共通検索
st.sidebar.header("🔍 共通検索")
search_id = st.sidebar.text_input("商品ID検索:").strip()
search_name = st.sidebar.text_input("商品名検索:").strip()

# B. 出荷フィルタ
st.sidebar.markdown("---")
st.sidebar.header(":blue[🚚 出荷フィルタ]")
ship_type = st.sidebar.radio("出荷種別:", ["全て", "卸出荷 (4)", "通販出荷 (7)"], horizontal=True) # ご要望の卸・通販ラジオ
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
df_m = df_pack.copy() if unit == "Pack" else df_set.copy().rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)

# 期間スライダーの復旧
num_months = st.sidebar.slider("月間表示期間（ヶ月）", 3, 26, 12)
num_weeks = st.sidebar.slider("週間表示期間（週）", 3, 50, 12)

# 分類連動フィルタ
sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m['大分類'].dropna().unique()))
chu_opts = sorted(df_m[df_m['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else sorted(df_m['中分類'].dropna().unique())
sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)
sho_opts = sorted(df_m[df_m['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else sorted(df_m['小分類'].dropna().unique())
sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# C. 在庫フィルタ (下部に独立して配置)
st.sidebar.markdown("---")
st.sidebar.header(":orange[📦 在庫フィルタ]")
sel_soko = st.sidebar.multiselect("倉庫絞り込み:", options=sorted(df_inv['倉庫名'].unique()) if '倉庫名' in df_inv.columns else [])
show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)

# --------------------------------------------------------------------------
# 4. 共通フィルタ関数
# --------------------------------------------------------------------------
def apply_common_filters(df, master):
    if df.empty: return df
    res = pd.merge(df, master[['商品ID', '大分類', '中分類', '小分類', '商品名']], on='商品ID', how='left', suffixes=('', '_m'))
    if search_id: res = res[res['商品ID'] == search_id]
    if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
    if sel_dai: res = res[res['大分類'].isin(sel_dai)]
    if sel_chu: res = res[res['中分類'].isin(sel_chu)]
    if sel_sho: res = res[res['小分類'].isin(sel_sho)]
    return res

# --------------------------------------------------------------------------
# 5. メイン画面
# --------------------------------------------------------------------------
tab_ship, tab_inv = st.tabs(["📝 出荷分析", "📊 在庫分析"])

# --- 出荷タブ ---
with tab_ship:
    st.header(f"🚚 出荷実績分析 ({ship_type})")
    
    def process_shipping(df, code_col, period):
        f_df = apply_common_filters(df, df_m)
        # 出荷種別フィルタ (業務区分ID 4=卸, 7=通販)
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

    # 月間表示
    st.subheader("📅 月間推移")
    piv_m, f_m = process_shipping(df_ship_m, 'month_code', num_months)
    if not piv_m.empty:
        col_t, col_g = st.columns([3, 2])
        col_t.dataframe(piv_m, use_container_width=True)
        with col_g:
            chart_df = f_m.pivot_table(index='month_code', columns=agg_level if agg_level != "商品ID" else "商品名", values='合計出荷数', aggfunc='sum').fillna(0).iloc[-num_months:]
            fig = plt.figure(figsize=(10, 6))
            gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1]) # 凡例分離
            ax = fig.add_subplot(gs[0])
            chart_df.plot(kind='bar', stacked=True, ax=ax, legend=False)
            add_labels_to_stacked_bar(ax, chart_df)
            ax_leg = fig.add_subplot(gs[1]); ax_leg.axis('off')
            h, l = ax.get_legend_handles_labels()
            ax_leg.legend(h, l, loc='center', ncol=3, fontsize=7)
            st.pyplot(fig)

    # 週間表示の復旧
    st.markdown("---")
    st.subheader("📅 週間推移")
    piv_w, f_w = process_shipping(df_ship_w, 'week_code', num_weeks)
    if not piv_w.empty:
        st.dataframe(piv_w, use_container_width=True)

# --- 在庫タブ ---
with tab_inv:
    st.header("📦 在庫詳細分析")
    inv_f = apply_common_filters(df_inv, df_pack) # 在庫はPackマスタ基準
    if sel_soko: inv_f = inv_f[inv_f['倉庫名'].isin(sel_soko)]
    inv_f['在庫数'] = pd.to_numeric(inv_f['在庫数(引当数を含む)'], errors='coerce').fillna(0)
    if show_zero: inv_f = inv_f[inv_f['在庫数'] > 0]
    
    if not inv_f.empty:
        c1, c2 = st.columns([3, 2])
        c1.dataframe(inv_f[['倉庫名', '商品ID', '商品名', '在庫数', '品質区分名', '大分類']], use_container_width=True)
        with c2:
            pie_data = inv_f.groupby('大分類')['在庫数'].sum()
            fig, ax = plt.subplots()
            ax.pie(pie_data, labels=pie_data.index, autopct='%1.1f%%', startangle=90)
            st.pyplot(fig)

