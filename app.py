import streamlit as st
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """列名を整え、商品IDの型と0埋めを統一する"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
        # 先頭の0を消して文字列に統一。これで 00100020 と 100020 が確実に紐付きます
        df['商品ID'] = df['商品ID'].astype(str).str.lstrip('0')
    return df

@st.cache_data(ttl=600)
def load_master(table_name):
    df = conn.query(f'SELECT * FROM "{table_name}";')
    return clean_column_names(df)

@st.cache_data(ttl=300)
def get_aggregated_shipments(period_type="monthly"):
    """SQLで集計し、列名をクリーンにする"""
    if period_type == "monthly":
        query = 'SELECT "商品ID", to_char(NULLIF("出荷確定日", \'\')::date, \'YYMM\') as code, SUM("出荷数") as "qty" FROM "shipment_all" GROUP BY 1, 2'
    else:
        query = 'SELECT "商品ID", to_char(date_trunc(\'week\', NULLIF("出荷確定日", \'\')::date), \'YYMMDD\') || \'w\' as code, SUM("出荷数") as "qty" FROM "shipment_all" GROUP BY 1, 2'
    df = conn.query(query)
    return clean_column_names(df)

# データロード
with st.spinner('最新データを同期中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    
    # 在庫情報の読み込み（PDFのインデックスに基づき厳密に設定）
    df_inv_raw = load_master("在庫情報")
    # PDF に基づき、インデックス 6 を商品ID、インデックス 13 を在庫数に指定
    df_inv_raw.columns = [
        '在庫日', '倉庫名', 'ブロック名省略', 'ブロックIP', 'ブロック名', 'ロケ', '商品ID', # 6: 商品ID
        'バーコード', '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数' # 13: 在庫数
    ] + [f"col_{i}" for i in range(len(df_inv_raw.columns) - 14)]
    
    # 型と0削除の再適用
    df_inv = clean_column_names(df_inv_raw)
    
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

TARGET_COL = "在庫数"

# --- 2. サイドバー：フィルタ機能 ---
st.sidebar.header("🔍 絞り込み条件")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

if unit == "Pack":
    df_m = df_pack.copy()
else:
    # SETIDかSET_IDか柔軟に対応
    df_m = df_set.copy()
    id_col = 'SETID' if 'SETID' in df_m.columns else ('SET_ID' if 'SET_ID' in df_m.columns else '商品ID')
    df_m = df_m.rename(columns={id_col: '商品ID', 'セット構成名称': '商品名'})

# マスタのIDも0削除
df_m['商品ID'] = df_m['商品ID'].astype(str).str.lstrip('0')

# カテゴリ絞り込み
dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)
if sel_dai != "すべて":
    df_m = df_m[df_m['大分類'] == sel_dai]

search_id = st.sidebar.text_input("商品ID (カンマ区切り可):")
search_name = st.sidebar.text_input("商品名キーワード:")
show_limit = st.sidebar.slider("表示期間 (過去いくつ分):", 4, 24, 12)
avg_period = st.sidebar.slider("予測期間 (直近何ヶ月/週):", 1, 6, 3)

# --- 3. 分析テーブル作成 ---
def display_analysis_table(df_ship, master, inv, title, period_label):
    if df_ship.empty: return
    
    # フィルタリング
    m_filtered = master.copy()
    if search_id:
        ids = [i.strip().lstrip('0') for i in search_id.split(',')]
        m_filtered = m_filtered[m_filtered['商品ID'].isin(ids)]
    if search_name:
        m_filtered = m_filtered[m_filtered['商品名'].str.contains(search_name, na=False)]

    if m_filtered.empty:
        st.info(f"{title}: 該当なし")
        return

    # 実績ピボット（ここで最新順にソート）
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    # 【重要】列名を降順（最新が左）に並べ替え
    piv = piv[sorted(piv.columns, reverse=True)]
    
    # 結合
    res = pd.merge(m_filtered, inv[['商品ID', TARGET_COL]], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 予測
    recent_cols = piv.columns[:avg_period]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    res['残り期間'] = np.where(res['平均出荷'] > 0, (res[TARGET_COL] / res['平均出荷']).round(1), np.inf)

    # トレンド可視化 (スライサーの制限に合わせて反転)
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
            "トレンド": st.column_config.AreaChartColumn("出荷推移", y_min=0),
            TARGET_COL: st.column_config.NumberColumn("実在庫", format="%d"),
            "残り期間": st.column_config.ProgressColumn(f"充足({period_label})", min_value=0, max_value=12, format="%.1f"),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 実績・予測", "📦 在庫詳細"])
with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv, "🗓️ 月次分析", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv, "🗓️ 週次分析", "週")
with tab2:
    # 重複列を避けつつ在庫詳細を表示
    inv_details = pd.merge(df_m, df_inv, on='商品ID', how='inner', suffixes=('', '_inv'))
    st.dataframe(inv_details, use_container_width=True)
