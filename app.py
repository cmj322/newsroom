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
            
            # 1. 피드 추가 양식
            with st.form("add_feed"):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input("언론사/사이트 이름")
                with col2:
                    url = st.text_input("RSS 주소(XML URL)")
                if st.form_submit_button("추가하기"):
                    if name and url:
                        feeds.append({"name": name, "url": url})
                        save_json("feeds.json", feeds, f_sha, "새 RSS 피드 추가")
                        st.success(f"'{name}' 피드가 추가되었습니다!")
                        st.rerun() # 화면 새로고침
                    else:
                        st.error("이름과 URL을 모두 입력해주세요.")
            
            st.divider() # 구분선
            
            # 2. 개별 피드 삭제 기능
            if feeds:
                st.subheader("등록된 피드 삭제")
                # 피드 이름들만 리스트로 만듭니다.
                feed_names = [f['name'] for f in feeds]
                selected_feed = st.selectbox("삭제할 피드를 선택하세요", feed_names)
                
                if st.button("선택한 피드 삭제"):
                    # 선택한 이름을 제외한 나머지 피드들만 남깁니다.
                    new_feeds = [f for f in feeds if f['name'] != selected_feed]
                    save_json("feeds.json", new_feeds, f_sha, f"피드 삭제: {selected_feed}")
                    st.success(f"'{selected_feed}' 피드가 삭제되었습니다.")
                    st.rerun() # 화면 새로고침
                
                st.write("현재 등록된 피드 목록:")
                st.table(pd.DataFrame(feeds))
            else:
                st.info("현재 등록된 피드가 없습니다. 위 양식에서 추가해주세요.")

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
                            for entry in parsed.entries[:5]:
                                title = entry.get('title', '')
                                summary = entry.get('description', '')[:100] # summary 대신 description 사용 시도
                                all_news += f"[{f['name']}] {title}\n{summary}\n\n"
                        
                        if not all_news.strip():
                            st.error("수집된 뉴스 내용이 없습니다. RSS 주소를 확인해주세요.")
                            st.stop()

                        with st.expander("🛠️ 디버깅: 내 API 키로 사용 가능한 모델 목록"):
                            try:
                                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                                st.write(models)
                            except Exception as debug_e:
                                st.error(f"모델 목록을 가져오는 데 실패했습니다: {debug_e}")
                        
                        try:
                            # 2. AI 분석 (가장 표준적인 모델명 사용)
                            # 'models/gemini-1.5-flash' 대신 'gemini-1.5-flash'만 입력해보세요.
                            model = genai.GenerativeModel(model_name='models/gemini-2.5-flash') 
                            
                            prompt = f"""
                            너는 전문 뉴스 편집장이야. 아래 뉴스 내용들을 바탕으로 오늘 핵심 이슈 3가지를 정리해주고, 
                            전체적인 내용을 뉴스레터 형식으로 요약해줘.
                            
                            내용:
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
                            # 에러 발생 시 상세 메시지 출력
                            st.error(f"AI 분석 중 오류가 발생했습니다: {e}")
                            st.info("해결 방법: 구글 AI 스튜디오(aistudio.google.com)에서 API 키가 'Gemini 2.0 Flash' 모델을 지원하는지 확인해주세요.")
                            
        with tab3:
            st.metric("누적 방문수", stats["total_views"])
            if stats["daily_views"]:
                st.line_chart(pd.DataFrame(list(stats["daily_views"].items()), columns=['날짜', '방문수']).set_index('날짜'))
