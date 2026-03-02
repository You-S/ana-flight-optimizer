import streamlit as st
import pandas as pd
import numpy as np


class DataLoader:
    """Class to handle loading and preprocessing of data."""

    @staticmethod
    @st.cache_data
    def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        try:
            mile_chart = pd.read_csv('マイルチャート.csv')
            booking_class = pd.read_csv('予約クラスと積算率.csv')
            status_bonus = pd.read_csv('ステイタス.csv')
            card_bonus = pd.read_csv('カードボーナス.csv')
            
            # Preprocessing
            if mile_chart['100%'].dtype == 'object':
                mile_chart['100%'] = mile_chart['100%'].astype(str).str.replace(',', '').astype(int)
            
            mile_chart['アジアオセアニアFLG'] = mile_chart['アジアオセアニアFLG'].fillna(0)
            
            return mile_chart, booking_class, status_bonus, card_bonus
            
        except FileNotFoundError as e:
            st.error(f"必要なCSVファイルが見つかりません。ファイル名と配置を確認してください: {e}")
            st.stop()
        except Exception as e:
            st.error(f"CSVファイルの読み込み中にエラーが発生しました: {e}")
            st.stop()


class PPSimulator:
    """Class to handle ANA Premium Points and Miles calculations."""

    # 400ポイント対象の予約クラス
    BOARDING_POINT_CLASSES = ['F', 'A', 'J', 'C', 'D', 'Z', 'E', 'G', 'Y', 'B', 'M']

    def __init__(self, mile_chart: pd.DataFrame, booking_class: pd.DataFrame):
        self.mile_chart = mile_chart
        self.booking_class = booking_class

    def get_route_info(self, route_name: str) -> dict:
        matched = self.mile_chart[self.mile_chart['路線（片道）'] == route_name]
        if matched.empty:
            raise ValueError(f"路線 '{route_name}' が見つかりません。")
        row = matched.iloc[0]
        return {
            'base_mile': row['100%'],
            'route_multiplier': 1.5 if row['アジアオセアニアFLG'] == 1.0 else 1.0
        }

    def get_accumulation_rate(self, booking_class_label: str) -> float:
        matched = self.booking_class[self.booking_class['予約クラス'] == booking_class_label]
        if matched.empty:
            raise ValueError(f"予約クラス '{booking_class_label}' が見つかりません。")
        return matched.iloc[0]['区間基本マイレージに対する積算率']
        
    def calculate_metrics(self, df: pd.DataFrame, final_bonus_rate: float) -> list[list]:
        results = []
        for idx, row in df.iterrows():
            try:
                # 出発地から目的地までのすべての指定された区間をリスト化する
                # 経由地(東京)がある場合は2区間、ない場合は1区間
                route_legs = []
                if pd.notna(row['出発地']) and row['出発地'] != "東京":
                    route_legs.append(row['出発地'])
                if pd.notna(row['目的地']) and row['目的地'] != "東京":
                    route_legs.append(row['目的地'])
                
                if not route_legs:
                     raise ValueError("有効な路線が選択されていません。")

                acc_rate = self.get_accumulation_rate(row['予約クラス'])
                boarding_point_eligible = row['予約クラス'] in self.BOARDING_POINT_CLASSES
                
                # 往復フラグ
                multiplier = 2 if row['往復'] else 1
                
                total_pp_one_way = 0
                total_miles_one_way = 0
                
                # 登録された各区間（レグ）に対して個別にPPとマイルを計算・加算する
                for leg in route_legs:
                    route_info = self.get_route_info(leg)
                    base_mile = route_info['base_mile']
                    route_multiplier = route_info['route_multiplier']
                    
                    # Boarding Points (対象クラスなら各搭乗区間ごとに400pt)
                    leg_boarding_point = 400 if boarding_point_eligible else 0
                    
                    # --- PP Calculation (端数は切り捨て) ---
                    # 区間基本マイレージ × クラス・運賃倍率 × 路線倍率 ＋ 搭乗ポイント
                    leg_pp_one_way = int(base_mile * acc_rate * route_multiplier) + leg_boarding_point
                    
                    # 片道分を合算
                    total_pp_one_way += leg_pp_one_way
                    
                    # --- Mile Calculation (端数は切り捨て) ---
                    # 1. 積算マイル（区間基本マイレージ × クラス・運賃倍率）
                    leg_accumulated_mile_one_way = int(base_mile * acc_rate)
                    
                    # 2. ボーナスマイル（区間基本マイレージ × クラス・運賃倍率 × ボーナス率）
                    leg_bonus_mile_one_way = int(base_mile * acc_rate * final_bonus_rate)
                    
                    # 3. レグ片道あたりの合計獲得マイル
                    leg_total_mile_one_way = leg_accumulated_mile_one_way + leg_bonus_mile_one_way
                    
                    # 片道分を合算
                    total_miles_one_way += leg_total_mile_one_way

                # 往復の場合、片道合計を2倍する
                total_pp = total_pp_one_way * multiplier
                total_miles = total_miles_one_way * multiplier

                # Mile Return Rate
                payment = row['支払金額']
                mile_return_rate = (total_miles / payment) * 100 if payment > 0 else 0
                
                # PP Unit Price
                pp_unit_price = payment / total_pp if total_pp > 0 else 0
                
                # Aptitude evaluation
                aptitude = self.evaluate_aptitude(pp_unit_price)
                
                results.append([
                    total_pp, 
                    total_miles, 
                    round(mile_return_rate, 1), 
                    round(pp_unit_price, 2), 
                    aptitude
                ])
                
            except ValueError as e:
                # エラー発生時はゼロやエラー文言を入れて続行する
                results.append([0, 0, 0, 0.0, f"エラー: {str(e)}"])
                
        return results
        
    @staticmethod
    def evaluate_aptitude(pp_unit_price: float) -> str:
        if pp_unit_price == 0:
            return "判定不能"
        elif pp_unit_price <= 10:
            return "極めて高い"
        elif pp_unit_price <= 15:
            return "普通"
        else:
            return "低い"


# --- Styling Functions ---
def apply_color_styles(val):
    if isinstance(val, (int, float)):
        if 0 < val <= 10:
            return 'background-color: #d4edda; color: #155724; font-weight: bold'  # Green
        elif val > 15:
            return 'background-color: #f8d7da; color: #721c24; font-weight: bold'  # Red
    return ''

def apply_aptitude_styles(val):
    if val == "極めて高い":
        return 'background-color: #d4edda; color: #155724; font-weight: bold'
    elif val == "低い":
        return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
    elif "エラー" in str(val):
        return 'background-color: #fff3cd; color: #856404;'
    return ''


def main():
    st.set_page_config(page_title="ANA国際線シミュレーター", layout="wide")
    
    # Custom CSS for ANA Brand Colors
    st.markdown("""
        <style>
        /* ANA Brand Colors - Light Mode Defaults */
        :root {
            --triton-blue: #002776;
            --mohican-blue: #00A0E9;
            --light-blue-bg: #F0F8FF;
        }
        
        /* Dark Mode Adjustments */
        @media (prefers-color-scheme: dark) {
            :root {
                --triton-blue: #66B2FF; /* Lighter sky blue for readability in dark mode */
                --mohican-blue: #33B5E5; 
                --light-blue-bg: #0D1623; /* Dark slate background for sidebar */
            }
        }

        /* Text Headers */
        h1, h2, h3 {
            color: var(--triton-blue) !important;
        }
        /* Main Accent Border */
        hr {
            border-top: 3px solid var(--mohican-blue) !important;
            margin-top: 0.5em !important;
            margin-bottom: 1.5em !important;
        }
        /* Colored Info Boxes */
        div[data-testid="stExpander"] summary {
            color: var(--triton-blue);
            font-weight: bold;
        }
        /* Subtle Sidebar */
        [data-testid="stSidebar"] {
            background-color: var(--light-blue-bg);
            border-right: 1px solid var(--mohican-blue);
        }
        </style>
    """, unsafe_allow_html=True)

    # Header section with title overlay on image
    import base64
    try:
        with open("ana_wing_photo.jpg", "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        
        st.markdown(f"""
            <div style="position: relative; border-radius: 8px; overflow: hidden; margin-bottom: 20px;">
                <img src="data:image/jpeg;base64,{img_b64}" style="width: 100%; display: block;">
                <div style="position: absolute; top: 10%; right: 5%; text-align: right; text-shadow: 2px 2px 8px rgba(0,0,0,0.8), 0px 0px 15px rgba(0,0,0,0.5);">
                    <div style="color: #FFFFFF !important; font-size: clamp(1.8rem, 4vw, 3.5rem); font-weight: 800; margin-bottom: 0; line-height: 1.2; letter-spacing: 0.05em;">✈️ ANA 国際線</div>
                    <div style="color: #FFFFFF !important; font-size: clamp(1.8rem, 4vw, 3.5rem); font-weight: 800; margin-top: 0; line-height: 1.2; letter-spacing: 0.05em;">PP & Mile Simulator</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    except Exception:
        # Fallback if image is missing
        st.title("✈️ ANA 国際線\nPP & Mile Simulator")
        
    st.markdown("---")

    # データとシミュレーターのロード
    mile_chart, booking_class, status_bonus, card_bonus = DataLoader.load_data()
    simulator = PPSimulator(mile_chart, booking_class)

    # UI用 リスト変換（Pandasのunique配列がStreamlit1.32以降でValueErrorを起こす対策）
    status_list = status_bonus['ステイタス'].dropna().unique().tolist()
    card_list = card_bonus['カード種別'].dropna().unique().tolist()
    route_list = mile_chart['路線（片道）'].dropna().unique().tolist()
    class_list = booking_class['予約クラス'].dropna().unique().tolist()

    # === サイドバー：ユーザー属性 ===
    st.sidebar.header("👤 Your Status (Global Setting)")
    selected_status = st.sidebar.selectbox("現在のステイタス", status_list)
    selected_card = st.sidebar.selectbox("所有ANAカード", card_list)

    # ステイタスとカードに基づくボーナス率（倍率）の計算
    has_card = selected_card != "カード無し"
    
    # ステイタスボーナスの取得
    status_row = status_bonus[status_bonus['ステイタス'] == selected_status].iloc[0]
    # 対象ステイタスにカードがない場合の倍率 または ある場合の倍率
    status_rate = float(status_row['倍率']) if has_card else float(status_row['ANAカード無し'])
    
    # カードボーナスの取得
    card_rate = float(card_bonus[card_bonus['カード種別'] == selected_card].iloc[0]['付与ボーナス'])

    # ボーナスは高い方が優先して適用される
    final_bonus_rate = max(status_rate, card_rate)

    st.sidebar.info(f"適用ボーナス率: **{int(round(final_bonus_rate * 100))}%**\n\n(ステイタス: {int(round(status_rate*100))}% / カード: {int(round(card_rate*100))}%)")

    # === メイン画面：ルート比較 ===
    st.subheader("📊 Route Comparison (修行ルート比較)")
    st.write("比較したいルートと運賃を入力してください。「東京」を発着とする単純往復のほか、海外発券（例：ジャカルタ発・東京経由・メキシコシティ行き）のような複数区間の組み合わせも可能です。")

    # デフォルトの入力データ
    if 'input_df' not in st.session_state:
        st.session_state.input_df = pd.DataFrame({
            '出発地': ['東京', 'ジャカルタ'],
            '目的地': ['メキシコシティ', 'メキシコシティ'],
            '予約クラス': ['E', 'K'],
            '支払金額': [250000, 180000],
            '往復': [True, True]
        })

    # 表示用リストに東京を追加 (CSVには片道先の都市名しか入っていないため)
    location_list = ['東京'] + route_list

    # データエディタ（複数行入力・比較UI）
    edited_df = st.data_editor(
        st.session_state.input_df,
        num_rows="dynamic",
        column_config={
            "出発地": st.column_config.SelectboxColumn("出発地", options=location_list, required=True),
            "目的地": st.column_config.SelectboxColumn("目的地（経由後の最終目的）", options=location_list, required=True),
            "予約クラス": st.column_config.SelectboxColumn("予約クラス", options=class_list, required=True),
            "支払金額": st.column_config.NumberColumn("支払金額 (JPY)", min_value=0, format="¥%d", required=True),
            "往復": st.column_config.CheckboxColumn("往復（全区間）")
        },
        use_container_width=True
    )

    # === 計算と結果の表示 ===
    if not edited_df.empty:
        calc_results = simulator.calculate_metrics(edited_df, final_bonus_rate)
        
        cols = ['獲得PP', '獲得マイル', 'マイル還元率', 'PP単価', '修行適性']
        res_df = pd.DataFrame(calc_results, columns=cols)
        
        display_df = pd.concat([edited_df.reset_index(drop=True), res_df], axis=1)

        st.markdown("### 🏆 計算結果")
        
        # applymap は Pandas >= 2.1.0 で非推奨となり map に変更されたため hasattr で両対応
        style_method = display_df.style.map if hasattr(display_df.style, 'map') else display_df.style.applymap
        
        styled_df = style_method(
            apply_color_styles, subset=['PP単価']
        ).map(
            apply_aptitude_styles, subset=['修行適性']
        ) if hasattr(display_df.style, 'map') else display_df.style.applymap(
            apply_color_styles, subset=['PP単価']
        ).applymap(
            apply_aptitude_styles, subset=['修行適性']
        )
        
        styled_df = styled_df.format({
            "支払金額": "¥{:,.0f}",
            "マイル還元率": "{:.1f}%",
            "獲得PP": "{:,.0f}",
            "獲得マイル": "{:,.0f}",
            "PP単価": "¥{:.2f}"
        })
        
        st.dataframe(styled_df, use_container_width=True)

        # 最適路線のサマリー（エラー行は除外）
        valid_df = display_df[~display_df['修行適性'].astype(str).str.contains("エラー|判定不能")]
        
        if not valid_df.empty:
            best_idx = valid_df['PP単価'].idxmin()
            best_row = valid_df.loc[best_idx]
            
            # 発着地を結合したサマリー文字列
            route_str = f"{best_row['出発地']} ⇔ {best_row['目的地']}"
            if best_row['出発地'] != '東京' and best_row['目的地'] != '東京':
                route_str = f"{best_row['出発地']} ⇔ (東京経由) ⇔ {best_row['目的地']}"
                
            summary_msg = f"**{route_str} (クラス{best_row['予約クラス']})** / PP単価: ¥{best_row['PP単価']:.2f}"
            
            if best_row['PP単価'] <= 10:
                st.success(f"💡 【超優秀】最も効率が良いのは {summary_msg} です！緑色の修行適性です。")
            elif best_row['PP単価'] <= 15:
                st.info(f"💡 最も効率が良いのは {summary_msg} です。")
            else:
                st.warning(f"💡 最も効率が良いのは {summary_msg} ですが、全体としてPP単価が15円を超えており修行向きではありません（赤色）。")

    # === ロジック解説エリア ===
    with st.expander("🛠 Antigravity の視点 (ロジック解説)"):
        st.write("""
        - **PP計算式**: `(基本マイル × 積算率 × 路線倍率) + 搭乗ポイント`
        - **マイル計算式**: `(基本マイル × 積算率) + ボーナスマイル(適用ボーナス率)`
        - **適用ボーナス率**: ステイタスとカード種別のうち、**高い方の倍率**のみを適用。（例：ステイタス120%, カード50% → 120%を適用）
        - **路線倍率**: アジア・オセアニア路線は一律1.5倍、その他は1.0倍で計算しています。
        - **搭乗ポイント**: 予約クラス(F, A, J, C, D, Z, E, G, Y, B, M)に基づき、各搭乗区間ごとに「400pt」を自動加算。
        - **海外発券の計算**: 出発地と目的地がいずれも「東京」以外の場合、自動的に東京を経由する2区間（例：ジャカルタ→東京 ＋ 東京→メキシコシティ）として合算し計算しています。片道でも2フライト分の搭乗ポイントが加算されます。
        - **マイル還元率**: 支払った航空券代に対して、何％がマイルとして還元されるか（`獲得マイル ÷ 支払金額 × 100`）を算出しています。
        - **修行適性の判定**: PP単価10円以下は「極めて高い（緑）」、15円超は「低い（赤）」として直感的に比較できるように色付けしています。
        """)


if __name__ == "__main__":
    main()
