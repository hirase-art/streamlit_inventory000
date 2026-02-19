import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """商品IDのクレンジング"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
        df = df.dropna(subset=['商品ID'])
        df['商品ID'] = df['商品ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.lstrip('0')
    return df

@st.cache_data(ttl=600)
def load_master(table_name):
    df = conn.query(f'SELECT * FROM "{table_name}";')
    return clean_column_names(df)

@st.cache_data(ttl=300)
def get_shipment_summary(period_type="monthly"):
    """【新設計】明細ではなく、集計済みテーブルを直接読み込む"""
    table = "shipment_monthly" if period_type == "monthly" else "shipment_weekly"
    df = conn.query(f'SELECT * FROM "{table}";')
    return clean_column_names(df)

@st.cache_data(ttl=300)
def get_incoming_summary():
    query = 'SELECT "商品ID", SUM("予定数") as "入荷予定合計", MIN(to_date("入荷予定日"::text, \'YYYYMMDD\')) as "次回入荷日" FROM "T_4001" GROUP BY 1'
    df = conn.query(query)
    return clean_column_names(df)

# データロード
with st.spinner('集計済みデータをロード中...'):
    df_m_ship_raw = get_shipment_summary("monthly")
    df_w_ship_raw = get_shipment_summary("weekly")
    df_incoming = get_incoming_summary()
    df_inv_raw = load_master("在庫情報")
    # (在庫情報のカラム定義は前回のものを継承)
    df_inv_raw.columns = ['在庫日', '倉庫ID', '倉庫名', 'ブロックID', 'ブロック名', 'ロケ', '商品ID', 'バーコード', '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数引当含', '引当数'] + [f"col_{i}" for i in range(len(df_inv_raw.columns) - 15)]
    df_inv_raw['利用可能在庫'] = pd.to_numeric(df_inv_raw['在庫数引当含'], errors='coerce').fillna(0) - pd.to_numeric(df_inv_raw['引当数'], errors='coerce').fillna(0)
    df_inv_final = clean_column_names(df_inv_raw[df_inv_raw['品質区分ID'].astype(str).isin(['1', '2'])]).pivot_table(index='商品ID', columns='倉庫ID', values='利用可能在庫', aggfunc='sum').fillna(0).rename(columns={'7': '大阪', '8': '千葉', 7: '大阪', 8: '千葉'}).reset_index()
    if '大阪' not in df_inv_final.columns: df_inv_final['大阪'] = 0
    if '千葉' not in df_inv_final.columns: df_inv_final['千葉'] = 0
    df_inv_final['現在庫合計'] = df_inv_final['大阪'] + df_inv_final['千葉']
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# --- 2. サイドバー：フィルタ ---
st.sidebar.header("🔍 絞り込み条件")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

# 【新設】倉庫と業務区分のフィルタ
wh_list = ["すべて", "7 (大阪)", "8 (千葉)"]
sel_wh = st.sidebar.selectbox("倉庫フィルタ:", wh_list)
biz_list = ["すべて"] + sorted(df_m_ship_raw['業務区分ID'].unique().tolist())
sel_biz = st.sidebar.selectbox("業務区分フィルタ:", biz_list)

if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.copy()
    id_col = 'SETID' if 'SETID' in df_m.columns else ('SET_ID' if 'SET_ID' in df_m.columns else '商品ID')
    df_m = df_m.rename(columns={id_col: '商品ID', 'セット構成名称': '商品名'})

df_m = clean_column_names(df_m)
dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)
if sel_dai != "すべて": df_m = df_m[df_m['大分類'] == sel_dai]

status_filter = st.sidebar.multiselect("判定ステータス:", ["⚠️間に合わない", "要発注", "入荷待ち", "安全", "動向なし"], default=["⚠️間に合わない", "要発注", "入荷待ち", "安全", "動向なし"])
hide_zeros = st.sidebar.toggle("現在庫・入荷予定ともにゼロを隠す", value=True)
search_id = st.sidebar.text_input("商品ID (カンマ区切り可):")
search_name = st.sidebar.text_input("商品名キーワード:")
show_limit = st.sidebar.slider("表示期間:", 4, 24, 12)
avg_period = st.sidebar.slider("予測期間:", 1, 6, 3)

# --- 3. 分析テーブル作成 ---
def display_analysis_table(df_ship_all, master, inv, incoming, title, period_label):
    # 3.1 倉庫・業務区分で出荷データをフィルタ
    df_ship = df_ship_all.copy()
    if sel_wh != "すべて":
        df_ship = df_ship[df_ship['倉庫ID'] == sel_wh.split(" ")[0]]
    if sel_biz != "すべて":
        df_ship = df_ship[df_ship['業務区分ID'] == sel_biz]
    
    if df_ship.empty:
        st.info(f"{title}: 指定の倉庫・業務区分に出荷データがありません。")
        return

    # 実績ピボット
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='出荷数', aggfunc='sum').fillna(0)
    piv = piv[sorted(piv.columns, reverse=True)]
    
    # 結合と計算
    res = pd.merge(master, inv[['商品ID', '千葉', '大阪', '現在庫合計']], on='商品ID', how='left').fillna(0)
    res = pd.merge(res, incoming[['商品ID', '入荷予定合計', '次回入荷日']], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    res['平均出荷'] = res[piv.columns[:avg_period]].mean(axis=1).round(1)
    res['現充足'] = np.where(res['平均出荷'] > 0, (res['現在庫合計'] / res['平均出荷']).round(1), np.inf)
    res['将充足'] = np.where(res['平均出荷'] > 0, ((res['現在庫合計'] + res['入荷予定合計'].fillna(0)) / res['平均出荷']).round(1), np.inf)
    
    days_per = 30 if period_label == "ヶ月" else 7
    res['在庫終了日数'] = np.where(res['平均出荷'] > 0, (res['現在庫合計'] / (res['平均出荷'] / days_per)), 999)
    res['入荷待ち日数'] = (pd.to_datetime(res['次回入荷日']) - datetime.now()).dt.days.fillna(0)
    
    def judge_risk(row):
        if row['平均出荷'] == 0 and row['現在庫合計'] == 0: return "動向なし"
        if row['現充足'] >= 1.2: return "安全"
        if row['入荷予定合計'] == 0: return "要発注"
        if row['在庫終了日数'] < row['入荷待ち日数']: return "⚠️間に合わない"
        return "入荷待ち"

    res['判定'] = res.apply(judge_risk, axis=1)

    # フィルタ適用
    if hide_zeros: res = res[(res['現在庫合計'] > 0) | (res['入荷予定合計'] > 0)]
    res = res[res['判定'].isin(status_filter)]
    if search_id: res = res[res['商品ID'].isin([i.strip().lstrip('0') for i in search_id.split(',')])]
    if search_name: res = res[res['商品名'].str.contains(search_name, na=False)]

    if res.empty: return

    res['トレンド'] = res[piv.columns[:show_limit][::-1]].values.tolist()
    base_cols = ["判定", "商品ID", "商品名", "千葉", "大阪", "現在庫合計", "現充足", "入荷予定合計", "将充足", "トレンド"]
    st.subheader(title)
    st.dataframe(res[base_cols + list(piv.columns[:show_limit])], use_container_width=True, hide_index=True, column_config={"トレンド": st.column_config.AreaChartColumn("推移", y_min=0), "現充足": st.column_config.ProgressColumn(f"現充足({period_label})", min_value=0, max_value=2, format="%.1f"), "将充足": st.column_config.ProgressColumn(f"将充足({period_label})", min_value=0, max_value=2, format="%.1f"), "商品ID": st.column_config.TextColumn("ID")})

# --- 4. 表示 ---
tab1, tab2 = st.tabs(["📊 実績・予測", "📦 在庫詳細"])
with tab1:
    display_analysis_table(df_m_ship_raw, df_m, df_inv_final, df_incoming, "🗓️ 月次分析", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship_raw, df_m, df_inv_final, df_incoming, "🗓️ 週次分析", "週")
with tab2:
    st.dataframe(pd.merge(df_m, df_inv_final, on='商品ID', how='inner'), use_container_width=True)
