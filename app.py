import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import japanize_matplotlib
import matplotlib.gridspec as gridspec

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷可視化システム")

# --------------------------------------------------------------------------
# 1. データ取得 (Supabase)
# --------------------------------------------------------------------------
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_supabase(table_name):
    try:
        query = f'SELECT * FROM "{table_name}";'
        df = conn.query(query)
        # ID列などは文字列として安全に扱う
        str_cols = ['商品ID', '業務区分ID', '倉庫ID', 'SET_ID', 'month_code', 'week_code']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().replace(['nan', 'None', ''], np.nan)
        return df
    except:
        return pd.DataFrame()

with st.spinner('最新データを同期中...'):
    df_inv = load_supabase("在庫情報")
    df_ship_m = load_supabase("T_9x30")
    df_ship_w = load_supabase("T_9x07")
    df_pack = load_supabase("Pack_Classification")
    df_set = load_supabase("SET_Class")

# --------------------------------------------------------------------------
# 2. 補助関数 (ラベル追加)
# --------------------------------------------------------------------------
def add_labels_to_stacked_bar(ax, data_df):
    bottom = pd.Series([0.0] * len(data_df), index=data_df.index)
    for col in data_df.columns:
        values = data_df[col].fillna(0)
        y_pos = bottom + values / 2
        for i, val in enumerate(values):
            if val > (data_df.sum(axis=1).max() * 0.05):
                ax.text(i, y_pos.iloc[i], f'{int(val)}', ha='center', va='center', fontsize=6, color='white', fontweight='bold')
        bottom += values

# --------------------------------------------------------------------------
# 3. 共通フィルタロジック (クラッシュ徹底ガード版)
# --------------------------------------------------------------------------
def apply_filters(df, master, s_id, s_name, dai, chu, sho):
    if df.empty: return df
    
    # マスタ結合 (suffixesを明示して列名の衝突を管理)
    m_sub = master[[c for c in ['商品ID', '大分類', '中分類', '小分類', '商品名'] if c in master.columns]].drop_duplicates(subset='商品ID')
    res = pd.merge(df, m_sub, on='商品ID', how='left', suffixes=('', '_master'))
    
    # 分類情報の安全な補完
    for col in ['大分類', '中分類', '小分類']:
        if col in res.columns:
            res[col] = res[col].fillna("(未登録)")
    
    # 商品名の補完 (KeyError対策)
    if '商品名' not in res.columns:
        if '商品名_master' in res.columns:
            res = res.rename(columns={'商品名_master': '商品名'})
        else:
            res['商品名'] = "(名称不明)"
    else:
        if '商品名_master' in res.columns:
            res['商品名'] = res['商品名'].fillna(res['商品名_master'])
        res['商品名'] = res['商品名'].fillna("(名称不明)")

    # 商品ID検索 (複数桁数パディング対応)
    if s_id:
        raw_ids = [i.strip() for i in s_id.split(',') if i.strip()]
        target_ids = set(raw_ids)
        for rid in raw_ids:
            if rid.isdigit():
                for length in range(1, 10): target_ids.add(rid.zfill(length))
        res = res[res['商品ID'].isin(list(target_ids))]
            
    if s_name: 
        res = res[res['商品名'].str.contains(s_name, na=False)]
    
    if dai: res = res[res['大分類'].isin(dai)]
    if chu: res = res[res['中分類'].isin(chu)]
    if sho: res = res[res['小分類'].isin(sho)]
    return res

# --------------------------------------------------------------------------
# 4. サイドバー
# --------------------------------------------------------------------------
st.sidebar.header("🔍 共通検索")
search_id = st.sidebar.text_input("商品ID検索 (カンマ区切り可):", placeholder="2039, 2040")
search_name = st.sidebar.text_input("商品名検索 (あいまい):")

st.sidebar.markdown("---")
st.sidebar.header(":blue[🚚 出荷フィルタ]")
ship_type = st.sidebar.radio("出荷種別:", ["全て", "卸出荷 (4)", "通販出荷 (7)"], horizontal=True)
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
df_m_source = df_pack if unit == "Pack" else df_set.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)
num_months = st.sidebar.slider("月間表示期間", 3, 26, 12)
num_weeks = st.sidebar.slider("週間表示期間", 3, 20, 12)

sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m_source['大分類'].dropna().unique()) if not df_m_source.empty else [])
chu_opts = sorted(df_m_source[df_m_source['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else []
sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)
sho_opts = sorted(df_m_source[df_m_source['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else []
sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# --------------------------------------------------------------------------
# 5. メイン表示
# --------------------------------------------------------------------------
tab_ship, tab_inv = st.tabs(["📝 出荷分析", "📊 在庫分析"])

with tab_ship:
    st.header(f"🚚 出荷実績分析 ({ship_type})")
    
    def get_ship_pivot(target_df, code_col, period):
        if target_df.empty: return pd.DataFrame()
        f_df = apply_filters(target_df, df_m_source, search_id, search_name, sel_dai, sel_chu, sel_sho)
        if ship_type == "卸出荷 (4)": f_df = f_df[f_df['業務区分ID'] == '4']
        elif ship_type == "通販出荷 (7)": f_df = f_df[f_df['業務区分ID'] == '7']
        if f_df.empty: return pd.DataFrame()
        
        idx_cols = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        current_idx = idx_cols[:idx_cols.index(agg_level if agg_level != "商品ID" else "商品ID") + 1]
        if agg_level == "商品ID": current_idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        
        try:
            piv = f_df.pivot_table(index=current_idx, columns=code_col, values='合計出荷数', aggfunc='sum', dropna=False).fillna(0)
            piv = piv.iloc[:, -period:]
            if show_total == "あり": piv['合計'] = piv.sum(axis=1)
            return piv
        except: return pd.DataFrame()

    st.subheader("🗓️ 月間推移")
    p_m = get_ship_pivot(df_ship_m, 'month_code', num_months)
    if not p_m.empty: st.dataframe(p_m, use_container_width=True)
    else: st.info("表示できる月間出荷データがありません。")

    st.markdown("---")
    st.subheader("🗓️ 週間推移")
    p_w = get_ship_pivot(df_ship_w, 'week_code', num_weeks)
    if not p_w.empty: st.dataframe(p_w, use_container_width=True)
    else: st.info("表示できる週間出荷データがありません。")

with tab_inv:
    st.header("📦 在庫詳細分析")
    inv_f = apply_filters(df_inv, df_pack, search_id, search_name, sel_dai, sel_chu, sel_sho)
    inv_f['有効在庫'] = pd.to_numeric(inv_f['在庫数(引当数を含む)'], errors='coerce').fillna(0) - pd.to_numeric(inv_f['引当数'], errors='coerce').fillna(0)
    
    st.dataframe(inv_f[['倉庫名', '商品ID', '商品名', '有効在庫', '品質区分名', '大分類']], use_container_width=True)
