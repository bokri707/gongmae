# 숨은 땅 찾기 (매일 자동 갱신)

온비드 토지 공매를 매일 새벽 5시(한국시간)에 전부 받아 도로접면·토지이용계획을 붙이고, 폰에서 열리는 검색 앱(docs/index.html)을 갱신합니다.

설치 순서
1. GitHub에서 새 저장소(Repository)를 만든다. 이름 예: gongmae, 공개(Public)로.
2. 이 폴더의 파일을 전부 올린다 (Add file > Upload files). `.github` 폴더 안의 파일 포함.
3. Settings > Secrets and variables > Actions > New repository secret 에서 아래 2개를 만든다.
   - ONBID_KEY : 공공데이터포털 인증키(일반 인증키)
   - VWORLD_KEY : 브이월드 키 (키 발급 때 입력한 주소가 있으면 VWORLD_DOMAIN 도 추가)
4. Settings > Pages > Source: Deploy from a branch, Branch: main, 폴더: /docs 로 저장.
5. Actions 탭 > "매일 공매 갱신" > Run workflow 로 첫 실행. 끝나면 Pages 주소로 앱이 열린다.

참고
- 하루 조회 상한은 update.py의 MAX_LOOKUPS(기본 3000필지)이며, 처음에는 며칠에 걸쳐 도로접면·토지이용계획이 채워진다.
- 키는 Secrets에만 넣고 파일에는 적지 않는다.
