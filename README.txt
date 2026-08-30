기존 프로젝트의 templates/와 static/ 폴더를 이 폴더에 그대로 복사하세요.
그 후 전체 폴더를 GitHub에 올립니다.

로컬 테스트:
pip install -r requirements.txt
python app.py
http://127.0.0.1:5000

Render 환경변수:
ADMIN_PASSWORD = ddyy1016
SECRET_KEY = Render에서 Generate
DATABASE_URL = PostgreSQL 연결 문자열

중요: render.yaml의 free 플랜 및 저장 정책은 실제 배포 시 Render의 현재 정책을 확인하세요.
