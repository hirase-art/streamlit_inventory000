import streamlit as st
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """列名から不要な記号を取り除く関数"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    return df

@st.cache_data(ttl=600)
def load_master(table_name):
    df = conn.query(f'SELECT * FROM "{table_name}";')
    return clean_column_names(df)

@st.cache_data(ttl=300)
def get_aggregated_shipments(period_type="monthly"):
    """インデックスを効かせた高速集計クエリ"""
    if period_type == "monthly":
        query = 'SELECT "商品ID", to_char(NULLIF("出荷確定日", \'\')::date, \'YYMM\') as code, SUM("出荷数") as "qty" FROM "shipment_all" GROUP BY 1, 2'
    else:
        query = 'SELECT "商品ID", to_char(date_trunc(\'week\', NULLIF("出荷確定日", \'\')::date), \'YYMMDD\') || \'w\' as code, SUM("出荷数") as "qty" FROM "shipment_all" GROUP BY 1, 2'
    df = conn.query(query)
    return clean_column_names(df)

# データロード
with st.spinner('最新データを取得中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    
    # 在庫情報の読み込みとカラム名強制上書き（PDFの46番目 = 13番目の要素に対応）
    df_inv = load_master("在庫情報")
    df_inv.columns = [
        '在庫日', '倉庫名', 'ブロックIP', 'ブロック名', 'ロケ', '商品ID', 'バーコード', 
        '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数', # 13番目
        '引当数', 'ロケ引当条件', 'ロケ業務区分', '取置取引先', '取置取引先名', '状況'
    ] + [f"col_{i}" for i in range(len(df_inv.columns) - 19)]

    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# ★ここが重要：使用する列名を「在庫数」に統一
TARGET_COL = "在庫数"

# --- 2. サイドバー：フィルタ機能 ---
st.sidebar.header("🔍 絞り込み条件")

unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'}).copy()

dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)
if sel_dai != "すべて":
    df_m = df_m[df_m['大分類'] == sel_dai]

search_id = st.sidebar.text_input("商品ID (カンマ区切り可):", placeholder="2039, 2040")
search_name = st.sidebar.text_input("商品名検索:")
show_limit = st.sidebar.slider("表示期間 (過去いくつ分):", 4, 24, 12)
avg_period = st.sidebar.slider("予測に使う期間 (直近何ヶ月/週):", 1, 6, 3)

# --- 3. ロジック関数：分析・予測テーブル作成 ---
def display_analysis_table(df_ship, master, inv, title, period_label):
    if df_ship.empty: return
    m_filtered = master.copy()
    
    m_filtered['商品ID'] = m_filtered['商品ID'].astype(str)
    inv['商品ID'] = inv['商品ID'].astype(str)
    df_ship['商品ID'] = df_ship['商品ID'].astype(str)

    # 結合
    res = pd.merge(m_filtered, inv[['商品ID', TARGET_COL]], on='商品ID', how='left')
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 予測ロジック
    recent_cols = piv.columns[:avg_period]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    res['残り期間'] = np.where(res['平均出荷'] > 0, (res[TARGET_COL] / res['平均出荷']).round(1), np.inf)

    # トレンドデータ
    trend_cols = piv.columns[:show_limit][::-1]
    res['トレンド'] = res[trend_cols].values.tolist()

    # 表示列
    base_cols = ["大分類", "商品ID", "商品名", TARGET_COL, "平均出荷", "残り期間", "トレンド"]
    display_df = res[base_cols + list(piv.columns[:show_limit])]

    st.subheader(title)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "トレンド": st.column_config.line_chart_column("出荷推移", y_min=0),
            TARGET_COL: st.column_config.NumberColumn("在庫数", format="%d"),
            "残り期間": st.column_config.ProgressColumn(f"充足({period_label})", min_value=0, max_value=12, format="%.1f"),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 実績・予測", "📦 在庫明細"])
with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv, "🗓️ 月次分析", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv, "🗓️ 週次分析", "週")
with tab2:
    st.dataframe(pd.merge(df_m, df_inv, on='商品ID', how='inner'), use_container_width=True)
