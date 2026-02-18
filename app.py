import streamlit as st
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """列名を整え、商品IDの型と0埋めを統一する共通関数"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
        # 先頭の0を消して文字列に統一。これで確実に紐付け可能にします
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
with st.spinner('データを最新の状態に更新中...'):
    # A. 出荷データの取得
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    
    # B. 在庫データの取得と集計
    df_inv_raw = load_master("在庫情報")
    # PDFの並び順に基づき列名を強制上書き
    df_inv_raw.columns = [
        '在庫日', '倉庫ID', '倉庫名', 'ブロックID', 'ブロック名', 'ロケ', '商品ID', 
        'バーコード', '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数'
    ] + [f"col_{i}" for i in range(len(df_inv_raw.columns) - 14)]
    
    # 型変換（数値化）
    df_inv_raw['在庫数'] = pd.to_numeric(df_inv_raw['在庫数'], errors='coerce').fillna(0)
    df_inv_raw['商品ID'] = df_inv_raw['商品ID'].astype(str).str.lstrip('0')
    
    # 【重要】品質区分 1, 2 のみを対象にする
    df_inv_filtered = df_inv_raw[df_inv_raw['品質区分ID'].astype(str).isin(['1', '2'])]
    
    # 【重要】商品ID単位で倉庫別（千葉:8, 大阪:7）に集計
    # pivot_tableで倉庫別の在庫列を自動生成
    inv_summary = df_inv_filtered.pivot_table(
        index='商品ID',
        columns='倉庫ID',
        values='在庫数',
        aggfunc='sum'
    ).fillna(0)
    
    # 列名を分かりやすくリネーム（存在しない列があれば0で作成）
    inv_summary = inv_summary.rename(columns={'7': '大阪在庫', '8': '千葉在庫'})
    if '大阪在庫' not in inv_summary.columns: inv_summary['大阪在庫'] = 0
    if '千葉在庫' not in inv_summary.columns: inv_summary['千葉在庫'] = 0
    
    # 合計列を作成
    inv_summary['実在庫合計'] = inv_summary['大阪在庫'] + inv_summary['千葉在庫']
    df_inv_final = inv_summary.reset_index()
    
    # C. マスタデータの取得
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# 充足計算に使うメイン列
TARGET_COL = "実在庫合計"

# --- 2. サイドバー：フィルタ機能 ---
st.sidebar.header("🔍 絞り込み条件")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.copy()
    id_col = 'SETID' if 'SETID' in df_m.columns else ('SET_ID' if 'SET_ID' in df_m.columns else '商品ID')
    df_m = df_m.rename(columns={id_col: '商品ID', 'セット構成名称': '商品名'})

df_m['商品ID'] = df_m['商品ID'].astype(str).str.lstrip('0')

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
    
    # 検索フィルタリング
    m_filtered = master.copy()
    if search_id:
        ids = [i.strip().lstrip('0') for i in search_id.split(',')]
        m_filtered = m_filtered[m_filtered['商品ID'].isin(ids)]
    if search_name:
        m_filtered = m_filtered[m_filtered['商品名'].str.contains(search_name, na=False)]

    if m_filtered.empty:
        st.info(f"{title}: 該当なし")
        return

    # 実績ピボット（最新順）
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    piv = piv[sorted(piv.columns, reverse=True)]
    
    # 結合（集約済みの在庫データを使用）
    res = pd.merge(m_filtered, inv[['商品ID', '千葉在庫', '大阪在庫', '実在庫合計']], on='商品ID', how='left').fillna(0)
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 充足予測
    recent_cols = piv.columns[:avg_period]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    res['残り期間'] = np.where(res['平均出荷'] > 0, (res['実在庫合計'] / res['平均出荷']).round(1), np.inf)

    # トレンド可視化用
    trend_cols = piv.columns[:show_limit][::-1]
    res['トレンド'] = res[trend_cols].values.tolist()

    # 表示列
    base_cols = ["大分類", "商品ID", "商品名", "千葉在庫", "大阪在庫", "実在庫合計", "平均出荷", "残り期間", "トレンド"]
    display_df = res[base_cols + list(piv.columns[:show_limit])]

    st.subheader(title)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "トレンド": st.column_config.AreaChartColumn("出荷推移", y_min=0),
            "千葉在庫": st.column_config.NumberColumn("千葉良品", format="%d"),
            "大阪在庫": st.column_config.NumberColumn("大阪良品", format="%d"),
            "実在庫合計": st.column_config.NumberColumn("良品合計", format="%d"),
            "残り期間": st.column_config.ProgressColumn(f"充足({period_label})", min_value=0, max_value=12, format="%.1f"),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 出荷実績・在庫予測", "📦 在庫詳細"])
with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv_final, "🗓️ 月次分析", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv_final, "🗓️ 週次分析", "週")
with tab2:
    # 詳細タブも集計済みデータで見やすく表示
    st.subheader("商品別の良品在庫サマリ")
    st.dataframe(pd.merge(df_m, df_inv_final, on='商品ID', how='inner'), use_container_width=True)
