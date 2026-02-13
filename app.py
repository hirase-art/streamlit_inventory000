import streamlit as st
import pandas as pd
import logging
import glob
import matplotlib.pyplot as plt
import japanize_matplotlib
import numpy as np
import matplotlib.gridspec as gridspec

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',
    filemode='w'
)

st.title('📊 在庫・出荷データの可視化アプリ')

# --------------------------------------------------------------------------
# 1. Supabase 接続設定
# --------------------------------------------------------------------------
# デバッグ用：secretsが読み込めているか確認
if not st.secrets:
    st.warning("設定ファイルが見つかりません。'.streamlit/secrets.toml' または Streamlit Cloud の 'Secrets' 設定を確認してください。")

try:
    # st.connection を使ってデータベースに接続
    conn = st.connection("postgresql", type="sql")
except Exception as e:
    st.error(f"Supabaseへの接続に失敗しました: {e}")

# --------------------------------------------------------------------------
# 2. データ読み込み関数
# --------------------------------------------------------------------------

# ★ 新規追加: Supabaseからデータを読み込む関数
@st.cache_data(ttl=3600)
def load_data_from_supabase(table_name):
    """Supabaseのテーブルからデータを読み込み、型変換を行う関数"""
    logging.info(f"Supabase: {table_name} からの読み込み開始。")
    try:
        query = f'SELECT * FROM "{table_name}";'
        df = conn.query(query)
        
        # ID関連の列を文字列として読み込むように指定 (CSV読み込み時の仕様を継承)
        str_cols = ['商品ID', '倉庫ID', '業務区分ID', 'SET_ID']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('None', np.nan).replace('nan', np.nan)
        
        logging.info(f"Supabase: {table_name} の読み込みに成功しました。")
        return df
    except Exception as e:
        logging.error(f"Supabaseからの読み込みエラー: {e}")
        st.error(f"テーブル '{table_name}' の取得に失敗しました。")
        return pd.DataFrame()

@st.cache_data
def load_single_csv(path, encoding='utf-8'):
    """指定されたパスから単一のCSVファイルを読み込む関数"""
    # (既存の関数を維持)
    try:
        df = pd.read_csv(path, encoding=encoding, dtype={'商品ID': str, '倉庫ID': str, '業務区分ID': str, 'SET_ID': str})
        return df
    except Exception as e:
        return None

# (add_labels_to_stacked_bar などの補助関数は省略せずに維持してください)

try:
    # --- データの読み込み ---
    # 他のファイルはまだCSVから読み込む構成を維持（必要に応じて順次Supabaseへ移行可能）
    df1 = load_single_csv("T_9x30.csv", encoding='utf-8')
    df_pack_master = load_single_csv("PACK_Classification.csv", encoding='utf-8') 
    df_set_master = load_single_csv("SET_Class.csv", encoding='utf-8') 
    
    # ★ 改修ポイント: GitHub上のファイルではなく、Supabaseから読み込む
    # 今後は git push せずに、Google Driveに置くだけで更新されます
    df3 = load_data_from_supabase("在庫情報") 
    
    # T_9x07 もすでにSupabaseに同期されているので、こちらに切り替えることも可能です
    df5 = load_data_from_supabase("T_9x07")

    # (以降のフィルタリング、グラフ描画ロジックは一切変更なしで動きます)
