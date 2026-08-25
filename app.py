import io
import os
import textwrap
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="알뜰 장보기 미션",
    page_icon="🛒",
    layout="wide",
)

PRODUCT_FILE = Path("products.csv")

MISSIONS = {
    "🍛 카레 만들기": {
        "budget": 15000,
        "description": "맛있는 카레를 만들기 위해 필요한 재료를 골라 보세요!",
    },
    "🏕️ 캠핑 준비하기": {
        "budget": 30000,
        "description": "친구들과 즐거운 캠핑을 떠나요. 필요한 물건을 준비해 보세요!",
    },
    "🎂 친구 생일파티 준비하기": {
        "budget": 25000,
        "description": "친구의 생일파티를 멋지게 준비해 보세요!",
    },
}


# =========================================================
# 유틸리티
# =========================================================
def money(value):
    return f"{int(value):,}원"


def load_products():
    """products.csv를 읽어 상품 정보를 가져옵니다."""
    if not PRODUCT_FILE.exists():
        st.error(
            "products.csv 파일을 찾을 수 없습니다. "
            "app.py와 같은 폴더에 products.csv를 넣어 주세요."
        )
        st.stop()

    df = pd.read_csv(PRODUCT_FILE)

    required_columns = ["품명", "가격", "이미지 url"]
    missing = [col for col in required_columns if col not in df.columns]

    if missing:
        st.error(
            "products.csv에 다음 열이 필요합니다: "
            + ", ".join(required_columns)
            + f" / 현재 누락된 열: {', '.join(missing)}"
        )
        st.stop()

    df["품명"] = df["품명"].astype(str)
    df["가격"] = pd.to_numeric(df["가격"], errors="coerce").fillna(0).astype(int)
    df["이미지 url"] = df["이미지 url"].fillna("").astype(str)

    # 상품을 구분하기 위한 내부 ID
    df = df.reset_index(drop=True)
    df["상품ID"] = df.index.astype(int)

    return df


def init_state():
    if "page" not in st.session_state:
        st.session_state.page = "start"

    if "mission" not in st.session_state:
        st.session_state.mission = None

    if "cart" not in st.session_state:
        # {상품ID: {"name": ..., "price": ..., "image_url": ..., "qty": ...}}
        st.session_state.cart = {}

    if "reason" not in st.session_state:
        st.session_state.reason = ""


def start_mission(mission_name):
    st.session_state.mission = mission_name
    st.session_state.cart = {}
    st.session_state.reason = ""
    st.session_state.page = "shop"


def go_start():
    st.session_state.page = "start"
    st.session_state.mission = None
    st.session_state.cart = {}
    st.session_state.reason = ""


def cart_total():
    return sum(
        item["price"] * item["qty"]
        for item in st.session_state.cart.values()
    )


def add_to_cart(product_id, name, price, image_url, qty):
    if qty <= 0:
        return

    if product_id in st.session_state.cart:
        st.session_state.cart[product_id]["qty"] += qty
    else:
        st.session_state.cart[product_id] = {
            "name": name,
            "price": price,
            "image_url": image_url,
            "qty": qty,
        }


def change_cart_quantity(product_id, delta):
    if product_id not in st.session_state.cart:
        return

    st.session_state.cart[product_id]["qty"] += delta

    if st.session_state.cart[product_id]["qty"] <= 0:
        del st.session_state.cart[product_id]


def get_font(size=32, bold=False):
    """한글 표시가 가능한 시스템 폰트를 찾아 사용합니다."""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
    ]

    # 굵은 글꼴을 먼저 찾고 싶을 때
    if bold:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "C:/Windows/Fonts/malgunbd.ttf",
        ] + candidates

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass

    # 한글 폰트가 없을 경우 기본 폰트 사용
    return ImageFont.load_default()


@st.cache_data(show_spinner=False)
def download_image(url):
    """상품 이미지 URL에서 이미지를 받아옵니다."""
    if not url or url.lower() == "nan":
        return None

    try:
        response = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception:
        return None


def make_result_image(mission_name, budget, cart, total, reason):
    """
    결과 화면을 PNG 이미지로 제작합니다.
    PIL을 이용하므로 학생이 '그림으로 저장'을 눌러 바로 다운로드할 수 있습니다.
    """
    width = 1200
    title_font = get_font(48, bold=True)
    sub_font = get_font(30, bold=True)
    normal_font = get_font(25)
    small_font = get_font(21)

    item_height = 170
    header_height = 230
    reason_height = 180
    footer_height = 170
    height = (
        header_height
        + max(len(cart), 1) * item_height
        + reason_height
        + footer_height
    )

    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    # 제목 영역
    draw.rectangle((0, 0, width, header_height), fill=(240, 247, 255))
    draw.text(
        (60, 35),
        f"미션: {mission_name}",
        font=title_font,
        fill=(30, 60, 100),
    )
    draw.text(
        (60, 115),
        f"예산 {money(budget)}   |   사용 금액 {money(total)}   |   남은 돈 {money(budget - total)}",
        font=normal_font,
        fill=(40, 40, 40),
    )

    # 상품 목록
    y = header_height

    if not cart:
        draw.text(
            (60, y + 50),
            "구매한 물건이 없습니다.",
            font=normal_font,
            fill=(80, 80, 80),
        )
        y += item_height
    else:
        for item in cart.values():
            draw.line((50, y, width - 50, y), fill=(220, 220, 220), width=2)

            img = download_image(item["image_url"])
            if img is not None:
                img.thumbnail((120, 120))
                x_img = 70 + (120 - img.width) // 2
                y_img = y + 20 + (120 - img.height) // 2
                canvas.paste(img, (x_img, y_img))

            text_x = 230
            draw.text(
                (text_x, y + 25),
                item["name"],
                font=sub_font,
                fill=(30, 30, 30),
            )
            draw.text(
                (text_x, y + 75),
                f"수량 {item['qty']}개 × {money(item['price'])}",
                font=normal_font,
                fill=(70, 70, 70),
            )
            draw.text(
                (text_x, y + 112),
                f"합계 {money(item['qty'] * item['price'])}",
                font=small_font,
                fill=(70, 100, 140),
            )

            y += item_height

    # 구매 이유
    draw.line((50, y, width - 50, y), fill=(220, 220, 220), width=2)
    draw.text(
        (60, y + 25),
        "📝 내가 이렇게 장을 본 이유",
        font=sub_font,
        fill=(30, 60, 100),
    )

    reason_text = reason.strip()
    if not reason_text:
        reason_text = "작성하지 않았습니다."

    # 줄바꿈
    max_chars = 42
    lines = textwrap.wrap(reason_text, width=max_chars)
    for i, line in enumerate(lines[:4]):
        draw.text(
            (70, y + 75 + i * 32),
            line,
            font=normal_font,
            fill=(60, 60, 60),
        )

    # 하단
    footer_y = height - footer_height
    draw.line((50, footer_y, width - 50, footer_y), fill=(220, 220, 220), width=2)
    draw.text(
        (60, footer_y + 30),
        "🛒 알뜰 장보기 미션 완료!",
        font=title_font,
        fill=(40, 100, 70),
    )

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    output.seek(0)
    return output.getvalue()


# =========================================================
# 화면 1. 시작 화면
# =========================================================
def show_start_page():
    st.title("🛒 알뜰 장보기 미션")
    st.subheader("오늘의 장보기 미션을 골라 보세요!")
    st.write("주어진 예산 안에서 꼭 필요한 물건을 똑똑하게 골라 봅시다. 😊")

    st.divider()

    cols = st.columns(3)

    for col, (mission_name, info) in zip(cols, MISSIONS.items()):
        with col:
            st.markdown(f"### {mission_name}")
            st.info(info["description"])
            st.markdown(f"**예산: {money(info['budget'])}**")

            if st.button(
                "이 미션 시작하기",
                key=f"start_{mission_name}",
                use_container_width=True,
            ):
                start_mission(mission_name)
                st.rerun()


# =========================================================
# 화면 2. 쇼핑 화면
# =========================================================
def show_shop_page(products):
    mission_name = st.session_state.mission
    budget = MISSIONS[mission_name]["budget"]
    total = cart_total()
    remaining = budget - total

    st.title("🛍️ 장보기")
    st.markdown(f"## 미션: **{mission_name}**")

    top1, top2, top3 = st.columns(3)
    top1.metric("미션 예산", money(budget))
    top2.metric("현재 사용 금액", money(total))
    top3.metric("남은 예산", money(remaining))

    if remaining < 0:
        st.error(
            f"⚠️ 예산을 {money(abs(remaining))} 초과했습니다. "
            "장바구니에서 물건을 줄여 주세요."
        )
    else:
        st.success(f"예산 안에서 {money(remaining)} 남았습니다!")

    st.divider()
    st.subheader("🏪 상품을 골라 보세요")

    # 상품 진열
    columns_per_row = 4

    for start in range(0, len(products), columns_per_row):
        row = products.iloc[start:start + columns_per_row]
        cols = st.columns(columns_per_row)

        for col, (_, product) in zip(cols, row.iterrows()):
            product_id = int(product["상품ID"])

            with col:
                image = download_image(product["이미지 url"])

                if image is not None:
                    st.image(image, use_container_width=True)
                else:
                    st.markdown(
                        "<div style='height:180px;display:flex;"
                        "align-items:center;justify-content:center;"
                        "background:#f2f2f2;border-radius:10px;'>"
                        "🖼️<br>이미지를 불러올 수 없음"
                        "</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown(f"**{product['품명']}**")
                st.write(f"가격: **{money(product['가격'])}**")

                # 상품별 선택 수량
                qty_key = f"qty_{product_id}"
                if qty_key not in st.session_state:
                    st.session_state[qty_key] = 1

                q1, q2, q3 = st.columns([1, 1, 1])
                with q1:
                    if st.button("−", key=f"minus_{product_id}", use_container_width=True):
                        st.session_state[qty_key] = max(
                            1, st.session_state[qty_key] - 1
                        )
                        st.rerun()

                with q2:
                    st.markdown(
                        f"<div style='text-align:center;padding-top:6px;'>"
                        f"<b>{st.session_state[qty_key]}</b>개</div>",
                        unsafe_allow_html=True,
                    )

                with q3:
                    if st.button("+", key=f"plus_{product_id}", use_container_width=True):
                        st.session_state[qty_key] += 1
                        st.rerun()

                if st.button(
                    "🛒 장바구니 담기",
                    key=f"add_{product_id}",
                    use_container_width=True,
                ):
                    add_to_cart(
                        product_id,
                        product["품명"],
                        int(product["가격"]),
                        product["이미지 url"],
                        st.session_state[qty_key],
                    )
                    st.toast(f"{product['품명']}을(를) 장바구니에 담았습니다!")

        st.write("")

    # 장바구니
    st.divider()
    st.subheader("🛒 장바구니")

    if not st.session_state.cart:
        st.info("아직 담은 물건이 없습니다. 상품을 골라 장바구니에 담아 보세요!")
    else:
        for product_id, item in list(st.session_state.cart.items()):
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 2])

            with c1:
                st.write(f"**{item['name']}**")

            with c2:
                st.write(money(item["price"]))

            with c3:
                st.write(f"{item['qty']}개")

            with c4:
                st.write(money(item["price"] * item["qty"]))

            with c5:
                m, p = st.columns(2)
                with m:
                    if st.button("−", key=f"cart_minus_{product_id}"):
                        change_cart_quantity(product_id, -1)
                        st.rerun()
                with p:
                    if st.button("+", key=f"cart_plus_{product_id}"):
                        change_cart_quantity(product_id, 1)
                        st.rerun()

        st.markdown(f"### 장바구니 합계: **{money(total)}**")

    # 제출
    st.divider()

    submit_disabled = (not st.session_state.cart) or (total > budget)

    if total > budget:
        st.warning("⚠️ 예산을 초과했습니다. 물건의 수량을 줄인 후 제출해 주세요.")
    elif not st.session_state.cart:
        st.warning("물건을 하나 이상 장바구니에 담아 주세요.")

    if st.button(
        "✅ 장보기 결과 제출하기",
        disabled=submit_disabled,
        use_container_width=True,
        type="primary",
    ):
        st.session_state.page = "result"
        st.session_state.reason = ""
        st.rerun()

    if st.button("← 미션 다시 선택하기", use_container_width=True):
        go_start()
        st.rerun()


# =========================================================
# 화면 3. 결과 화면
# =========================================================
def show_result_page():
    mission_name = st.session_state.mission
    budget = MISSIONS[mission_name]["budget"]
    total = cart_total()
    remaining = budget - total

    st.title("🎉 장보기 미션 결과")
    st.markdown(f"## 미션: **{mission_name}**")

    st.success("장보기 결과가 제출되었습니다!")

    st.subheader("🛍️ 내가 구매한 물건")

    for item in st.session_state.cart.values():
        c1, c2, c3 = st.columns([1, 3, 2])

        with c1:
            image = download_image(item["image_url"])
            if image is not None:
                st.image(image, width=100)
            else:
                st.write("🖼️")

        with c2:
            st.markdown(f"**{item['name']}**")
            st.write(f"수량: {item['qty']}개")

        with c3:
            st.write(f"개당 가격: {money(item['price'])}")
            st.write(f"상품 합계: **{money(item['price'] * item['qty'])}**")

    st.divider()

    r1, r2, r3 = st.columns(3)
    r1.metric("예산", money(budget))
    r2.metric("사용한 금액", money(total))
    r3.metric("남은 돈", money(remaining))

    st.divider()

    st.subheader("📝 내가 이렇게 장을 본 이유")
    st.write("고른 물건이 왜 필요했는지, 또는 예산을 어떻게 사용했는지 적어 보세요.")

    reason = st.text_area(
        "구매 이유",
        value=st.session_state.reason,
        placeholder="예: 카레를 만들려면 감자와 당근이 꼭 필요하고, 남은 돈으로 우유도 살 수 있기 때문입니다.",
        height=130,
        key="reason_input",
    )
    st.session_state.reason = reason

    if reason.strip():
        st.success("구매 이유를 작성했어요! 이제 결과를 그림으로 저장할 수 있습니다.")

        image_bytes = make_result_image(
            mission_name,
            budget,
            st.session_state.cart,
            total,
            reason,
        )

        st.download_button(
            label="🖼️ 그림으로 저장",
            data=image_bytes,
            file_name="장보기_미션_결과.png",
            mime="image/png",
            use_container_width=True,
            type="primary",
        )
    else:
        st.info("구매 이유를 작성하면 '그림으로 저장' 버튼이 나타납니다.")

    st.divider()

    if st.button("🛒 다시 장보기", use_container_width=True):
        st.session_state.page = "shop"
        st.session_state.cart = {}
        st.session_state.reason = ""
        st.rerun()

    if st.button("🏠 처음으로 돌아가기", use_container_width=True):
        go_start()
        st.rerun()


# =========================================================
# 실행
# =========================================================
init_state()
products = load_products()

if st.session_state.page == "start":
    show_start_page()
elif st.session_state.page == "shop":
    show_shop_page(products)
elif st.session_state.page == "result":
    show_result_page()
