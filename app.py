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
    # ID列は文字列に固定。前後の空白を削除
    str_cols = ['商品ID', '業務区分ID', '倉庫ID', 'SET_ID', '品質区分']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(['nan', 'None', ''], np.nan)
    return df

with st.spinner('最新データを同期中...'):
    df_inv = load_supabase("在庫情報")
    df_ship_m = load_supabase("T_9x30")
    df_ship_w = load_supabase("T_9x07")
    df_pack = load_supabase("Pack_Classification")
    df_set = load_supabase("SET_Class")

# --------------------------------------------------------------------------
# 2. 補助関数
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
# 3. サイドバー構成
# --------------------------------------------------------------------------
st.sidebar.header("🔍 共通検索")
# カンマ区切り対応ID検索
search_id_input = st.sidebar.text_input("商品ID検索 (カンマ区切りで複数可):", placeholder="例: 2039, 2040").strip()
search_name = st.sidebar.text_input("商品名検索 (あいまい):").strip()

# 出荷用サイドバー
st.sidebar.markdown("---")
st.sidebar.header(":blue[🚚 出荷フィルタ]")
ship_type = st.sidebar.radio("出荷種別:", ["全て", "卸出荷 (4)", "通販出荷 (7)"], horizontal=True)
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

# マスタ選択
df_m_source = df_pack if unit == "Pack" else df_set.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

agg_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)
num_months = st.sidebar.slider("月間表示期間", 3, 26, 12)
num_weeks = st.sidebar.slider("週間表示期間", 3, 20, 12)

# 分類連動フィルタ
sel_dai = st.sidebar.multiselect("大分類:", options=sorted(df_m_source['大分類'].dropna().unique()) if not df_m_source.empty else [])
chu_opts = sorted(df_m_source[df_m_source['大分類'].isin(sel_dai)]['中分類'].dropna().unique()) if sel_dai else sorted(df_m_source['中分類'].dropna().unique()) if not df_m_source.empty else []
sel_chu = st.sidebar.multiselect("中分類:", options=chu_opts)
sho_opts = sorted(df_m_source[df_m_source['中分類'].isin(sel_chu)]['小分類'].dropna().unique()) if sel_chu else sorted(df_m_source['小分類'].dropna().unique()) if not df_m_source.empty else []
sel_sho = st.sidebar.multiselect("小分類:", options=sho_opts)

# --------------------------------------------------------------------------
# 4. 共通フィルタロジック (桁数不一致対応版)
# --------------------------------------------------------------------------
def apply_filters(df, master):
    if df.empty: return df
    
    # マスタと結合。suffixesを使って商品名の重複を回避
    res = pd.merge(df, master[['商品ID', '大分類', '中分類', '小分類', '商品名']], on='商品ID', how='left', suffixes=('', '_m'))
    
    # マスタにない場合の補完（ピボットで消えるのを防ぐ）
    for col in ['大分類', '中分類', '小分類']:
        res[col] = res[col].fillna("(マスタ未登録)")
    if '商品名' in res.columns:
        res['商品名'] = res['商品名'].fillna(res['商品名_m']).fillna("(名称不明)")

    # ★ID検索のロジック強化
    if search_id_input:
        # 入力をリスト化
        raw_ids = [i.strip() for i in search_id_input.split(',') if i.strip()]
        # 前ゼロ埋め(6桁)したものも検索対象に加える
        padded_ids = [i.zfill(6) for i in raw_ids if i.isdigit()]
        target_ids = list(set(raw_ids + padded_ids))
        res = res[res['商品ID'].isin(target_ids)]
            
    if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]
    if sel_dai: res = res[res['大分類'].isin(sel_dai)]
    if sel_chu: res = res[res['中分類'].isin(sel_chu)]
    if sel_sho: res = res[res['小分類'].isin(sel_sho)]
    return res

# --------------------------------------------------------------------------
# 5. メイン画面
# --------------------------------------------------------------------------
tab_ship, tab_inv = st.tabs(["📝 出荷実績分析", "📊 在庫詳細分析"])

with tab_ship:
    st.header(f"🚚 出荷実績分析 ({ship_type})")
    
    def get_ship_pivot(target_df, code_col, period):
        f_df = apply_filters(target_df, df_m_source)
        # 業務区分フィルタ
        if ship_type == "卸出荷 (4)": f_df = f_df[f_df['業務区分ID'] == '4']
        elif ship_type == "通販出荷 (7)": f_df = f_df[f_df['業務区分ID'] == '7']
        
        if f_df.empty: return pd.DataFrame(), pd.DataFrame()
        
        # 集計インデックス決定
        idx_cols = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        current_idx = idx_cols[:["大分類", "中分類", "小分類", "商品ID"].index(agg_level) + 1]
        if agg_level == "商品ID": current_idx = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
        
        # ピボット作成。dropna=Falseで(マスタ未登録)を表示
        piv = f_df.pivot_table(index=current_idx, columns=code_col, values='合計出荷数', aggfunc='sum', dropna=False).fillna(0)
        piv = piv.iloc[:, -period:] # 指定期間のみ
        
        if show_total == "あり":
            piv['合計'] = piv.sum(axis=1)
            total_row = piv.sum().to_frame().T
            total_row.index = pd.MultiIndex.from_tuples([("合計",) * len(current_idx)])
            piv = pd.concat([piv, total_row])
        return piv, f_df

    # 月間推移
    st.subheader("🗓️ 月間推移")
    p_m, f_m = get_ship_pivot(df_ship_m, 'month_code', num_months)
    if not p_m.empty:
        c1, c2 = st.columns([3, 2])
        c1.dataframe(p_m, use_container_width=True)
        with c2:
            chart_col = agg_level if agg_level != "商品ID" else "商品名"
            c_df = f_m.pivot_table(index='month_code', columns=chart_col, values='合計出荷数', aggfunc='sum').fillna(0).iloc[-num_months:]
            fig = plt.figure(figsize=(10, 6)); gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
            ax = fig.add_subplot(gs[0]); c_df.plot(kind='bar', stacked=True, ax=ax, legend=False)
            add_labels_to_stacked_bar(ax, c_df)
            ax_leg = fig.add_subplot(gs[1]); ax_leg.axis('off')
            h, l = ax.get_legend_handles_labels(); ax_leg.legend(h, l, loc='center', ncol=3, fontsize=7)
            st.pyplot(fig)
    else:
        st.info("条件に一致する月間出荷データがありません。")

    # 週間推移 (確実に表示)
    st.markdown("---")
    st.subheader("🗓️ 週間推移")
    p_w, f_w = get_ship_pivot(df_ship_w, 'week_code', num_weeks)
    if not p_w.empty:
        st.dataframe(p_w, use_container_width=True)
    else:
        st.info("条件に一致する週間出荷データがありません。")

# 在庫タブ (フィルタの仕組みを共通化)
with tab_inv:
    st.header("📦 在庫詳細分析")
    inv_f = apply_filters(df_inv, df_pack)
    # 在庫専用フィルタ
    st.sidebar.markdown("---")
    st.sidebar.header(":orange[📦 在庫フィルタ]")
    sel_soko = st.sidebar.multiselect("倉庫絞り込み:", options=sorted(df_inv['倉庫名'].unique()) if '倉庫名' in df_inv.columns else [])
    show_zero = st.sidebar.checkbox("在庫0を表示しない", value=True)
    
    if sel_soko: inv_f = inv_f[inv_f['倉庫名'].isin(sel_soko)]
    inv_f['有効在庫'] = pd.to_numeric(inv_f['在庫数(引当数を含む)'], errors='coerce').fillna(0) - pd.to_numeric(inv_f['引当数'], errors='coerce').fillna(0)
    if show_zero: inv_f = inv_f[inv_f['有効在庫'] > 0]
    
    if not inv_f.empty:
        c1, c2 = st.columns([3, 2])
        c1.dataframe(inv_f[['倉庫名', '商品ID', '商品名', '有効在庫', '品質区分名', '大分類']], use_container_width=True)
        with c2:
            if '大分類' in inv_f.columns:
                pie = inv_f.groupby('大分類')['有効在庫'].sum()
                fig, ax = plt.subplots(); ax.pie(pie, labels=pie.index, autopct='%1.1f%%', startangle=90)
                st.pyplot(fig)
