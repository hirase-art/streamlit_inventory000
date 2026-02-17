import streamlit as st
import pandas as pd

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム V2")

# --- 1. データベース接続 ---
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_master(table_name):
    return conn.query(f'SELECT * FROM "{table_name}";')

@st.cache_data(ttl=300)
def get_aggregated_shipments(period_type="monthly"):
    """キャスト(::date)を含んだ集計SQL"""
    if period_type == "monthly":
        query = """
        SELECT "商品ID", to_char("出荷確定日"::date, 'YYMM') as code, SUM("出荷数") as "qty"
        FROM shipment_all GROUP BY 1, 2 ORDER BY 2 DESC
        """
    else:
        query = """
        SELECT "商品ID", to_char(date_trunc('week', "出荷確定日"::date), 'YYMMDD') || 'w' as code, SUM("出荷数") as "qty"
        FROM shipment_all GROUP BY 1, 2 ORDER BY 2 DESC
        """
    return conn.query(query)

# データ取得
with st.spinner('データを同期中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    df_inv = load_master("在庫情報")
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# --- 2. サイドバー：シャープな検索機能 ---
st.sidebar.header("🔍 絞り込み条件")

# 2.1 単位切り替え
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'}).copy()

# 2.2 カテゴリ絞り込み (連動型)
dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)
if sel_dai != "すべて":
    df_m = df_m[df_m['大分類'] == sel_dai]

# 2.3 フリーワード検索
search_id = st.sidebar.text_input("商品ID (カンマ区切り可):")
search_name = st.sidebar.text_input("商品名キーワード:")

# 2.4 表示期間制限 (最新のN件)
show_limit = st.sidebar.slider("表示期間 (過去いくつ分表示するか):", 4, 24, 12)

# --- 3. ロジック関数：過去実績を可視化 ---
def display_analysis_table(df_ship, master, title):
    if df_ship.empty: return

    # マスタ結合
    res = pd.merge(master[['商品ID', '商品名', '大分類', '中分類']], df_ship, on='商品ID', how='inner')

    # フィルタ
    if search_id:
        ids = [i.strip().zfill(8) if i.strip().isdigit() else i.strip() for i in search_id.split(',')]
        res = res[res['商品ID'].isin(ids)]
    if search_name:
        res = res[res['商品名'].str.contains(search_name, na=False)]

    if res.empty:
        st.info(f"{title}: 該当なし")
        return

    # ピボット作成
    piv = res.pivot_table(index=["商品ID", "商品名", "大分類"], columns='code', values='qty', aggfunc='sum').fillna(0)
    
    # 最新順に並んでいるので、表示期間でカット
    piv = piv.iloc[:, :show_limit]
    
    # 過去トレンド列（Sparkline）の作成用データを準備
    piv["トレンド"] = piv.values.tolist()

    st.subheader(title)
    st.dataframe(
        piv,
        use_container_width=True,
        column_config={
            "トレンド": st.column_config.line_chart_column("過去トレンド", y_min=0),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 出荷実績（トレンド付）", "📦 在庫詳細"])

with tab1:
    display_analysis_table(df_m_ship, df_m, "🗓️ 月間出荷（最新順）")
    st.write("---")
    display_analysis_table(df_w_ship, df_m, "🗓️ 週間出荷（最新順）")

with tab2:
    st.subheader("現在の在庫状況")
    inv_display = pd.merge(df_m, df_inv, on='商品ID', how='inner')
    st.dataframe(inv_display, use_container_width=True)
