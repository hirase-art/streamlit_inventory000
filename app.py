import streamlit as st
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_master(table_name):
    return conn.query(f'SELECT * FROM "{table_name}";')

@st.cache_data(ttl=300)
def get_aggregated_shipments(period_type="monthly"):
    """SQL側で集計。::date キャスト付き"""
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

# データロード
with st.spinner('最新データを取得中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    df_inv = load_master("在庫情報")
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# --- 2. サイドバー：シャープなフィルタ機能 ---
st.sidebar.header("🔍 絞り込み条件")

# 2.1 単位切り替え
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'}).copy()

# 2.2 動的フィルタ (大分類 -> 中分類)
dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)

if sel_dai != "すべて":
    df_m = df_m[df_m['大分類'] == sel_dai]
    chu_list = ["すべて"] + sorted(df_m['中分類'].dropna().unique().tolist())
    sel_chu = st.sidebar.selectbox("中分類:", chu_list)
    if sel_chu != "すべて":
        df_m = df_m[df_m['中分類'] == sel_chu]

# 2.3 フリーワード・ID検索
st.sidebar.markdown("---")
search_id = st.sidebar.text_input("商品ID (カンマ区切り可):", placeholder="2039, 2040")
search_name = st.sidebar.text_input("商品名検索:")

# 2.4 表示・予測設定
show_limit = st.sidebar.slider("表示期間 (過去いくつ分):", 4, 24, 12)
avg_period = st.sidebar.slider("予測に使う期間 (直近何ヶ月/週):", 1, 6, 3)

# --- 3. ロジック関数：分析・予測テーブル作成 ---
def display_analysis_table(df_ship, master, inv, title, period_label):
    if df_ship.empty: return

    # 1. フィルタ適用 (マスターに対して)
    m_filtered = master.copy()
    if search_id:
        ids = [i.strip().zfill(8) if i.strip().isdigit() else i.strip() for i in search_id.split(',')]
        m_filtered = m_filtered[m_filtered['商品ID'].isin(ids)]
    if search_name:
        m_filtered = m_filtered[m_filtered['商品名'].str.contains(search_name, na=False)]
    
    if m_filtered.empty:
        st.info(f"{title}: 該当データがありません")
        return

    # 2. 出荷実績をピボット
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    
    # 3. マスターと在庫、出荷実績を統合
    res = pd.merge(m_filtered[['商品ID', '商品名', '大分類', '中分類']], inv[['商品ID', '実在庫']], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 4. 在庫切れ予測ロジック
    # 直近N期間の平均出荷を算出
    recent_cols = piv.columns[:avg_period]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    
    # 残り期間の計算 (0除算回避)
    res['残り期間'] = np.where(res['平均出荷'] > 0, (res['実在庫'] / res['平均出荷']).round(1), np.inf)

    # 5. トレンド用のリスト作成 (最新から過去へ並んでいるので反転させて時系列にする)
    trend_cols = piv.columns[:show_limit][::-1]
    res['トレンド'] = res[trend_cols].values.tolist()

    # 表示列の整理
    base_cols = ["大分類", "商品ID", "商品名", "実在庫", "平均出荷", "残り期間", "トレンド"]
    display_df = res[base_cols + list(piv.columns[:show_limit])]

    # 6. 表示 (column_config で見た目を整える)
    st.subheader(title)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "トレンド": st.column_config.line_chart_column("出荷推移", y_min=0),
            "実在庫": st.column_config.NumberColumn("在庫数", format="%d"),
            "平均出荷": st.column_config.NumberColumn(f"平均({avg_period}{period_label})"),
            "残り期間": st.column_config.ProgressColumn(
                f"在庫充足({period_label})", 
                help="現在の在庫が平均出荷ペースで何日/週もつか",
                min_value=0, max_value=12, format="%.1f"
            ),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 出荷実績・在庫予測", "📦 在庫明細"])

with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv, "🗓️ 月次分析 (Stockout予測付)", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv, "🗓️ 週次分析 (Stockout予測付)", "週")

with tab2:
    st.subheader("現在の全在庫リスト")
    st.dataframe(pd.merge(df_m, df_inv, on='商品ID', how='inner'), use_container_width=True)
