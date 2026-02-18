import streamlit as st
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """列名から不要な記号を取り除き、商品IDの0を削って型を統一する"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
        # IDの先頭にある「0」をすべて削り、文字列として統一（結合ミスを防ぐ）
        df['商品ID'] = df['商品ID'].astype(str).str.lstrip('0')
    return df

@st.cache_data(ttl=600)
def load_master(table_name):
    df = conn.query(f'SELECT * FROM "{table_name}";')
    return clean_column_names(df)

@st.cache_data(ttl=300)
def get_aggregated_shipments(period_type="monthly"):
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
    df_inv = load_master("在庫情報")
    # PDFに基づき在庫列を強制設定 (13番目が在庫数)
    df_inv.columns = [
        '在庫日', '倉庫名', 'ブロックIP', 'ブロック名', 'ロケ', '商品ID', 'バーコード', 
        '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数', 
        '引当数', 'ロケ引当条件', 'ロケ業務区分', '取置取引先', '取置取引先名', '状況'
    ] + [f"col_{i}" for i in range(len(df_inv.columns) - 19)]
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

TARGET_COL = "在庫数"

# --- 2. サイドバー：フィルタ機能 ---
st.sidebar.header("🔍 絞り込み条件")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.copy()
    # SETIDかSET_IDか柔軟に対応
    id_col = 'SETID' if 'SETID' in df_m.columns else 'SET_ID'
    df_m = df_m.rename(columns={id_col: '商品ID', 'セット構成名称': '商品名'})

# IDの0を削って統一
df_m['商品ID'] = df_m['商品ID'].astype(str).str.lstrip('0')

# カテゴリ絞り込み
dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)
if sel_dai != "すべて":
    df_m = df_m[df_m['大分類'] == sel_dai]

# 検索入力
search_id = st.sidebar.text_input("商品ID (カンマ区切り可):", help="例: 2039, 2040")
search_name = st.sidebar.text_input("商品名キーワード:")
show_limit = st.sidebar.slider("表示期間 (過去いくつ分):", 4, 24, 12)
avg_period = st.sidebar.slider("予測期間 (直近何ヶ月/週):", 1, 6, 3)

# --- 3. 分析テーブル作成 ---
def display_analysis_table(df_ship, master, inv, title, period_label):
    if df_ship.empty: return
    
    # マスターのフィルタリング
    m_filtered = master.copy()
    if search_id:
        # 入力されたIDからも0を削って検索（100020 に 00100020 がヒットするようにする）
        ids = [i.strip().lstrip('0') for i in search_id.split(',')]
        m_filtered = m_filtered[m_filtered['商品ID'].isin(ids)]
    if search_name:
        m_filtered = m_filtered[m_filtered['商品名'].str.contains(search_name, na=False)]

    if m_filtered.empty:
        st.info(f"{title}: 検索条件に合う商品が見つかりません。")
        return

    # 実績と在庫を結合
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    res = pd.merge(m_filtered, inv[['商品ID', TARGET_COL]], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 予測計算
    recent_cols = piv.columns[:avg_period]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    res['残り期間'] = np.where(res['平均出荷'] > 0, (res[TARGET_COL] / res['平均出荷']).round(1), np.inf)

    # トレンドデータのリスト作成
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
            "トレンド": st.column_config.AreaChartColumn("出荷トレンド", y_min=0), # より安定した描画設定
            TARGET_COL: st.column_config.NumberColumn("実在庫", format="%d"),
            "残り期間": st.column_config.ProgressColumn(f"充足({period_label})", min_value=0, max_value=12, format="%.1f"),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 出荷実績・在庫予測", "📦 在庫詳細"])
with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv, "🗓️ 月次分析", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv, "🗓️ 週次分析", "週")
with tab2:
    st.dataframe(pd.merge(df_m, df_inv, on='商品ID', how='inner'), use_container_width=True)
