import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム Pro")

# --- 1. データベース接続 ---
conn = st.connection("postgresql", type="sql")

def clean_column_names(df):
    df.columns = df.columns.str.strip().str.replace('"', '').str.replace(' ', '')
    if '商品ID' in df.columns:
        df = df.dropna(subset=['商品ID'])
        df['商品ID'] = df['商品ID'].astype(str).str.replace(r'\.0$', '', regex=True).str.lstrip('0')
    return df

@st.cache_data(ttl=600)
def load_all_masters():
    """PackとSETを統合して一つのマスタとして扱う"""
    p = clean_column_names(conn.query('SELECT * FROM "Pack_Classification";'))
    s = clean_column_names(conn.query('SELECT * FROM "SET_Class";'))
    
    # SETマスタをPackの形式に合わせるマッピング
    s = s.rename(columns={
        'SETID': '商品ID', 'SET_ID': '商品ID', 
        'セット構成名称': '商品名'
    })
    # SETに分類がない場合の補填
    if '大分類' not in s.columns: s['大分類'] = 'SET'
    if '中分類' not in s.columns: s['中分類'] = 'セット商品'
    if '小分類' not in s.columns: s['小分類'] = '-'
    
    # 必要な列だけ抽出して結合
    cols = ['大分類', '中分類', '小分類', '商品ID', '商品名']
    # 共通の列だけを維持して縦積み
    combined = pd.concat([p[cols], s[cols]], ignore_index=True).drop_duplicates(subset=['商品ID'])
    return combined

@st.cache_data(ttl=300)
def get_shipment_summary(period_type="monthly"):
    table = "shipment_monthly" if period_type == "monthly" else "shipment_weekly"
    df = conn.query(f'SELECT * FROM "{table}";')
    return clean_column_names(df)

@st.cache_data(ttl=300)
def get_incoming_summary():
    query = 'SELECT "商品ID", SUM("予定数") as "入荷予定合計", MIN(to_date("入荷予定日"::text, \'YYYYMMDD\')) as "次回入荷日" FROM "T_4001" GROUP BY 1'
    df = conn.query(query)
    return clean_column_names(df)

# データロード
with st.spinner('データを同期中...'):
    df_m_ship_raw = get_shipment_summary("monthly")
    df_w_ship_raw = get_shipment_summary("weekly")
    df_incoming = get_incoming_summary()
    df_master_combined = load_all_masters()
    
    # 在庫集約
    df_inv_raw = clean_column_names(conn.query('SELECT * FROM "在庫情報";'))
    # (在庫カラム設定は以前のロジックを継承...)
    df_inv_raw.columns = ['在庫日', '倉庫ID', '倉庫名', 'ブロックID', 'ブロック名', 'ロケ', '商品ID', 'バーコード', '商品名', 'ロット', '有効期限', '品質区分ID', '品質区分名', '在庫数引当含', '引当数'] + [f"col_{i}" for i in range(len(df_inv_raw.columns) - 15)]
    df_inv_raw['利用可能'] = pd.to_numeric(df_inv_raw['在庫数引当含'], errors='coerce').fillna(0) - pd.to_numeric(df_inv_raw['引当数'], errors='coerce').fillna(0)
    df_inv_final = df_inv_raw[df_inv_raw['品質区分ID'].astype(str).isin(['1', '2'])].pivot_table(index='商品ID', columns='倉庫ID', values='利用可能', aggfunc='sum').fillna(0).rename(columns={'7': '大阪', '8': '千葉', 7: '大阪', 8: '千葉'}).reset_index()
    for c in ['大阪', '千葉']:
        if c not in df_inv_final.columns: df_inv_final[c] = 0
    df_inv_final['現在庫合計'] = df_inv_final['大阪'] + df_inv_final['千葉']

# --- 2. サイドバー：高度なフィルタ ---
st.sidebar.header("🔍 絞り込み条件")

# 倉庫フィルタ（全社対応）
sel_wh = st.sidebar.selectbox("出荷元倉庫:", ["全社", "7 (大阪)", "8 (千葉)"])

# 階層フィルタ（複数選択）
def multi_select_filter(df, col, label):
    options = sorted(df[col].dropna().unique().tolist())
    selected = st.sidebar.multiselect(label, options)
    return df[df[col].isin(selected)] if selected else df

df_f = df_master_combined.copy()
df_f = multi_select_filter(df_f, '大分類', "大分類")
df_f = multi_select_filter(df_f, '中分類', "中分類")
df_f = multi_select_filter(df_f, '小分類', "小分類")

st.sidebar.markdown("---")
# 判定ステータス（過多を追加）
all_status = ["⚠️間に合わない", "要発注", "入荷待ち", "安全", "📈過多", "動向なし"]
status_filter = st.sidebar.multiselect("判定ステータス:", all_status, default=all_status)

# 予測期間の個別設定
avg_n_month = st.sidebar.slider("月次予測平均 (nヶ月):", 1, 12, 3)
avg_n_week = st.sidebar.slider("週次予測平均 (n週):", 1, 12, 4)

# --- 3. 分析エンジン ---
def analyze_stock(df_ship_raw, master, inv, incoming, avg_n, period_label):
    # 倉庫フィルタ
    df_ship = df_ship_raw.copy()
    if sel_wh != "全社":
        df_ship = df_ship[df_ship['倉庫ID'] == sel_wh.split(" ")[0]]
    
    # 出荷実績ピボット (新→旧)
    piv = df_ship.pivot_table(index="商品ID", columns='code', values='出荷数', aggfunc='sum').fillna(0)
    piv_cols_desc = sorted(piv.columns, reverse=True)
    piv = piv[piv_cols_desc]

    # データ結合
    res = pd.merge(master, inv[['商品ID', '千葉', '大阪', '現在庫合計']], on='商品ID', how='inner')
    res = pd.merge(res, incoming[['商品ID', '入荷予定合計', '次回入荷日']], on='商品ID', how='left')
    res = pd.merge(res, piv, on='商品ID', how='left').fillna(0)

    # 充足計算
    res['平均出荷'] = res[piv_cols_desc[:avg_n]].mean(axis=1).round(1)
    res['現充足'] = np.where(res['平均出荷'] > 0, (res['現在庫合計'] / res['平均出荷']).round(1), np.inf)
    res['将充足'] = np.where(res['平均出荷'] > 0, ((res['現在庫合計'] + res['入荷予定合計'].fillna(0)) / res['平均出荷']).round(1), np.inf)
    
    # 判定ロジック強化
    days_per = 30 if period_label == "ヶ月" else 7
    res['在庫終了日数'] = np.where(res['平均出荷'] > 0, (res['現在庫合計'] / (res['平均出荷'] / days_per)), 999)
    res['入荷待ち日数'] = (pd.to_datetime(res['次回入荷日']) - datetime.now()).dt.days.fillna(0)

    def get_status(row):
        if row['平均出荷'] == 0 and row['現在庫合計'] == 0: return "動向なし"
        if row['現充足'] >= 3.0: return "📈過多" # 3ヶ月分以上は過多
        if row['現充足'] >= 1.0: return "安全"
        if row['入荷予定合計'] == 0: return "要発注"
        if row['在庫終了日数'] < row['入荷待ち日数']: return "⚠️間に合わない"
        return "入荷待ち"

    res['判定'] = res.apply(get_status, axis=1)
    
    # グラフ用データ (旧→新 に反転)
    chart_cols = piv_cols_desc[:12][::-1]
    res['トレンド'] = res[chart_cols].values.tolist()

    # 表示フィルタ
    res = res[res['判定'].isin(status_filter)]
    
    # カラム並び替え
    display_cols = ["判定", "大分類", "中分類", "小分類", "商品ID", "商品名", "現在庫合計", "現充足", "将充足", "トレンド"] + piv_cols_desc[:12]
    
    st.subheader(f"📊 {period_label}次分析 (予測期間: {avg_n}{period_label})")
    st.dataframe(
        res[display_cols],
        use_container_width=True, hide_index=True,
        column_config={
            "トレンド": st.column_config.AreaChartColumn("推移(旧→新)", y_min=0),
            "現充足": st.column_config.ProgressColumn("現充足", min_value=0, max_value=3, format="%.1f"),
            "将充足": st.column_config.ProgressColumn("将充足", min_value=0, max_value=3, format="%.1f")
        }
    )

# --- 4. 実行 ---
tab1, tab2 = st.tabs(["🚀 在庫適正化分析", "📦 拠点別在庫詳細"])
with tab1:
    analyze_stock(df_m_ship_raw, df_f, df_inv_final, df_incoming, avg_n_month, "ヶ月")
    st.write("---")
    analyze_stock(df_w_ship_raw, df_f, df_inv_final, df_incoming, avg_n_week, "週")
