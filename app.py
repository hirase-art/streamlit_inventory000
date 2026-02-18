import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """列名を整え、商品IDの型と0埋めを統一する"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
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

@st.cache_data(ttl=300)
def get_incoming_summary():
    """T_4001から入荷予定数と、最も近い入荷予定日を取得"""
    query = 'SELECT "商品ID", SUM("予定数") as "入荷予定合計", MIN("入荷予定日"::date) as "次回入荷日" FROM "T_4001" GROUP BY 1'
    df = conn.query(query)
    return clean_column_names(df)

# データロード
with st.spinner('未来の在庫ギャップを計算中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    df_incoming = get_incoming_summary()
    
    # 在庫データの取得と集計
    df_inv_raw = load_master("在庫情報")
    df_inv_raw.columns = [
        '在庫日', '倉庫ID', '倉庫名', 'ブロックID', 'ブロック名', 'ロケ', '商品ID', 
        'バーコード', '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数引当含', '引当数'
    ] + [f"col_{i}" for i in range(len(df_inv_raw.columns) - 15)]
    
    df_inv_raw['在庫数引当含'] = pd.to_numeric(df_inv_raw['在庫数引当含'], errors='coerce').fillna(0)
    df_inv_raw['引当数'] = pd.to_numeric(df_inv_raw['引当数'], errors='coerce').fillna(0)
    df_inv_raw['利用可能在庫'] = df_inv_raw['在庫数引当含'] - df_inv_raw['引当数']
    df_inv_raw['商品ID'] = df_inv_raw['商品ID'].astype(str).str.lstrip('0')
    
    df_inv_filtered = df_inv_raw[df_inv_raw['品質区分ID'].astype(str).isin(['1', '2'])]
    
    inv_summary = df_inv_filtered.pivot_table(
        index='商品ID', columns='倉庫ID', values='利用可能在庫', aggfunc='sum'
    ).fillna(0)
    
    rename_map = {7: '大阪', 8: '千葉', '7': '大阪', '8': '千葉'}
    inv_summary = inv_summary.rename(columns=rename_map)
    for col in ['大阪', '千葉']:
        if col not in inv_summary.columns: inv_summary[col] = 0
            
    inv_summary['現在庫'] = inv_summary['大阪'] + inv_summary['千葉']
    df_inv_final = inv_summary.reset_index()
    
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

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
def display_analysis_table(df_ship, master, inv, incoming, title, period_label):
    if df_ship.empty: return
    
    m_filtered = master.copy()
    if search_id:
        ids = [i.strip().lstrip('0') for i in search_id.split(',')]
        m_filtered = m_filtered[m_filtered['商品ID'].isin(ids)]
    if search_name:
        m_filtered = m_filtered[m_filtered['商品名'].str.contains(search_name, na=False)]

    if m_filtered.empty:
        st.info(f"{title}: 該当なし")
        return

    # 実績ピボット
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    piv = piv[sorted(piv.columns, reverse=True)]
    
    # 結合
    res = pd.merge(m_filtered, inv[['商品ID', '千葉', '大阪', '現在庫']], on='商品ID', how='left').fillna(0)
    res = pd.merge(res, incoming[['商品ID', '入荷予定合計', '次回入荷日']], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 充足予測ロジック
    recent_cols = piv.columns[:avg_period]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    
    # 1. 現在充足
    res['現在充足'] = np.where(res['平均出荷'] > 0, (res['現在庫'] / res['平均出荷']).round(1), np.inf)
    
    # 2. 将来充足 (現在庫 + 入荷予定)
    res['予定込充足'] = np.where(res['平均出荷'] > 0, ((res['現在庫'] + res['入荷予定合計'].fillna(0)) / res['平均出荷']).round(1), np.inf)

    # 3. 欠品リスク判定 (魔の空白期間)
    # 現在庫が尽きるまでの日数
    res['在庫終了日数'] = np.where(res['平均出荷'] > 0, (res['現在庫'] / (res['平均出荷'] / (30 if period_label=="ヶ月" else 7))), 999)
    
    # 今日から次回入荷日までの日数
    res['次回入荷日'] = pd.to_datetime(res['次回入荷日'])
    res['入荷待ち日数'] = (res['次回入荷日'] - datetime.now()).dt.days.fillna(0)
    
    # 判定ロジック
    def judge_risk(row):
        if row['平均出荷'] == 0: return "安定"
        if row['現在充足'] >= 1.0: return "安全"
        if row['入荷予定合計'] == 0: return "要発注"
        if row['在庫終了日数'] < row['入荷待ち日数']: return "⚠️間に合わない"
        return "入荷待ち"

    res['判定'] = res.apply(judge_risk, axis=1)

    # トレンド可視化
    trend_cols = piv.columns[:show_limit][::-1]
    res['トレンド'] = res[trend_cols].values.tolist()

    # 表示列
    base_cols = [
        "判定", "商品ID", "商品名", "千葉", "大阪", "現在庫", 
        "現在充足", "入荷予定合計", "予定込充足", "トレンド"
    ]
    display_df = res[base_cols + list(piv.columns[:show_limit])]

    st.subheader(title)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "トレンド": st.column_config.AreaChartColumn("推移", y_min=0),
            "判定": st.column_config.TextColumn("状況"),
            "現在充足": st.column_config.ProgressColumn(f"現充足({period_label})", min_value=0, max_value=2, format="%.1f"),
            "予定込充足": st.column_config.ProgressColumn(f"将充足({period_label})", min_value=0, max_value=2, format="%.1f"),
            "入荷予定合計": st.column_config.NumberColumn("入荷予定"),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
tab1, tab2 = st.tabs(["📊 出荷実績・在庫予測", "📦 在庫詳細"])
with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv_final, df_incoming, "🗓️ 月次分析（欠品リスク検知版）", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv_final, df_incoming, "🗓️ 週次分析（欠品リスク検知版）", "週")
with tab2:
    inv_all = pd.merge(df_m, df_inv_final, on='商品ID', how='inner')
    inv_all = pd.merge(inv_all, df_incoming, on='商品ID', how='left').fillna(0)
    st.dataframe(inv_all, use_container_width=True)
