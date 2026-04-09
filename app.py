import streamlit as st
import feedparser
import json
import google.generativeai as genai
from datetime import datetime
from github import Github
import pandas as pd

# 1. 보안 설정 불러오기
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["GITHUB_REPO"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    ADMIN_PW = st.secrets["ADMIN_PASSWORD"]
except Exception as e:
    st.error("⚠️ 시크릿(Secrets) 설정이 완료되지 않았습니다. Streamlit 설정에서 키를 입력해주세요.")
    st.stop()

# 2. 서비스 연결 (GitHub & Gemini)
g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)
genai.configure(api_key=GEMINI_API_KEY)

# --- 깃허브 파일 읽기/쓰기 함수 ---
def load_json(file_path, default):
    try:
        content = repo.get_contents(file_path)
        return json.loads(content.decoded_content.decode('utf-8')), content.sha
    except:
        return default, None

def save_json(file_path, data, sha, message):
    json_string = json.dumps(data, indent=4, ensure_ascii=False)
    if sha:
        repo.update_file(file_path, message, json_string, sha)
    else:
        repo.create_file(file_path, message, json_string)

# --- 메인 화면 시작 ---
st.set_page_config(page_title="나만의 AI 뉴스룸", layout="wide")

# 접속자 통계 업데이트
stats, s_sha = load_json("stats.json", {"total_views": 0, "daily_views": {}})
today = datetime.now().strftime("%Y-%m-%d")
if 'visited' not in st.session_state:
    stats["total_views"] += 1
    stats["daily_views"][today] = stats["daily_views"].get(today, 0) + 1
    save_json("stats.json", stats, s_sha, "방문자 통계 업데이트")
    st.session_state['visited'] = True

# 사이드바 메뉴
menu = st.sidebar.selectbox("메뉴 선택", ["뉴스룸 메인", "관리자 대시보드"])

if menu == "뉴스룸 메인":
    st.title("🗞️ 오늘의 IT 뉴스 브리핑")
    news_db, _ = load_json("news_data.json", {})
    
    # 날짜 선택
    date_choice = st.date_input("보고 싶은 날짜를 선택하세요", datetime.now())
    date_str = date_choice.strftime("%Y-%m-%d")
    
    if date_str in news_db:
        st.markdown(news_db[date_str])
    else:
        st.info(f"📍 {date_str}에는 생성된 리포트가 없습니다. 관리자 메뉴에서 [분석 실행]을 눌러주세요.")

elif menu == "관리자 대시보드":
    st.title("⚙️ 관리자 대시보드")
    pw = st.text_input("관리자 암호를 입력하세요", type="password")
    
    if pw == ADMIN_PW:
        tab1, tab2, tab3 = st.tabs(["RSS 관리", "AI 분석 실행", "통계 보기"])
        
        with tab1:
            st.subheader("구독할 RSS 피드 관리")
            feeds, f_sha = load_json("feeds.json", [])
            
            with st.form("add_feed"):
                name = st.text_input("언론사/사이트 이름")
                url = st.text_input("RSS 주소(XML URL)")
                if st.form_submit_button("추가하기"):
                    feeds.append({"name": name, "url": url})
                    save_json("feeds.json", feeds, f_sha, "새 RSS 피드 추가")
                    st.success("피드가 저장되었습니다!")
            
            st.write("현재 등록된 피드:")
            st.table(pd.DataFrame(feeds)) if feeds else st.write("등록된 피드가 없습니다.")

        with tab2:
            st.subheader("AI 뉴스 수집 및 분석")
            if st.button("뉴스 분석 시작 (수 분 소요될 수 있음)"):
                feeds, _ = load_json("feeds.json", [])
                if not feeds:
                    st.error("먼저 RSS 피드를 하나 이상 등록해주세요!")
                else:
                    with st.spinner("AI가 뉴스를 읽고 요약하는 중..."):
                        # 1. 뉴스 수집
                        all_news = ""
                        for f in feeds:
                            parsed = feedparser.parse(f['url'])
                            for entry in parsed.entries[:10]:
                                # 제목과 요약을 합쳐서 전달
                                title = entry.get('title', '')
                                summary = entry.get('summary', '')[:100]
                                all_news += f"[{f['name']}] {title}\n{summary}\n\n"
                        
                        if not all_news.strip():
                            st.error("수집된 뉴스 내용이 없습니다. RSS 주소를 확인해주세요.")
                            st.stop()

                        try:
                            # 2. AI 분석 (모델 명칭을 더 안정적인 것으로 변경)
                            # 'gemini-1.5-flash' 대신 'models/gemini-1.5-flash'를 시도하거나
                            # 가장 기본인 'gemini-1.5-flash'를 사용합니다.
                            model = genai.GenerativeModel('gemini-1.5-flash') 
                            
                            prompt = f"""
                            너는 공인중개사와 투자 전문가를 위한 부동산 전문 편집장이야. 
                            오늘 뉴스 중에서 아파트 청약 정보, 정부의 부동산 정책 변화, 금리 관련 소식을 중점적으로 요약해줘.
                            형식은 가독성 좋은 마크다운(Markdown)을 사용해.
                            
                            뉴스 내용:
                            {all_news}
                            """
                            
                            response = model.generate_content(prompt)
                            
                            # 3. 결과 저장
                            news_db, n_sha = load_json("news_data.json", {})
                            news_db[today] = response.text
                            save_json("news_data.json", news_db, n_sha, f"{today} 뉴스 분석 완료")
                            st.success("분석 완료! 메인 화면에서 확인하세요.")
                            st.markdown(response.text)
                            
                        except Exception as e:
                            st.error(f"AI 분석 중 오류가 발생했습니다: {e}")
                            st.info("Tip: API 키가 올바른지, 혹은 Google AI Studio에서 'Gemini 1.5 Flash' 모델이 활성화 되어있는지 확인해주세요.")

        with tab3:
            st.metric("누적 방문수", stats["total_views"])
            if stats["daily_views"]:
                st.line_chart(pd.DataFrame(list(stats["daily_views"].items()), columns=['날짜', '방문수']).set_index('날짜'))
