import streamlit as st
import pandas as pd
import logging
import glob # ★ ワイルドカードを扱うためにglobをインポート
import matplotlib.pyplot as plt # ★ グラフ作成のためにpyplotをインポート
import japanize_matplotlib # 日本語文字化け対策

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

try:
    st.set_page_config(layout="wide") # ★ページレイアウトをワイドに変更
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

    # --- 出荷情報フィルタの準備 ---
    if df1 is not None and df_master is not None:
        master_cols = ['商品ID', '商品名', '大分類', '中分類', '小分類']
        if all(col in df_master.columns for col in master_cols):
            df_master_shipping = df_master[master_cols].drop_duplicates(subset='商品ID')
            base_df_monthly = pd.merge(df1, df_master_shipping, on='商品ID', how='left')
            if df5 is not None:
                base_df_weekly = pd.merge(df5, df_master_shipping, on='商品ID', how='left')
            
            st.sidebar.header(":blue[出荷情報フィルタ]")
            
            selected_daibunrui_shipping = "すべて"
            if '大分類' in base_df_monthly.columns:
                daibunrui_options = base_df_monthly['大分類'].dropna().unique().tolist()
                daibunrui_options.sort()
                daibunrui_options.insert(0, "すべて")
                selected_daibunrui_shipping = st.sidebar.selectbox("大分類で絞り込み:", options=daibunrui_options, key='daibunrui_shipping')
            
            df_after_daibunrui_filter = base_df_monthly[base_df_monthly['大分類'] == selected_daibunrui_shipping] if selected_daibunrui_shipping != "すべて" else base_df_monthly
            selected_shobunrui_shipping = []
            if '小分類' in df_after_daibunrui_filter.columns:
                shobunrui_options = df_after_daibunrui_filter['小分類'].dropna().unique().tolist()
                shobunrui_options.sort()
                selected_shobunrui_shipping = st.sidebar.multiselect("小分類で絞り込み（複数選択可）:", options=shobunrui_options, key='shobunrui_shipping')
            
            df_after_shobunrui_filter = df_after_daibunrui_filter[df_after_daibunrui_filter['小分類'].isin(selected_shobunrui_shipping)] if selected_shobunrui_shipping else df_after_daibunrui_filter
            product_ids_input_shipping = st.sidebar.text_input("商品IDで絞り込み (カンマ区切りで複数可):", key='product_id_shipping').strip()
            selected_product_ids_shipping = [pid.strip() for pid in product_ids_input_shipping.split(',')] if product_ids_input_shipping else []
            df_after_product_id_filter = df_after_shobunrui_filter[df_after_shobunrui_filter['商品ID'].isin(selected_product_ids_shipping)] if selected_product_ids_shipping else df_after_shobunrui_filter

            gyomu_display_map = {'4': '卸出荷機能', '7': '通販出荷機能'}
            selected_gyomu = "すべて"
            if '業務区分ID' in df_after_product_id_filter.columns:
                gyomu_options = df_after_product_id_filter['業務区分ID'].dropna().unique().tolist()
                gyomu_options.sort()
                gyomu_options.insert(0, "すべて")
                selected_gyomu = st.sidebar.radio("業務区分IDで絞り込み:", options=gyomu_options, key='gyomu_shipping', format_func=lambda x: "すべて" if x == "すべて" else gyomu_display_map.get(x, x))
            
            df_after_gyomu_filter = df_after_product_id_filter[df_after_product_id_filter['業務区分ID'] == selected_gyomu] if selected_gyomu != "すべて" else df_after_product_id_filter
            soko_display_map = {'7': '大阪', '8': '千葉'}
            selected_soko_shipping = "すべて"
            if '倉庫ID' in df_after_gyomu_filter.columns:
                soko_options = df_after_gyomu_filter['倉庫ID'].dropna().unique().tolist()
                soko_options.sort()
                soko_options.insert(0, "すべて")
                selected_soko_shipping = st.sidebar.radio("倉庫IDで絞り込み:", options=soko_options, key='soko_shipping', format_func=lambda x: "すべて" if x == "すべて" else soko_display_map.get(x, x))

    # --- 在庫情報フィルタの準備 ---
    if df3 is not None and df_master is not None:
        base_df_stock = df3.copy()
        master_cols_stock = ['商品ID', '大分類', '中分類', '小分類']
        if all(col in df_master.columns for col in master_cols_stock):
            cols_to_drop = ['大分類', '中分類', '小分類']
            df3_for_merge = df3.drop(columns=cols_to_drop, errors='ignore')
            df_master_stock = df_master[master_cols_stock].drop_duplicates(subset='商品ID')
            base_df_stock = pd.merge(df3_for_merge, df_master_stock, on='商品ID', how='left')
        
        st.sidebar.header(":blue[在庫情報フィルタ]")
        selected_daibunrui_stock = "すべて"
        if '大分類' in base_df_stock.columns:
            daibunrui_options_stock = base_df_stock['大分類'].dropna().unique().tolist()
            daibunrui_options_stock.sort()
            daibunrui_options_stock.insert(0, "すべて")
            selected_daibunrui_stock = st.sidebar.selectbox("大分類で絞り込み:", options=daibunrui_options_stock, key='daibunrui_stock')
        
        df_after_daibunrui_filter_stock = base_df_stock[base_df_stock['大分類'] == selected_daibunrui_stock] if selected_daibunrui_stock != "すべて" else base_df_stock
        selected_shobunrui_stock = []
        if '小分類' in df_after_daibunrui_filter_stock.columns:
            shobunrui_options_stock = df_after_daibunrui_filter_stock['小分類'].dropna().unique().tolist()
            shobunrui_options_stock.sort()
            selected_shobunrui_stock = st.sidebar.multiselect("小分類で絞り込み（複数選択可）:", options=shobunrui_options_stock, key='shobunrui_stock')
        
        df_after_shobunrui_filter_stock = df_after_daibunrui_filter_stock[df_after_daibunrui_filter_stock['小分類'].isin(selected_shobunrui_stock)] if selected_shobunrui_stock else df_after_daibunrui_filter_stock
        product_ids_input_stock = st.sidebar.text_input("商品IDで絞り込み (カンマ区切りで複数可):", key='product_id_stock').strip()
        selected_product_ids_stock = [pid.strip() for pid in product_ids_input_stock.split(',')] if product_ids_input_stock else []
        df_after_product_id_filter_stock = df_after_shobunrui_filter_stock[df_after_shobunrui_filter_stock['商品ID'].isin(selected_product_ids_stock)] if selected_product_ids_stock else df_after_shobunrui_filter_stock
        selected_quality_stock = "すべて"
        if '品質区分名' in df_after_product_id_filter_stock.columns:
            quality_options_stock = df_after_product_id_filter_stock['品質区分名'].dropna().unique().tolist()
            quality_options_stock.insert(0, "すべて")
            selected_quality_stock = st.sidebar.radio("品質区分名で絞り込み:", options=quality_options_stock, key='quality_stock')

    # ★★★【改修ポイント】★★★ ここからタブを作成
    tab_stock, tab_shipping = st.tabs(["📊 在庫情報", "📝 出荷情報"])

    # --- 在庫情報のタブ ---
    with tab_stock:
        st.header("📦 在庫情報")
        if df3 is not None and df_master is not None:
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
                                fig, ax = plt.subplots()
                                ax.pie(pie_data, labels=pie_data.index, autopct='%1.1f%%', startangle=90, textprops={'fontsize': 10}) 
                                ax.axis('equal')
                                st.pyplot(fig)
                            else:
                                st.warning("グラフ化できる在庫データがありません。")
                except Exception as e:
                    st.error(f"ピボットテーブルまたはグラフの作成中にエラーが発生しました: {e}")
            else:
                st.warning("在庫情報: 選択された条件に一致するデータがないか、必要な列が不足しています。")

    # --- 出荷情報のタブ ---
    with tab_shipping:
        st.header("🚚 出荷情報")
        if df1 is not None and df_master is not None:
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
                recent_cols = pivot.columns[-12:]
                pivot_filtered = pivot[pivot[recent_cols].sum(axis=1) != 0]
                pivot_display = pivot_filtered.loc[:, recent_cols]

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.info("ヒント: テーブルは直近12ヶ月合計が0でないデータを表示しています。")
                    st.dataframe(pivot_display.reset_index(), height=400, use_container_width=True)
                with col2:
                    st.write("グラフ（商品別積み上げ）")
                    chart_df_monthly = df_monthly_filtered.pivot_table(index='month_code', columns='商品名', values='合計出荷数', aggfunc='sum').fillna(0)
                    st.bar_chart(chart_df_monthly.iloc[-12:, :]) 
            else:
                st.warning("月間出荷: 選択された条件に一致するデータがないか、必要な列が不足しています。")

            # 週間出荷
            if df5 is not None:
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
                    recent_cols_weekly = pivot_weekly.columns[-12:]
                    pivot_weekly_filtered = pivot_weekly[pivot_weekly[recent_cols_weekly].sum(axis=1) != 0]
                    pivot_weekly_display = pivot_weekly_filtered.loc[:, recent_cols_weekly]

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.info("ヒント: テーブルは直近12週合計が0でないデータを表示しています。")
                        st.dataframe(pivot_weekly_display.reset_index(), height=400, use_container_width=True)
                    with col2:
                        st.write("グラフ（商品別積み上げ）")
                        chart_df_weekly = df_weekly_filtered.pivot_table(index='week_code', columns='商品名', values='合計出荷数', aggfunc='sum').fillna(0)
                        st.bar_chart(chart_df_weekly.iloc[-12:, :])
                else:
                    st.warning("週間出荷: 選択された条件に一致するデータがないか、必要な列が不足しています。")

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
    st.error(f"予期せぬエラーが発生しました: {e}")
