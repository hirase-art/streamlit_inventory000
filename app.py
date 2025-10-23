import streamlit as st
import pandas as pd
import logging
import glob # ★ ワイルドカードを扱うためにglobをインポート
import matplotlib.pyplot as plt # ★ グラフ作成のためにpyplotをインポート
import japanize_matplotlib # 日本語文字化け対策
import numpy as np # ★ 数値計算のためにnumpyをインポート

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',
    filemode='w'
)

logging.info("--- アプリケーション開始 ---")

# --------------------------------------------------------------------------
# データ読み込み関数
# --------------------------------------------------------------------------
@st.cache_data
def load_single_csv(path, encoding='utf-8'):
    """指定されたパスから単一のCSVファイルを読み込む関数"""
    logging.info(f"load_single_csv: {path} を {encoding} として読み込み開始。")
    try:
        # ID関連の列を文字列として読み込むように指定
        df = pd.read_csv(path, encoding=encoding, dtype={'商品ID': str, '倉庫ID': str, '業務区分ID': str})
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

# # 棒グラフに数値ラベルを追加する関数 (情報過多になるため今回は使用しない)
# def add_labels_to_stacked_bar(ax, data_df):
#     ... (省略) ...

try:
    st.set_page_config(layout="wide") 
    st.title('📊 在庫・出荷データの可視化アプリ')

    # --- データの読み込み ---
    DATA_PATH1 = "T_9x30.csv"
    DATA_PATH_MASTER = "PACK_Classification.csv"
    DATA_PATH3_PATTERN = "CZ04003_*.csv"
    DATA_PATH5 = "T_9x07.csv"

    df1 = load_single_csv(DATA_PATH1, encoding='utf-8')
    df_master = load_single_csv(DATA_PATH_MASTER, encoding='utf-8') 
    df3 = load_multiple_csv(DATA_PATH3_PATTERN, encoding='cp932')
    df5 = load_single_csv(DATA_PATH5, encoding='utf-8')

    # --- サイドバーのフィルターを先にすべて定義 ---
    # (フィルター部分は変更なしのため省略)
    base_df_monthly = pd.DataFrame()
    base_df_weekly = pd.DataFrame()
    selected_daibunrui_shipping = "すべて"
    selected_shobunrui_shipping = []
    selected_product_ids_shipping = []
    selected_gyomu = "すべて"
    selected_soko_shipping = "すべて"
    gyomu_display_map = {'4': '卸出荷機能', '7': '通販出荷機能'}
    soko_display_map = {'7': '大阪', '8': '千葉'}
    num_months = 12 
    num_weeks = 12 

    if df1 is not None and df_master is not None:
        master_cols = ['商品ID', '商品名', '大分類', '中分類', '小分類']
        if all(col in df_master.columns for col in master_cols):
            df_master_shipping = df_master[master_cols].drop_duplicates(subset='商品ID')
            base_df_monthly = pd.merge(df1, df_master_shipping, on='商品ID', how='left')
            if df5 is not None:
                base_df_weekly = pd.merge(df5, df_master_shipping, on='商品ID', how='left')
            
            st.sidebar.header(":blue[出荷情報フィルタ]")
            
            if '大分類' in base_df_monthly.columns:
                daibunrui_options = base_df_monthly['大分類'].dropna().unique().tolist()
                daibunrui_options.sort()
                daibunrui_options.insert(0, "すべて")
                selected_daibunrui_shipping = st.sidebar.selectbox("大分類で絞り込み:", options=daibunrui_options, key='daibunrui_shipping')
            
            df_after_daibunrui_filter = base_df_monthly[base_df_monthly['大分類'] == selected_daibunrui_shipping] if selected_daibunrui_shipping != "すべて" else base_df_monthly
            if '小分類' in df_after_daibunrui_filter.columns:
                shobunrui_options = df_after_daibunrui_filter['小分類'].dropna().unique().tolist()
                shobunrui_options.sort()
                selected_shobunrui_shipping = st.sidebar.multiselect("小分類で絞り込み（複数選択可）:", options=shobunrui_options, key='shobunrui_shipping')
            
            df_after_shobunrui_filter = df_after_daibunrui_filter[df_after_daibunrui_filter['小分類'].isin(selected_shobunrui_shipping)] if selected_shobunrui_shipping else df_after_daibunrui_filter
            product_ids_input_shipping = st.sidebar.text_input("商品IDで絞り込み (カンマ区切りで複数可):", key='product_id_shipping').strip()
            selected_product_ids_shipping = [pid.strip() for pid in product_ids_input_shipping.split(',')] if product_ids_input_shipping else []
            df_after_product_id_filter = df_after_shobunrui_filter[df_after_shobunrui_filter['商品ID'].isin(selected_product_ids_shipping)] if selected_product_ids_shipping else df_after_shobunrui_filter

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
            num_months = st.sidebar.slider("月間表示期間（ヶ月）", min_value=3, max_value=15, value=12, key='num_months')
            num_weeks = st.sidebar.slider("週間表示期間（週）", min_value=3, max_value=15, value=12, key='num_weeks')

    # --- 在庫情報フィルタの準備 ---
    # (省略)
    base_df_stock = pd.DataFrame()
    selected_daibunrui_stock = "すべて"
    selected_shobunrui_stock = []
    selected_product_ids_stock = []
    selected_quality_stock = "すべて"

    if df3 is not None and df_master is not None:
        master_cols_stock = ['商品ID', '大分類', '中分類', '小分類']
        if all(col in df_master.columns for col in master_cols_stock):
            cols_to_drop = ['大分類', '中分類', '小分類']
            df3_for_merge = df3.drop(columns=cols_to_drop, errors='ignore')
            df_master_stock = df_master[master_cols_stock].drop_duplicates(subset='商品ID')
            base_df_stock = pd.merge(df3_for_merge, df_master_stock, on='商品ID', how='left')
        
        st.sidebar.header(":blue[在庫情報フィルタ]")
        if '大分類' in base_df_stock.columns:
            daibunrui_options_stock = base_df_stock['大分類'].dropna().unique().tolist()
            daibunrui_options_stock.sort()
            daibunrui_options_stock.insert(0, "すべて")
            selected_daibunrui_stock = st.sidebar.selectbox("大分類で絞り込み:", options=daibunrui_options_stock, key='daibunrui_stock')
        
        df_after_daibunrui_filter_stock = base_df_stock[base_df_stock['大分類'] == selected_daibunrui_stock] if selected_daibunrui_stock != "すべて" else base_df_stock
        if '小分類' in df_after_daibunrui_filter_stock.columns:
            shobunrui_options_stock = df_after_daibunrui_filter_stock['小分類'].dropna().unique().tolist()
            shobunrui_options_stock.sort()
            selected_shobunrui_stock = st.sidebar.multiselect("小分類で絞り込み（複数選択可）:", options=shobunrui_options_stock, key='shobunrui_stock')
        
        df_after_shobunrui_filter_stock = df_after_daibunrui_filter_stock[df_after_daibunrui_filter_stock['小分類'].isin(selected_shobunrui_stock)] if selected_shobunrui_stock else df_after_daibunrui_filter_stock
        product_ids_input_stock = st.sidebar.text_input("商品IDで絞り込み (カンマ区切りで複数可):", key='product_id_stock').strip()
        selected_product_ids_stock = [pid.strip() for pid in product_ids_input_stock.split(',')] if product_ids_input_stock else []
        df_after_product_id_filter_stock = df_after_shobunrui_filter_stock[df_after_shobunrui_filter_stock['商品ID'].isin(selected_product_ids_stock)] if selected_product_ids_stock else df_after_shobunrui_filter_stock
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
            st.write(f"**大分類:** `{selected_daibunrui_shipping}` | **小分類:** `{selected_shobunrui_shipping if selected_shobunrui_shipping else 'すべて'}` | **商品ID:** `{selected_product_ids_shipping if selected_product_ids_shipping else 'すべて'}` | **業務区分ID:** `{gyomu_display_str}` | **倉庫ID:** `{soko_display_str}`")
            
            df_monthly_filtered = base_df_monthly[
                (base_df_monthly['大分類'] == selected_daibunrui_shipping if selected_daibunrui_shipping != "すべて" else True) &
                (base_df_monthly['小分類'].isin(selected_shobunrui_shipping) if selected_shobunrui_shipping else True) &
                (base_df_monthly['商品ID'].isin(selected_product_ids_shipping) if selected_product_ids_shipping else True) &
                (base_df_monthly['業務区分ID'] == selected_gyomu if selected_gyomu != "すべて" else True) &
                (base_df_monthly['倉庫ID'] == selected_soko_shipping if selected_soko_shipping != "すべて" else True)
            ]
            
            required_cols = ["倉庫ID", "業務区分ID", "商品ID", "month_code", "合計出荷数", "商品名", "大分類", "中分類", "小分類"]
            if not df_monthly_filtered.empty and all(col in df_monthly_filtered.columns for col in required_cols):
                pivot = df_monthly_filtered.pivot_table(index=["大分類", "中分類", "小分類", "商品ID", "商品名"], columns="month_code", values="合計出荷数", aggfunc="sum").fillna(0)
                
                recent_cols = pivot.columns[-num_months:] 
                pivot_filtered = pivot[pivot[recent_cols].sum(axis=1) != 0]
                pivot_display = pivot_filtered.loc[:, recent_cols]

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.info(f"ヒント: テーブルは直近{num_months}ヶ月合計が0でないデータを表示しています。")
                    st.dataframe(pivot_display.reset_index(), height=400, use_container_width=True)
                with col2:
                    st.write("グラフ（上位5商品+その他）")
                    chart_df_monthly_base = df_monthly_filtered.pivot_table(index='month_code', columns='商品名', values='合計出荷数', aggfunc='sum').fillna(0)
                    chart_df_monthly_display = chart_df_monthly_base.iloc[-num_months:, :] 
                    
                    if not chart_df_monthly_display.empty:
                        product_totals = chart_df_monthly_display.sum().sort_values(ascending=False)
                        top_products = product_totals.head(5).index.tolist()
                        
                        chart_data_top = chart_df_monthly_display[top_products]
                        if len(product_totals) > 5:
                            other_products = product_totals.iloc[5:].index.tolist()
                            chart_data_top['その他'] = chart_df_monthly_display[other_products].sum(axis=1)

                        fig, ax = plt.subplots(figsize=(6, 4)) # グラフサイズ調整
                        chart_data_top.plot(kind='bar', stacked=True, ax=ax)
                        ax.set_xlabel("月コード")
                        ax.set_ylabel("合計出荷数")
                        # ★★★【改修ポイント】★★★ X軸ラベルの間引き
                        tick_interval = max(1, len(chart_data_top) // 10) # 10個程度のラベルになるように調整
                        ax.set_xticks(np.arange(0, len(chart_data_top), tick_interval))
                        ax.set_xticklabels(chart_data_top.index[::tick_interval], rotation=45, ha='right', fontsize=8) # フォントサイズ調整
                        # ★★★【改修ポイント】★★★ 凡例をグラフの外（右側）に配置、フォントサイズ調整
                        ax.legend(title='商品名', bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
                        plt.tight_layout(rect=[0, 0, 0.80, 1]) # レイアウト調整して凡例スペース確保
                        st.pyplot(fig)
                        st.caption("上位5商品（+その他）を表示")
                    else:
                        st.warning("月間出荷グラフ: 表示できるデータがありません。")

            else:
                st.warning("月間出荷: 選択された条件に一致するデータがないか、必要な列が不足しています。")

            # 週間出荷
            if not base_df_weekly.empty:
                st.markdown("---")
                st.subheader("週間出荷数")
                st.write(f"**大分類:** `{selected_daibunrui_shipping}` | **小分類:** `{selected_shobunrui_shipping if selected_shobunrui_shipping else 'すべて'}` | **商品ID:** `{selected_product_ids_shipping if selected_product_ids_shipping else 'すべて'}` | **業務区分ID:** `{gyomu_display_str}` | **倉庫ID:** `{soko_display_str}`")
                
                df_weekly_filtered = base_df_weekly[
                    (base_df_weekly['大分類'] == selected_daibunrui_shipping if selected_daibunrui_shipping != "すべて" else True) &
                    (base_df_weekly['小分類'].isin(selected_shobunrui_shipping) if selected_shobunrui_shipping else True) &
                    (base_df_weekly['商品ID'].isin(selected_product_ids_shipping) if selected_product_ids_shipping else True) &
                    (base_df_weekly['業務区分ID'] == selected_gyomu if selected_gyomu != "すべて" else True) &
                    (base_df_weekly['倉庫ID'] == selected_soko_shipping if selected_soko_shipping != "すべて" else True)
                ]
                
                required_cols_weekly = ["倉庫ID", "業務区分ID", "商品ID", "week_code", "合計出荷数", "商品名", "大分類", "中分類", "小分類"]
                if not df_weekly_filtered.empty and all(col in df_weekly_filtered.columns for col in required_cols_weekly):
                    pivot_weekly = df_weekly_filtered.pivot_table(index=["大分類", "中分類", "小分類", "商品ID", "商品名"], columns="week_code", values="合計出荷数", aggfunc="sum").fillna(0)
                    
                    recent_cols_weekly = pivot_weekly.columns[-num_weeks:]
                    pivot_weekly_filtered = pivot_weekly[pivot_weekly[recent_cols_weekly].sum(axis=1) != 0]
                    pivot_weekly_display = pivot_weekly_filtered.loc[:, recent_cols_weekly]

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.info(f"ヒント: テーブルは直近{num_weeks}週合計が0でないデータを表示しています。")
                        st.dataframe(pivot_weekly_display.reset_index(), height=400, use_container_width=True)
                    with col2:
                        st.write("グラフ（上位5商品+その他）")
                        chart_df_weekly_base = df_weekly_filtered.pivot_table(index='week_code', columns='商品名', values='合計出荷数', aggfunc='sum').fillna(0)
                        chart_df_weekly_display = chart_df_weekly_base.iloc[-num_weeks:, :] 
                        
                        if not chart_df_weekly_display.empty:
                            product_totals_w = chart_df_weekly_display.sum().sort_values(ascending=False)
                            top_products_w = product_totals_w.head(5).index.tolist()
                            
                            chart_data_top_w = chart_df_weekly_display[top_products_w]
                            if len(product_totals_w) > 5:
                                other_products_w = product_totals_w.iloc[5:].index.tolist()
                                chart_data_top_w['その他'] = chart_df_weekly_display[other_products_w].sum(axis=1)

                            fig_w, ax_w = plt.subplots(figsize=(6, 4)) # グラフサイズ調整
                            chart_data_top_w.plot(kind='bar', stacked=True, ax=ax_w)
                            ax_w.set_xlabel("週コード")
                            ax_w.set_ylabel("合計出荷数")
                            # ★★★【改修ポイント】★★★ X軸ラベルの間引き
                            tick_interval = max(1, len(chart_data_top_w) // 10) 
                            ax_w.set_xticks(np.arange(0, len(chart_data_top_w), tick_interval))
                            ax_w.set_xticklabels(chart_data_top_w.index[::tick_interval], rotation=45, ha='right', fontsize=8) # フォントサイズ調整
                            # ★★★【改修ポイント】★★★ 凡例をグラフの外（右側）に配置、フォントサイズ調整
                            ax_w.legend(title='商品名', bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
                            plt.tight_layout(rect=[0, 0, 0.80, 1]) # レイアウト調整
                            
                            st.pyplot(fig_w)
                            st.caption("上位5商品（+その他）を表示")
                        else:
                             st.warning("週間出荷グラフ: 表示できるデータがありません。")
                else:
                    st.warning("週間出荷: 選択された条件に一致するデータがないか、必要な列が不足しています。")
    
    # --- 在庫情報のタブ ---
    with tab_stock:
        st.header("📦 在庫情報")
        if not base_df_stock.empty:
            pivot_target_df_stock = base_df_stock[
                (base_df_stock['大分類'] == selected_daibunrui_stock if selected_daibunrui_stock != "すべて" else True) &
                (base_df_stock['小分類'].isin(selected_shobunrui_stock) if selected_shobunrui_stock else True) &
                (base_df_stock['商品ID'].isin(selected_product_ids_stock) if selected_product_ids_stock else True) &
                (base_df_stock['品質区分名'] == selected_quality_stock if selected_quality_stock != "すべて" else True)
            ]

            st.markdown("---")
            st.subheader("利用可能在庫")
            st.write(f"**大分類:** `{selected_daibunrui_stock}` | **小分類:** `{selected_shobunrui_stock if selected_shobunrui_stock else 'すべて'}` | **商品ID:** `{selected_product_ids_stock if selected_product_ids_stock else 'すべて'}` | **品質区分名:** `{selected_quality_stock}`")
            
            required_cols_stock = ["商品ID", "商品名", "倉庫名", "在庫数(引当数を含む)", "引当数"]
            if not pivot_target_df_stock.empty and all(col in pivot_target_df_stock.columns for col in required_cols_stock):
                try:
                    pivot_target_df_stock['実在庫数'] = pd.to_numeric(pivot_target_df_stock['在庫数(引当数を含む)'], errors='coerce').fillna(0) - pd.to_numeric(pivot_target_df_stock['引当数'], errors='coerce').fillna(0)
                    pivot_index_stock = ["大分類", "中分類", "小分類", "商品ID", "商品名"]
                    pivot_stock = pivot_target_df_stock.pivot_table(index=pivot_index_stock, columns="倉庫名", values="実在庫数", aggfunc="sum").fillna(0)
                    pivot_stock_filtered = pivot_stock[pivot_stock.sum(axis=1) != 0]

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.info("ヒント: テーブルは合計在庫が0でないデータを表示しています。")
                        st.dataframe(pivot_stock_filtered.reset_index(), height=400, use_container_width=True)
                    with col2:
                        st.write("グラフ（大分類別 在庫構成比）")
                        if '大分類' in pivot_target_df_stock.columns:
                            pie_data = pivot_target_df_stock.groupby('大分類')['実在庫数'].sum()
                            pie_data = pie_data[pie_data > 0] 
                            if not pie_data.empty:
                                fig, ax = plt.subplots(figsize=(4,4)) # 円グラフのサイズを調整
                                ax.pie(pie_data, labels=pie_data.index, autopct='%1.1f%%', startangle=90, textprops={'fontsize': 8}) # フォントサイズ調整
                                ax.axis('equal')
                                st.pyplot(fig)
                            else:
                                st.warning("グラフ化できる在庫データがありません。")
                except Exception as e:
                    st.error(f"ピボットテーブルまたはグラフの作成中にエラーが発生しました: {e}")
            else:
                st.warning("在庫情報: 選択された条件に一致するデータがないか、必要な列が不足しています。")

    # --- 共通のフッターなど ---
    # (省略)

except Exception as e:
    logging.critical(f"--- アプリケーションの未補足の致命的エラー: {e} ---", exc_info=True)
    if "Image size" in str(e):
         st.error("グラフ描画エラー: グラフが複雑すぎるため、表示できませんでした。フィルター条件を絞り込んでください。")
         logging.error(f"グラフ描画エラー（Image size limit）: {e}")
    else:
        st.error(f"予期せぬエラーが発生しました: {e}")

