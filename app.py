import streamlit as st
import pandas as pd
import logging
import glob # ★ ワイルドカードを扱うためにglobをインポート
import matplotlib.pyplot as plt # ★ グラフ作成のためにpyplotをインポート
import japanize_matplotlib # 日本語文字化け対策
import numpy as np # ★ 数値計算のためにnumpyをインポート
import matplotlib.gridspec as gridspec

st.write(st.secrets) # secretsが読み込めていれば、中身が表示されます

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',
    filemode='w'
)

logging.info("--- アプリケーション開始 ---")
# --------------------------------------------------------------------------
# 1. Supabase 接続設定 (新規追加)
# --------------------------------------------------------------------------
# .streamlit/secrets.toml に設定した情報を使用して接続します
try:
    conn = st.connection("postgresql", type="sql")
except Exception as e:
    st.error(f"Supabaseへの接続に失敗しました。secrets.tomlを確認してください: {e}")

# --------------------------------------------------------------------------
# 2. データ読み込み関数
# --------------------------------------------------------------------------
@st.cache_data
def load_single_csv(path, encoding='utf-8'):
    """指定されたパスから単一のCSVファイルを読み込む関数"""
    logging.info(f"load_single_csv: {path} を {encoding} として読み込み開始。")
    try:
        # ID関連の列を文字列として読み込むように指定
        df = pd.read_csv(path, encoding=encoding, dtype={'商品ID': str, '倉庫ID': str, '業務区分ID': str, 'SET_ID': str})
        logging.info(f"load_single_csv: {path} の読み込みに成功しました。")
        return df
    except FileNotFoundError:
        logging.error(f"load_single_csv: ファイルが見つかりません: {path}")
        st.error(f"エラー: 指定されたファイルが見つかりませんでした。\nファイルがこのスクリプトと同じ場所にあるか確認してください: {path}")
        return None
    except Exception as e:
        logging.error(f"load_single_csv: {path} 読み込み中にエラーが発生: {e}")
        st.error(f"ファイル読み込みエラー: {e}")
        return None

@st.cache_data
def load_multiple_csv(pattern, encoding='utf-8'):
    """指定されたパターンに一致する複数のCSVを読み込んで結合する関数"""
    logging.info(f"load_multiple_csv: パターン '{pattern}' の検索を開始。")
    
    file_list = glob.glob(pattern)
    
    if not file_list:
        logging.warning(f"load_multiple_csv: パターンに一致するファイルが見つかりません: {pattern}")
        st.warning(f"警告: パターンに一致するファイルが見つかりませんでした。\nパターンを確認してください: {pattern}")
        return None

    logging.info(f"{len(file_list)} 件のファイルが見つかりました: {file_list}")
    
    df_list = []
    for file_path in file_list:
        try:
            # ID関連の列を文字列として読み込むように指定
            df = pd.read_csv(file_path, encoding=encoding, dtype={'商品ID': str, '倉庫ID': str})
            df_list.append(df)
        except Exception as e:
            logging.error(f"ファイルの読み込みに失敗しました: {file_path}, エラー: {e}")
            st.error(f"エラー: {file_path} の読み込みに失敗しました。")
            continue 
            
    if not df_list:
        logging.error("読み込めたデータが1つもありませんでした。")
        return None

    logging.info("すべてのデータフレームを結合します。")
    combined_df = pd.concat(df_list, ignore_index=True)
    return combined_df

# 棒グラフに数値ラベルを追加する関数
def add_labels_to_stacked_bar(ax, data_df):
    """積み上げ棒グラフの各セグメントにラベルを追加する"""
    bottom = pd.Series([0.0] * len(data_df), index=data_df.index) 
    x_positions = np.arange(len(data_df.index)) 

    for col in data_df.columns:
        values = data_df[col]
        # 値が一定以上の場合のみラベルを表示（閾値を調整）
        threshold = values.sum() * 0.03 
        non_zero_values = values[values > threshold] 
        
        valid_indices = non_zero_values.index
        # y_pos の計算時にインデックスが一致するように調整 (NaNを避ける)
        y_pos = bottom.loc[valid_indices].fillna(0) + non_zero_values.fillna(0) / 2
        
        x_pos_map = {label: i for i, label in enumerate(data_df.index)}
        valid_x_positions = [x_pos_map.get(idx) for idx in valid_indices if x_pos_map.get(idx) is not None]

        valid_non_zero_values = non_zero_values.iloc[:len(valid_x_positions)]
        valid_y_pos = y_pos.iloc[:len(valid_x_positions)]

        for i, val in enumerate(valid_non_zero_values):
             if i < len(valid_x_positions):
                # フォントサイズ微調整
                ax.text(valid_x_positions[i], valid_y_pos.iloc[i], f'{int(val)}', 
                        ha='center', va='center', fontsize=5, color='white', fontweight='bold') 
            
        bottom += values.fillna(0) 

# ★★★【改修ポイント】★★★ CSV変換用関数
@st.cache_data
def convert_df(df):
    # utf-8-sigにすることでExcelで開いた時の文字化けを防ぐ
    return df.to_csv(encoding='utf-8-sig').encode('utf-8-sig')

try:
    st.set_page_config(layout="wide") 
    st.title('📊 在庫・出荷データの可視化アプリ')

    # --- データの読み込み ---
    DATA_PATH1 = "T_9x30.csv"
    DATA_PATH_PACK_MASTER = "PACK_Classification.csv"
    DATA_PATH_SET_MASTER = "SET_Class.csv"
    DATA_PATH3_PATTERN = "CZ04003_*.csv"
    DATA_PATH5 = "T_9x07.csv"

    df1 = load_single_csv(DATA_PATH1, encoding='utf-8')
    df_pack_master = load_single_csv(DATA_PATH_PACK_MASTER, encoding='utf-8') 
    df_set_master = load_single_csv(DATA_PATH_SET_MASTER, encoding='utf-8') 
    df3 = load_multiple_csv(DATA_PATH3_PATTERN, encoding='cp932')
    df5 = load_single_csv(DATA_PATH5, encoding='utf-8')


    # --- サイドバーのフィルター定義 ---
    base_df_monthly = pd.DataFrame()
    base_df_weekly = pd.DataFrame()
    selected_daibunrui_shipping = [] 
    selected_shobunrui_shipping = []
    product_name_search_shipping = "" 
    selected_product_ids_shipping = []
    selected_gyomu = "すべて"
    selected_soko_shipping = "すべて"
    gyomu_display_map = {'4': '卸出荷機能', '7': '通販出荷機能'}
    soko_display_map = {'7': '大阪', '8': '千葉'}
    num_months = 12 
    num_weeks = 12 
    aggregation_level = "商品ID" # デフォルト値
    show_total_column = "なし" # デフォルト値

    # --- 出荷情報フィルタの準備 ---
    if df1 is not None and df_pack_master is not None and df_set_master is not None:
        
        st.sidebar.header(":blue[出荷情報フィルタ]")

        # 1. 集計単位の選択
        unit_selection = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True, key='unit_selection')

        # 2. マスタデータの切り替えと整形
        if unit_selection == "Pack":
            df_master_for_shipping = df_pack_master.copy()
            master_cols = ['商品ID', '商品名', '大分類', '中分類', '小分類']
        else: # SETの場合
            df_master_for_shipping = df_set_master.copy()
            df_master_for_shipping = df_master_for_shipping.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})
            master_cols = ['商品ID', '商品名', '大分類', '中分類', '小分類']
        
        # 3. マージ処理とフィルタリング
        if all(col in df_master_for_shipping.columns for col in master_cols):
            df_master_shipping = df_master_for_shipping[master_cols].drop_duplicates(subset='商品ID')
            df1['商品ID'] = df1['商品ID'].astype(str)
            df_master_shipping['商品ID'] = df_master_shipping['商品ID'].astype(str)
            base_df_monthly = pd.merge(df1, df_master_shipping, on='商品ID', how='left')
            
            if df5 is not None:
                df5['商品ID'] = df5['商品ID'].astype(str)
                base_df_weekly = pd.merge(df5, df_master_shipping, on='商品ID', how='left')

            # --- フィルタUI ---
            st.sidebar.markdown("---")
            aggregation_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True, key='agg_level')
            show_total_column = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True, key='show_total')
            st.sidebar.markdown("---")

            if '大分類' in base_df_monthly.columns:
                daibunrui_options = base_df_monthly['大分類'].dropna().unique().tolist()
                daibunrui_options.sort()
                selected_daibunrui_shipping = st.sidebar.multiselect(
                    "大分類で絞り込み（複数選択可）:", options=daibunrui_options, key='daibunrui_shipping'
                )
            
            df_after_daibunrui_filter = base_df_monthly[base_df_monthly['大分類'].isin(selected_daibunrui_shipping)] if selected_daibunrui_shipping else base_df_monthly

            if '小分類' in df_after_daibunrui_filter.columns:
                shobunrui_options = df_after_daibunrui_filter['小分類'].dropna().unique().tolist()
                shobunrui_options.sort()
                selected_shobunrui_shipping = st.sidebar.multiselect("小分類で絞り込み（複数選択可）:", options=shobunrui_options, key='shobunrui_shipping')
            
            df_after_shobunrui_filter = df_after_daibunrui_filter[df_after_daibunrui_filter['小分類'].isin(selected_shobunrui_shipping)] if selected_shobunrui_shipping else df_after_daibunrui_filter
            
            product_name_search_shipping = st.sidebar.text_input("商品名であいまい検索:", key='product_name_shipping').strip()
            df_after_name_filter = df_after_shobunrui_filter[df_after_shobunrui_filter['商品名'].str.contains(product_name_search_shipping, na=False)] if product_name_search_shipping else df_after_shobunrui_filter
            
            product_ids_input_shipping = st.sidebar.text_input("商品IDで絞り込み (カンマ区切りで複数可):", key='product_id_shipping').strip()
            selected_product_ids_shipping = [pid.strip() for pid in product_ids_input_shipping.split(',')] if product_ids_input_shipping else []
            df_after_product_id_filter = df_after_name_filter[df_after_name_filter['商品ID'].isin(selected_product_ids_shipping)] if selected_product_ids_shipping else df_after_name_filter

            if '業務区分ID' in df_after_product_id_filter.columns:
                gyomu_options = df_after_product_id_filter['業務区分ID'].dropna().unique().tolist()
                gyomu_options.sort()
                gyomu_options.insert(0, "すべて")
                selected_gyomu = st.sidebar.radio("業務区分IDで絞り込み:", options=gyomu_options, key='gyomu_shipping', format_func=lambda x: "すべて" if x == "すべて" else gyomu_display_map.get(x, x))
            
            df_after_gyomu_filter = df_after_product_id_filter[df_after_product_id_filter['業務区分ID'] == selected_gyomu] if selected_gyomu != "すべて" else df_after_product_id_filter
            
            if '倉庫ID' in df_after_gyomu_filter.columns:
                soko_options = df_after_gyomu_filter['倉庫ID'].dropna().unique().tolist()
                soko_options.sort()
                soko_options.insert(0, "すべて")
                selected_soko_shipping = st.sidebar.radio("倉庫IDで絞り込み:", options=soko_options, key='soko_shipping', format_func=lambda x: "すべて" if x == "すべて" else soko_display_map.get(x, x))
            
            st.sidebar.markdown("---")
            num_months = st.sidebar.slider("月間表示期間（ヶ月）", min_value=3, max_value=26, value=12, key='num_months')
            num_weeks = st.sidebar.slider("週間表示期間（週）", min_value=3, max_value=15, value=12, key='num_weeks')
        else:
            st.error(f"選択されたマスタ({unit_selection})に必要な列が含まれていません。")


    # --- 在庫情報フィルタの準備 ---
    base_df_stock = pd.DataFrame()
    selected_daibunrui_stock = []
    selected_shobunrui_stock = []
    product_name_search_stock = ""
    selected_product_ids_stock = []
    selected_quality_stock = "すべて"

    if df3 is not None and df_pack_master is not None:
        master_cols_stock = ['商品ID', '大分類', '中分類', '小分類', '商品名'] 
        if all(col in df_pack_master.columns for col in master_cols_stock):
            cols_to_drop = ['大分類', '中分類', '小分類', '商品名'] 
            df3['商品ID'] = df3['商品ID'].astype(str)
            df_master_stock = df_pack_master[master_cols_stock].drop_duplicates(subset='商品ID')
            df_master_stock['商品ID'] = df_master_stock['商品ID'].astype(str)
            df3_for_merge = df3.drop(columns=cols_to_drop, errors='ignore')
            base_df_stock = pd.merge(df3_for_merge, df_master_stock, on='商品ID', how='left')
        
        st.sidebar.header(":blue[在庫情報フィルタ]")
        if '大分類' in base_df_stock.columns:
            daibunrui_options_stock = base_df_stock['大分類'].dropna().unique().tolist()
            daibunrui_options_stock.sort()
            selected_daibunrui_stock = st.sidebar.multiselect(
                "大分類で絞り込み（複数選択可）:", options=daibunrui_options_stock, key='daibunrui_stock'
            )
        
        df_after_daibunrui_filter_stock = base_df_stock[base_df_stock['大分類'].isin(selected_daibunrui_stock)] if selected_daibunrui_stock else base_df_stock
        
        if '小分類' in df_after_daibunrui_filter_stock.columns:
            shobunrui_options_stock = df_after_daibunrui_filter_stock['小分類'].dropna().unique().tolist()
            shobunrui_options_stock.sort()
            selected_shobunrui_stock = st.sidebar.multiselect("小分類で絞り込み（複数選択可）:", options=shobunrui_options_stock, key='shobunrui_stock')
        
        df_after_shobunrui_filter_stock = df_after_daibunrui_filter_stock[df_after_daibunrui_filter_stock['小分類'].isin(selected_shobunrui_stock)] if selected_shobunrui_stock else df_after_daibunrui_filter_stock
        product_name_search_stock = st.sidebar.text_input("商品名であいまい検索:", key='product_name_stock').strip()
        df_after_name_filter_stock = df_after_shobunrui_filter_stock[df_after_shobunrui_filter_stock['商品名'].str.contains(product_name_search_stock, na=False)] if product_name_search_stock else df_after_shobunrui_filter_stock
        product_ids_input_stock = st.sidebar.text_input("商品IDで絞り込み (カンマ区切りで複数可):", key='product_id_stock').strip()
        selected_product_ids_stock = [pid.strip() for pid in product_ids_input_stock.split(',')] if product_ids_input_stock else []
        df_after_product_id_filter_stock = df_after_name_filter_stock[df_after_name_filter_stock['商品ID'].isin(selected_product_ids_stock)] if selected_product_ids_stock else df_after_name_filter_stock
        
        if '品質区分名' in df_after_product_id_filter_stock.columns:
            quality_options_stock = df_after_product_id_filter_stock['品質区分名'].dropna().unique().tolist()
            quality_options_stock.insert(0, "すべて")
            selected_quality_stock = st.sidebar.radio("品質区分名で絞り込み:", options=quality_options_stock, key='quality_stock')


    # --- タブの作成 ---
    tab_shipping, tab_stock = st.tabs(["📝 出荷情報", "📊 在庫情報"])

    # --- 出荷情報のタブ ---
    with tab_shipping:
        st.header("🚚 出荷情報")
        if not base_df_monthly.empty:
            # 月間出荷
            st.markdown("---")
            st.subheader("月間出荷数")
            gyomu_display_str = "すべて" if selected_gyomu == "すべて" else gyomu_display_map.get(selected_gyomu, selected_gyomu)
            soko_display_str = "すべて" if selected_soko_shipping == "すべて" else soko_display_map.get(selected_soko_shipping, selected_soko_shipping)
            st.write(f"**大分類:** `{selected_daibunrui_shipping if selected_daibunrui_shipping else 'すべて'}` | **小分類:** `{selected_shobunrui_shipping if selected_shobunrui_shipping else 'すべて'}` | **商品名:** `{product_name_search_shipping if product_name_search_shipping else 'すべて'}` | **商品ID:** `{selected_product_ids_shipping if selected_product_ids_shipping else 'すべて'}` | **業務区分ID:** `{gyomu_display_str}` | **倉庫ID:** `{soko_display_str}`")
            
            df_monthly_filtered = base_df_monthly[
                (base_df_monthly['大分類'].isin(selected_daibunrui_shipping) if selected_daibunrui_shipping else True) &
                (base_df_monthly['小分類'].isin(selected_shobunrui_shipping) if selected_shobunrui_shipping else True) &
                (base_df_monthly['商品名'].str.contains(product_name_search_shipping, na=False) if product_name_search_shipping else True) &
                (base_df_monthly['商品ID'].isin(selected_product_ids_shipping) if selected_product_ids_shipping else True) &
                (base_df_monthly['業務区分ID'] == selected_gyomu if selected_gyomu != "すべて" else True) &
                (base_df_monthly['倉庫ID'] == selected_soko_shipping if selected_soko_shipping != "すべて" else True)
            ]
            
            required_cols = ["倉庫ID", "業務区分ID", "商品ID", "month_code", "合計出荷数", "商品名", "大分類", "中分類", "小分類"]
            if not df_monthly_filtered.empty and all(col in df_monthly_filtered.columns for col in required_cols):
                
                # 集計粒度に応じてインデックスを切り替え
                if aggregation_level == "大分類":
                    index_cols = ["大分類"]
                    graph_stack_col = "大分類"
                elif aggregation_level == "中分類":
                    index_cols = ["大分類", "中分類"]
                    graph_stack_col = "中分類"
                elif aggregation_level == "小分類":
                    index_cols = ["大分類", "中分類", "小分類"]
                    graph_stack_col = "小分類"
                else: # 商品ID
                    index_cols = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
                    graph_stack_col = "商品名"

                pivot = df_monthly_filtered.pivot_table(index=index_cols, columns="month_code", values="合計出荷数", aggfunc="sum").fillna(0)
                recent_cols = pivot.columns[-num_months:] 
                pivot_filtered = pivot[pivot[recent_cols].sum(axis=1) != 0]
                pivot_display = pivot_filtered.loc[:, recent_cols].copy() 

                # 合計列と合計行を追加
                if show_total_column == "あり":
                    # 横計（列の合計）を追加
                    pivot_display['合計'] = pivot_display.sum(axis=1)
                    # 縦計（行の合計）を追加
                    total_row = pivot_display.sum()
                    total_row.name = ('合計',) * len(pivot_display.index.names) 
                    pivot_display = pd.concat([pivot_display, total_row.to_frame().T]) 
                    pivot_display.index.names = index_cols

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.info(f"ヒント: テーブルは直近{num_months}ヶ月合計が0でないデータを表示しています。")
                    st.dataframe(pivot_display.reset_index(), height=400, use_container_width=True)
                    # ★★★【改修ポイント】★★★ CSVダウンロードボタンを追加
                    csv = convert_df(pivot_display)
                    st.download_button(
                        label="データをCSVとしてダウンロード",
                        data=csv,
                        file_name=f'monthly_shipping_data_{num_months}months.csv',
                        mime='text/csv',
                    )

                with col2:
                    st.write(f"グラフ（{graph_stack_col}別積み上げ）") 
                    # グラフも動的に集計対象を変更
                    chart_df_monthly_base = df_monthly_filtered.pivot_table(index='month_code', columns=graph_stack_col, values='合計出荷数', aggfunc='sum').fillna(0)
                    chart_df_monthly_display = chart_df_monthly_base.iloc[-num_months:, :] 
                    if not chart_df_monthly_display.empty:
                        chart_data_top = chart_df_monthly_display 
                        fig = plt.figure() 
                        gs = gridspec.GridSpec(5, 1, height_ratios=[3, 1, 0.1, 0.1, 0.1]) 
                        ax_chart = fig.add_subplot(gs[0]) 
                        ax_legend = fig.add_subplot(gs[1]) 
                        ax_legend.axis('off') 
                        ax_chart.set_facecolor('lightgray') 
                        chart_data_top.plot(kind='bar', stacked=True, ax=ax_chart, legend=False) 
                        try: add_labels_to_stacked_bar(ax_chart, chart_data_top)
                        except Exception as label_e: st.caption("数値ラベル表示中にエラー")
                        ax_chart.set_xlabel("月コード") 
                        ax_chart.set_ylabel("合計出荷数")
                        tick_interval = max(1, len(chart_data_top) // 10) 
                        ax_chart.set_xticks(np.arange(0, len(chart_data_top), tick_interval))
                        ax_chart.set_xticklabels(chart_data_top.index[::tick_interval], rotation=45, ha='right', fontsize=8) 
                        handles, labels = ax_chart.get_legend_handles_labels()
                        ncol_legend = min(5, len(labels)) 
                        ax_legend.legend(handles, labels, title=graph_stack_col, loc='upper center', ncol=ncol_legend, fontsize=6) 
                        plt.tight_layout(rect=[0, 0.05, 1, 1]) 
                        st.pyplot(fig, use_container_width=True)
                    else: st.warning("月間グラフ: データ無")
            else:
                st.warning("月間出荷: 条件一致データ無 or 列不足")

            # 週間出荷
            if not base_df_weekly.empty:
                st.markdown("---")
                st.subheader("週間出荷数")
                st.write(f"**大分類:** `{selected_daibunrui_shipping if selected_daibunrui_shipping else 'すべて'}` | **小分類:** `{selected_shobunrui_shipping if selected_shobunrui_shipping else 'すべて'}` | **商品名:** `{product_name_search_shipping if product_name_search_shipping else 'すべて'}` | **商品ID:** `{selected_product_ids_shipping if selected_product_ids_shipping else 'すべて'}` | **業務区分ID:** `{gyomu_display_str}` | **倉庫ID:** `{soko_display_str}`")
                
                df_weekly_filtered = base_df_weekly[
                    (base_df_weekly['大分類'].isin(selected_daibunrui_shipping) if selected_daibunrui_shipping else True) &
                    (base_df_weekly['小分類'].isin(selected_shobunrui_shipping) if selected_shobunrui_shipping else True) &
                    (base_df_weekly['商品名'].str.contains(product_name_search_shipping, na=False) if product_name_search_shipping else True) &
                    (base_df_weekly['商品ID'].isin(selected_product_ids_shipping) if selected_product_ids_shipping else True) &
                    (base_df_weekly['業務区分ID'] == selected_gyomu if selected_gyomu != "すべて" else True) &
                    (base_df_weekly['倉庫ID'] == selected_soko_shipping if selected_soko_shipping != "すべて" else True)
                ]
                
                required_cols_weekly = ["倉庫ID", "業務区分ID", "商品ID", "week_code", "合計出荷数", "商品名", "大分類", "中分類", "小分類"]
                if not df_weekly_filtered.empty and all(col in df_weekly_filtered.columns for col in required_cols_weekly):
                    
                    # 集計粒度に応じてインデックスを切り替え（週間）
                    if aggregation_level == "大分類":
                        index_cols_w = ["大分類"]
                        graph_stack_col_w = "大分類"
                    elif aggregation_level == "中分類":
                        index_cols_w = ["大分類", "中分類"]
                        graph_stack_col_w = "中分類"
                    elif aggregation_level == "小分類":
                        index_cols_w = ["大分類", "中分類", "小分類"]
                        graph_stack_col_w = "小分類"
                    else: # 商品ID
                        index_cols_w = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
                        graph_stack_col_w = "商品名"

                    pivot_weekly = df_weekly_filtered.pivot_table(index=index_cols_w, columns="week_code", values="合計出荷数", aggfunc="sum").fillna(0)
                    recent_cols_weekly = pivot_weekly.columns[-num_weeks:]
                    pivot_weekly_filtered = pivot_weekly[pivot_weekly[recent_cols_weekly].sum(axis=1) != 0]
                    pivot_weekly_display = pivot_weekly_filtered.loc[:, recent_cols_weekly].copy()

                    # 合計列と合計行を追加（週間）
                    if show_total_column == "あり":
                        # 横計
                        pivot_weekly_display['合計'] = pivot_weekly_display.sum(axis=1)
                        # 縦計
                        total_row_w = pivot_weekly_display.sum()
                        total_row_w.name = ('合計',) * len(pivot_weekly_display.index.names)
                        pivot_weekly_display = pd.concat([pivot_weekly_display, total_row_w.to_frame().T])
                        pivot_weekly_display.index.names = index_cols_w

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.info(f"ヒント: テーブルは直近{num_weeks}週合計が0でないデータを表示しています。")
                        st.dataframe(pivot_weekly_display.reset_index(), height=400, use_container_width=True)
                        # ★★★【改修ポイント】★★★ CSVダウンロードボタンを追加
                        csv_weekly = convert_df(pivot_weekly_display)
                        st.download_button(
                            label="データをCSVとしてダウンロード",
                            data=csv_weekly,
                            file_name=f'weekly_shipping_data_{num_weeks}weeks.csv',
                            mime='text/csv',
                        )
                    with col2:
                        st.write(f"グラフ（{graph_stack_col_w}別積み上げ）") 
                        chart_df_weekly_base = df_weekly_filtered.pivot_table(index='week_code', columns=graph_stack_col_w, values='合計出荷数', aggfunc='sum').fillna(0)
                        chart_df_weekly_display = chart_df_weekly_base.iloc[-num_weeks:, :] 
                        if not chart_df_weekly_display.empty:
                            chart_data_top_w = chart_df_weekly_display 
                            fig_w = plt.figure()
                            gs_w = gridspec.GridSpec(5, 1, height_ratios=[3, 1, 0.1, 0.1, 0.1]) 
                            ax_chart_w = fig_w.add_subplot(gs_w[0])
                            ax_legend_w = fig_w.add_subplot(gs_w[1])
                            ax_legend_w.axis('off')
                            ax_chart_w.set_facecolor('lightgray')
                            chart_data_top_w.plot(kind='bar', stacked=True, ax=ax_chart_w, legend=False)
                            try: add_labels_to_stacked_bar(ax_chart_w, chart_data_top_w)
                            except Exception as label_e: st.caption("数値ラベル表示中にエラー")
                            ax_chart_w.set_xlabel("週コード")
                            ax_chart_w.set_ylabel("合計出荷数")
                            tick_interval_w = max(1, len(chart_data_top_w) // 10) 
                            ax_chart_w.set_xticks(np.arange(0, len(chart_data_top_w), tick_interval_w))
                            ax_chart_w.set_xticklabels(chart_data_top_w.index[::tick_interval_w], rotation=45, ha='right', fontsize=8)
                            handles_w, labels_w = ax_chart_w.get_legend_handles_labels()
                            ncol_legend_w = min(5, len(labels_w))
                            ax_legend_w.legend(handles_w, labels_w, title=graph_stack_col_w, loc='upper center', ncol=ncol_legend_w, fontsize=6) 
                            plt.tight_layout(rect=[0, 0.05, 1, 1]) 
                            st.pyplot(fig_w, use_container_width=True) 
                        else: st.warning("週間グラフ: データ無")
                else:
                    st.warning("週間出荷: 条件一致データ無 or 列不足")
    
    # --- 在庫情報のタブ ---
    # (変更なし)
    with tab_stock:
        st.header("📦 在庫情報")
        if not base_df_stock.empty:
            # ★★★ フィルター適用ロジック更新 (大分類)
            pivot_target_df_stock = base_df_stock[
                (base_df_stock['大分類'].isin(selected_daibunrui_stock) if selected_daibunrui_stock else True) &
                (base_df_stock['小分類'].isin(selected_shobunrui_stock) if selected_shobunrui_stock else True) &
                (base_df_stock['商品名'].str.contains(product_name_search_stock, na=False) if product_name_search_stock else True) &
                (base_df_stock['商品ID'].isin(selected_product_ids_stock) if selected_product_ids_stock else True) &
                (base_df_stock['品質区分名'] == selected_quality_stock if selected_quality_stock != "すべて" else True)
            ]

            st.markdown("---")
            st.subheader("利用可能在庫")
             # ★★★ フィルター表示更新 (大分類)
            st.write(f"**大分類:** `{selected_daibunrui_stock if selected_daibunrui_stock else 'すべて'}` | **小分類:** `{selected_shobunrui_stock if selected_shobunrui_stock else 'すべて'}` | **商品名:** `{product_name_search_stock if product_name_search_stock else 'すべて'}` | **商品ID:** `{selected_product_ids_stock if selected_product_ids_stock else 'すべて'}` | **品質区分名:** `{selected_quality_stock}`")
            
            required_cols_stock = ["商品ID", "商品名", "倉庫名", "在庫数(引当数を含む)", "引当数"]
            if not pivot_target_df_stock.empty and all(col in pivot_target_df_stock.columns for col in required_cols_stock):
                try:
                    # (以降、在庫情報の表示部分は変更なし)
                    pivot_target_df_stock['実在庫数'] = pd.to_numeric(pivot_target_df_stock['在庫数(引当数を含む)'], errors='coerce').fillna(0) - pd.to_numeric(pivot_target_df_stock['引当数'], errors='coerce').fillna(0)
                    pivot_index_stock = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
                    available_index_cols = [col for col in pivot_index_stock if col in pivot_target_df_stock.columns]
                    pivot_stock = pivot_target_df_stock.pivot_table(index=available_index_cols, columns="倉庫名", values="実在庫数", aggfunc="sum").fillna(0)
                    pivot_stock_filtered = pivot_stock[pivot_stock.sum(axis=1) != 0]

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.info("ヒント: テーブルは合計在庫が0でないデータを表示しています。")
                        st.dataframe(pivot_stock_filtered.reset_index(), height=400, use_container_width=True)
                        # ★★★【改修ポイント】★★★ CSVダウンロードボタンを追加
                        csv_stock = convert_df(pivot_stock_filtered)
                        st.download_button(
                            label="データをCSVとしてダウンロード",
                            data=csv_stock,
                            file_name='inventory_data.csv',
                            mime='text/csv',
                        )
                    with col2:
                        st.write("グラフ（大分類別 在庫構成比）")
                        if '大分類' in pivot_target_df_stock.columns and '実在庫数' in pivot_target_df_stock.columns:
                            pie_data = pivot_target_df_stock.groupby('大分類')['実在庫数'].sum()
                            pie_data = pie_data[pie_data > 0] 
                            if not pie_data.empty:
                                fig, ax = plt.subplots() 
                                ax.pie(pie_data, labels=pie_data.index, autopct='%1.1f%%', startangle=90, textprops={'fontsize': 8}) 
                                ax.axis('equal')
                                fig.patch.set_facecolor('lightgray')
                                st.pyplot(fig, use_container_width=True) 
                            else: st.warning("グラフ化できる在庫データ無")
                        else: st.warning("グラフ作成に必要な列無")
                except Exception as e:
                    st.error(f"ピボットテーブル・グラフ作成中にエラー: {e}")
            else:
                st.warning("在庫情報: 条件一致データ無 or 列不足")

    # --- 共通のフッターなど ---
    st.markdown("---")
    with st.expander("取り込みデータファイルの仕様について"):
        st.markdown("""
        - **月間出荷情報 (T_9x30.csv)**: 月ごとの出荷実績データ。
        - **商品マスタ (PACK_Classification.csv)**: 商品の分類情報（大分類、中分類、小分類）を格納。
        - **在庫情報 (CZ04003_*.csv)**: 日々の在庫スナップショット。ワイルドカードで複数ファイルを読み込みます。
        - **週間出荷情報 (T_9x07.csv)**: 週ごとの出荷実績データ。
        """)

except Exception as e:
    logging.critical(f"--- アプリケーションの未補足の致命的エラー: {e} ---", exc_info=True)
    if "Image size" in str(e):
         st.error("グラフ描画エラー: グラフ複雑すぎ。フィルター条件絞り込んでください。")
         logging.error(f"グラフ描画エラー（Image size limit）: {e}")
    else:
        st.error(f"予期せぬエラー: {e}")






