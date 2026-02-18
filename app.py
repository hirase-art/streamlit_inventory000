import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 & キャッシュ ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    """列名を整え、商品IDを『完全な文字列』としてクレンジングする"""
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
        # IDがNoneやNaNの行を削除（ID=None対策）
        df = df.dropna(subset=['商品ID'])
        # 型変換：float経由の.0を防ぎつつ文字列化
        df['商品ID'] = df['商品ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.lstrip('0')
        # 空文字の行も削除
        df = df[df['商品ID'] != '']
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
    """T_4001の型変換エラーを防止した日付取得"""
    query = 'SELECT "商品ID", SUM("予定数") as "入荷予定合計", MIN(to_date("入荷予定日"::text, \'YYYYMMDD\')) as "次回入荷日" FROM "T_4001" GROUP BY 1'
    df = conn.query(query)
    return clean_column_names(df)

# データロード
with st.spinner('最新の在庫・入荷状況を計算中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    df_incoming = get_incoming_summary()
    
    df_inv_raw = load_master("在庫情報")
    df_inv_raw.columns = [
        '在庫日', '倉庫ID', '倉庫名', 'ブロックID', 'ブロック名', 'ロケ', '商品ID', 
        'バーコード', '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数引当含', '引当数'
    ] + [f"col_{i}" for i in range(len(df_inv_raw.columns) - 15)]
    
    df_inv_raw['在庫数引当含'] = pd.to_numeric(df_inv_raw['在庫数引当含'], errors='coerce').fillna(0)
    df_inv_raw['引当数'] = pd.to_numeric(df_inv_raw['引当数'], errors='coerce').fillna(0)
    df_inv_raw['利用可能在庫'] = df_inv_raw['在庫数引当含'] - df_inv_raw['引当数']
    
    df_inv_filtered = clean_column_names(df_inv_raw[df_inv_raw['品質区分ID'].astype(str).isin(['1', '2'])])
    
    inv_summary = df_inv_filtered.pivot_table(index='商品ID', columns='倉庫ID', values='利用可能在庫', aggfunc='sum').fillna(0)
    rename_map = {7: '大阪', 8: '千葉', '7': '大阪', '8': '千葉'}
    inv_summary = inv_summary.rename(columns=rename_map)
    for col in ['大阪', '千葉']:
        if col not in inv_summary.columns: inv_summary[col] = 0
            
    inv_summary['現在庫合計'] = inv_summary['大阪'] + inv_summary['千葉']
    df_inv_final = inv_summary.reset_index()
    
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# --- 2. サイドバー：シャープなフィルタ機能 ---
st.sidebar.header("🔍 絞り込み条件")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

if unit == "Pack":
    df_m = df_pack.copy()
else:
    df_m = df_set.copy()
    id_col = 'SETID' if 'SETID' in df_m.columns else ('SET_ID' if 'SET_ID' in df_m.columns else '商品ID')
    df_m = df_m.rename(columns={id_col: '商品ID', 'セット構成名称': '商品名'})

# マスタデータのクリーンアップ
df_m = clean_column_names(df_m)

# 2.1 大分類・中分類
dai_list = ["すべて"] + sorted(df_m['大分類'].dropna().unique().tolist())
sel_dai = st.sidebar.selectbox("大分類:", dai_list)
if sel_dai != "すべて":
    df_m = df_m[df_m['大分類'] == sel_dai]

# 2.2 状況（判定）による抽出
st.sidebar.markdown("---")
status_filter = st.sidebar.multiselect(
    "判定ステータスで絞り込み:",
    ["⚠️間に合わない", "要発注", "入荷待ち", "安全", "動向なし"],
    default=["⚠️間に合わない", "要発注", "入荷待ち", "安全", "動向なし"]
)

# 2.3 ゼロ在庫商品の非表示スイッチ
hide_zeros = st.sidebar.toggle("現在庫・入荷予定ともにゼロの商品を隠す", value=False)

# 2.4 キーワード検索
search_id = st.sidebar.text_input("商品ID (カンマ区切り可):")
search_name = st.sidebar.text_input("商品名キーワード:")
show_limit = st.sidebar.slider("表示期間 (最新から何件表示するか):", 4, 24, 12)

# --- 3. 分析テーブル作成 ---
def display_analysis_table(df_ship, master, inv, incoming, title, period_label):
    if df_ship.empty: return
    
    # 結合処理
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='qty', aggfunc='sum').fillna(0)
    piv = piv[sorted(piv.columns, reverse=True)]
    
    res = pd.merge(master, inv[['商品ID', '千葉', '大阪', '現在庫合計']], on='商品ID', how='left').fillna(0)
    res = pd.merge(res, incoming[['商品ID', '入荷予定合計', '次回入荷日']], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 充足計算
    recent_cols = piv.columns[:avg_period] if 'avg_period' in locals() else piv.columns[:3]
    res['平均出荷'] = res[recent_cols].mean(axis=1).round(1)
    res['現充足'] = np.where(res['平均出荷'] > 0, (res['現在庫合計'] / res['平均出荷']).round(1), np.inf)
    res['将充足'] = np.where(res['平均出荷'] > 0, ((res['現在庫合計'] + res['入荷予定合計'].fillna(0)) / res['平均出荷']).round(1), np.inf)

    # リスク判定
    days_per = 30 if period_label == "ヶ月" else 7
    res['在庫終了日数'] = np.where(res['平均出荷'] > 0, (res['現在庫合計'] / (res['平均出荷'] / days_per)), 999)
    res['次回入荷日'] = pd.to_datetime(res['次回入荷日'])
    res['入荷待ち日数'] = (res['次回入荷日'] - datetime.now()).dt.days.fillna(0)
    
    def judge_risk(row):
        if row['平均出荷'] == 0 and row['現在庫合計'] == 0: return "動向なし"
        if row['現充足'] >= 1.2: return "安全"
        if row['入荷予定合計'] == 0: return "要発注"
        if row['在庫終了日数'] < row['入荷待ち日数']: return "⚠️間に合わない"
        return "入荷待ち"

    res['判定'] = res.apply(judge_risk, axis=1)

    # --- 各種フィルタの適用 ---
    # A. ゼロ在庫非表示
    if hide_zeros:
        res = res[(res['現在庫合計'] > 0) | (res['入荷予定合計'] > 0)]
    
    # B. 判定ステータスフィルタ
    res = res[res['判定'].isin(status_filter)]
    
    # C. ID検索
    if search_id:
        ids = [i.strip().lstrip('0') for i in search_id.split(',')]
        res = res[res['商品ID'].isin(ids)]
    
    # D. 名称検索
    if search_name:
        res = res[res['商品名'].str.contains(search_name, na=False)]

    if res.empty:
        st.info(f"{title}: 条件に合致するデータがありません")
        return

    # トレンド可視化
    trend_cols = piv.columns[:show_limit][::-1]
    res['トレンド'] = res[trend_cols].values.tolist()

    # 表示
    base_cols = ["判定", "商品ID", "商品名", "千葉", "大阪", "現在庫合計", "現充足", "入荷予定合計", "将充足", "トレンド"]
    display_df = res[base_cols + list(piv.columns[:show_limit])]

    st.subheader(title)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "トレンド": st.column_config.AreaChartColumn("推移", y_min=0),
            "現充足": st.column_config.ProgressColumn(f"現充足({period_label})", min_value=0, max_value=2, format="%.1f"),
            "将充足": st.column_config.ProgressColumn(f"将充足({period_label})", min_value=0, max_value=2, format="%.1f"),
            "商品ID": st.column_config.TextColumn("ID"),
        }
    )

# --- 4. メイン表示 ---
avg_period = st.sidebar.slider("予測期間 (直近何ヶ月/週):", 1, 6, 3)
tab1, tab2 = st.tabs(["📊 出荷実績・在庫予測", "📦 在庫詳細"])
with tab1:
    display_analysis_table(df_m_ship, df_m, df_inv_final, df_incoming, "🗓️ 月次分析", "ヶ月")
    st.markdown("---")
    display_analysis_table(df_w_ship, df_m, df_inv_final, df_incoming, "🗓️ 週次分析", "週")
with tab2:
    st.dataframe(pd.merge(df_m, df_inv_final, on='商品ID', how='inner'), use_container_width=True)
