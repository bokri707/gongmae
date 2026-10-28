# -*- coding: utf-8 -*-
"""매일 실행: 온비드 토지 공매 전체 수집 -> 브이월드 도로접면/토지이용계획 조회 -> docs/data.json 생성.
환경변수: ONBID_KEY, VWORLD_KEY (GitHub Secrets), 선택: VWORLD_DOMAIN, MAX_LOOKUPS(하루 조회 상한, 기본 3000)
"""
import datetime, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from collections import defaultdict

ONBID_KEY = os.environ.get("ONBID_KEY", "").strip()
VWORLD_KEY = os.environ.get("VWORLD_KEY", "").strip()
DOMAIN = os.environ.get("VWORLD_DOMAIN", "")
MAX_LOOKUPS = int(os.environ.get("MAX_LOOKUPS", "3000") or 3000)
ONBID_URL = "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2"
ROAD_URL = "https://api.vworld.kr/ned/data/getLandCharacteristics"
USE_URL = "https://api.vworld.kr/ned/data/getLandUseAttr"
PROPERTY_TYPES = "0007,0010,0005,0008,0011,0013"
ROWS = 1000
SLEEP = 0.15
KST = datetime.timezone(datetime.timedelta(hours=9))

ROAD_WORDS = ["도로", "소로", "중로", "대로", "광로"]
DEV_WORDS = ["정비구역", "재개발", "재건축", "재정비촉진", "정비예정", "택지개발", "공공주택", "도시개발", "개발촉진", "산업단지",
             "지구단위", "도시재생", "주거환경개선", "역세권", "혁신도시", "경제자유구역", "보금자리", "개발사업"]
FAC_WORDS = ["공원", "학교", "광장", "유수지", "하수", "공공청사", "운동장", "문화시설", "주차장", "체육시설", "시장", "도시계획시설", "공공용지", "저수"]
CONFLICT = ("저촉", "접합")
# 시·군이 직접 시행하는 경우가 많은 공공사업 (토지이용계획 이름에서 찾는다)
PUBLIC_WORDS = ["도시계획시설", "도시ㆍ군계획시설", "공원", "유원지", "광장", "주차장", "공공청사", "학교", "문화시설", "체육시설",
                "도서관", "박물관", "하수도", "하수종말", "폐기물", "장사시설", "묘지", "화장", "시장", "하천", "소하천", "유수지", "저수지",
                "관광지", "관광단지", "농공단지", "산업단지", "도시첨단", "도시개발", "정비구역", "정비사업", "재개발", "재건축",
                "도시재생", "소규모주택정비", "택지개발", "녹지", "도로", "소로", "중로", "대로", "광로"]
# 용도지역이거나 사업이 아닌 구역 이름은 뺀다
PUBLIC_EXCLUDE = ["녹지지역", "정화구역", "처리구역", "보호구역", "제한구역", "시장정비구역외", "관리지역", "주거지역", "상업지역", "공업지역"]


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        raise RuntimeError("HTTP %s %s | %s" % (e.code, e.reason, body.replace("\n", " ")))


def find_items(node):
    if isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node):
            return node
        for x in node:
            r = find_items(x)
            if r:
                return r
    elif isinstance(node, dict):
        if "item" in node and isinstance(node["item"], dict):
            return [node["item"]]
        for v in node.values():
            r = find_items(v)
            if r:
                return r
    return []


def find_total(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() == "totalcount":
                try:
                    return int(v)
                except Exception:
                    pass
            r = find_total(v)
            if r is not None:
                return r
    elif isinstance(node, list):
        for x in node:
            r = find_total(x)
            if r is not None:
                return r
    return None


def onbid_fetch_all():
    """매각(0001) 전체 목록. 수의계약 대상(Y)은 받지 않는다."""
    key = ONBID_KEY if "%" in ONBID_KEY else urllib.parse.quote(ONBID_KEY, safe="")
    seen, out, calls = set(), [], 0
    for pvct in ("N",):
        page, rows, total, got = 1, ROWS, None, 0
        while page <= 600:
            q = {"pageNo": page, "numOfRows": rows, "resultType": "json", "prptDivCd": PROPERTY_TYPES,
                 "pvctTrgtYn": pvct, "dspsMthodCd": "0001"}
            url = ONBID_URL + "?serviceKey=" + key + "&" + urllib.parse.urlencode(q)
            data = None
            for attempt in range(3):
                try:
                    calls += 1
                    data = json.loads(http_get(url))
                    break
                except Exception as e:
                    print("온비드 응답 오류(%s) %d/3: %s" % (pvct, attempt + 1, str(e)[:150]))
                    time.sleep(5)
            if data is None:
                raise SystemExit("온비드 목록을 받지 못했습니다. 인증키 또는 일일 호출 한도를 확인하세요.")
            items = find_items(data)
            if total is None:
                total = find_total(data)
            if not items:
                break
            if page == 1 and total and len(items) < min(rows, total):
                rows = len(items)  # 서버가 한 번에 주는 개수가 더 작으면 맞춘다
                continue
            for it in items:
                sig = json.dumps(it, ensure_ascii=False, sort_keys=True)
                if sig not in seen:
                    seen.add(sig)
                    out.append(it)
            got += len(items)
            print("[pvct=%s] %d / %s" % (pvct, got, total))
            if (total and got >= total) or len(items) < rows:
                break
            page += 1
            time.sleep(0.3)
    print("온비드 호출 %d회, 행 %d개" % (calls, len(out)))
    return out


def pick_items(rows, now):
    """토지 + 매각만. 물건마다 가장 이른 미래 회차 한 줄."""
    groups = defaultdict(list)
    for r in rows:
        if (r.get("cltrUsgMclsCtgrNm") == "토지" and r.get("dspsMthodCd", "0001") == "0001"
                and r.get("pvctTrgtYn", "N") != "Y" and "수의계약" not in r.get("pbctStatNm", "")):
            groups[r["cltrMngNo"]].append(r)
    items = []
    for g in groups.values():
        fut = [x for x in g if x.get("cltrBidEndDt", "") >= now]
        if not fut:
            continue  # 마감된 물건은 뺀다
        items.append(min(fut, key=lambda x: x.get("cltrBidBgngDt", "")))
    return items


def won(r, key):
    try:
        v = int(float(r.get(key) or 0))
    except Exception:
        return 0
    # 국유재산 중 관리번호 가운데가 6자리인 것은 천원 단위
    m = re.match(r"^\d{4}-(\d+)-\d+$", r.get("cltrMngNo", ""))
    if m and len(m.group(1)) == 6:
        v *= 1000
    return v


def std_pnu(pnu):
    if len(pnu) == 19 and pnu[10] in "01":
        return pnu[:10] + str(int(pnu[10]) + 1) + pnu[11:]
    return pnu


def vworld_call(base, pnu, rows):
    q = {"key": VWORLD_KEY, "pnu": std_pnu(pnu), "format": "json", "numOfRows": rows, "pageNo": 1}
    if DOMAIN:
        q["domain"] = DOMAIN
    return http_get(base + "?" + urllib.parse.urlencode(q))


def collect(node, field, out):
    if isinstance(node, dict):
        if field in node:
            out.append(node)
        else:
            for v in node.values():
                collect(v, field, out)
    elif isinstance(node, list):
        for x in node:
            collect(x, field, out)


def lookup_road(pnu):
    try:
        text = vworld_call(ROAD_URL, pnu, 100)
        recs = []
        collect(json.loads(text), "roadSideCodeNm", recs)
    except Exception as e:
        return {"_error": str(e)[:200]}
    if not recs:
        return {"_error": text[:300]}
    recs.sort(key=lambda r: str(r.get("stdrYear", "")))
    r = recs[-1]
    gp = ""
    for k, v in r.items():
        if k.lower().endswith("pclnd"):
            gp = v
    return {"road": r.get("roadSideCodeNm", ""), "year": r.get("stdrYear", ""), "gp": gp}


def lookup_use(pnu):
    try:
        text = vworld_call(USE_URL, pnu, 1000)
        recs = []
        collect(json.loads(text), "prposAreaDstrcCodeNm", recs)
    except Exception as e:
        return {"_error": str(e)[:200]}
    if not recs:
        return {"_error": text[:300]}
    return {"items": [[str(r.get("prposAreaDstrcCodeNm", "")), str(r.get("cnflcAtNm", ""))] for r in recs]}


def final(rec):
    """다시 조회할 필요 없는 결과인지 (정상이거나 '결과 0건')"""
    if "_error" not in rec:
        return True
    return bool(re.search(r'"totalCount"\s*:\s*"?0"?', str(rec["_error"])))


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def has(words, text):
    return any(w in text for w in words)


def main():
    print("키 길이: 온비드 %d자, 브이월드 %d자" % (len(ONBID_KEY), len(VWORLD_KEY)))
    try:
        ip = http_get("https://api.ipify.org")
        print("실행 서버 IP:", ip)
    except Exception as e:
        print("IP 확인 실패:", str(e)[:100])
    if not ONBID_KEY or not VWORLD_KEY:
        sys.exit("ONBID_KEY, VWORLD_KEY 가 설정되지 않았습니다 (GitHub Settings > Secrets).")
    now_dt = datetime.datetime.now(KST)
    now = now_dt.strftime("%Y%m%d%H%M")
    today = now_dt.strftime("%Y-%m-%d")

    rows = onbid_fetch_all()
    items = pick_items(rows, now)
    print("진행 중/예정 토지 매각 물건: %d" % len(items))
    if not items:
        sys.exit("물건이 0건입니다. 기존 데이터를 그대로 둡니다.")

    os.makedirs("cache", exist_ok=True)
    road_c = load_json("cache/road.json", {})
    use_c = load_json("cache/use.json", {})
    seen = load_json("cache/seen.json", {})

    pnus = []
    for r in sorted(items, key=lambda x: x.get("cltrBidEndDt", "")):
        p = r.get("ltnoPnu")
        if p and p not in pnus:
            pnus.append(p)
    todo = [p for p in pnus if not (p in road_c and final(road_c[p])) or not (p in use_c and final(use_c[p]))]
    print("조회가 필요한 필지: %d (오늘 상한 %d)" % (len(todo), MAX_LOOKUPS))

    fails = 0
    for i, p in enumerate(todo[:MAX_LOOKUPS], 1):
        for cache, fn in ((road_c, lookup_road), (use_c, lookup_use)):
            if p in cache and final(cache[p]):
                continue
            rec = fn(p)
            cache[p] = rec
            fails = fails + 1 if not final(rec) else 0
            time.sleep(SLEEP)
        if fails >= 20:
            print("연속 실패 20회: 브이월드 한도 또는 키 문제로 보고 오늘 조회를 멈춥니다.")
            break
        if i % 200 == 0:
            print("조회 %d / %d" % (i, min(len(todo), MAX_LOOKUPS)))
            json.dump(road_c, open("cache/road.json", "w", encoding="utf-8"), ensure_ascii=False)
            json.dump(use_c, open("cache/use.json", "w", encoding="utf-8"), ensure_ascii=False)

    live = set(pnus)
    road_c = {k: v for k, v in road_c.items() if k in live}
    use_c = {k: v for k, v in use_c.items() if k in live}
    json.dump(road_c, open("cache/road.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(use_c, open("cache/use.json", "w", encoding="utf-8"), ensure_ascii=False)

    out = []
    for r in items:
        pnu = r.get("ltnoPnu", "")
        rd = road_c.get(pnu, {})
        us = use_c.get(pnu, {})
        got_road = "_error" not in rd and bool(rd)
        got_use = "_error" not in us and bool(us)
        uitems = us.get("items", []) if got_use else []
        z = [re.sub(r"\[.*?\]", "", n).strip() for n, c in uitems if n.strip() and c not in CONFLICT]
        road_f = "; ".join("%s[%s]" % (n, c) for n, c in uitems if has(ROAD_WORDS, n) and c in CONFLICT)
        dev_f = "; ".join(n for n, c in uitems if has(DEV_WORDS, n))
        fac_f = "; ".join("%s[%s]" % (n, c) for n, c in uitems if has(FAC_WORDS, n))
        perm_f = "; ".join(n for n, c in uitems if "토지거래" in n)
        pub_f = "; ".join(n for n, c in uitems if has(PUBLIC_WORDS, n) and not has(PUBLIC_EXCLUDE, n)
                          and (c in CONFLICT or c == "포함"))
        mid = r["cltrMngNo"]
        seen.setdefault(mid, today)
        try:
            gp = int(float(rd.get("gp") or 0)) if got_road else 0
        except Exception:
            gp = 0
        try:
            ar = int(round(float(r.get("landSqms") or 0)))
        except Exception:
            ar = 0
        out.append({"id": mid, "s": r.get("lctnSdnm", ""), "g": r.get("lctnSggnm", ""), "d": r.get("lctnEmdNm", ""),
                    "nm": r.get("onbidCltrNm", ""), "jm": r.get("cltrUsgSclsCtgrNm", ""), "ar": ar,
                    "ap": won(r, "apslEvlAmt"), "lp": won(r, "lowstBidPrcIndctCont"), "fb": int(r.get("usbdNft") or 0),
                    "kd": r.get("prptDivNm", ""), "st": r.get("pbctStatNm", ""), "en": r.get("cltrBidEndDt", ""),
                    "rd": rd.get("road", "") if got_road else "", "gp": gp, "z": z,
                    "fl": [road_f, dev_f, fac_f, perm_f, pub_f], "pnu": pnu, "nw": seen[mid],
                    "ck": int(got_road) + 2 * int(got_use)})
    seen = {k: v for k, v in seen.items() if k in {o["id"] for o in out}}
    json.dump(seen, open("cache/seen.json", "w", encoding="utf-8"), ensure_ascii=False)
    done = sum(1 for o in out if o["ck"] == 3)
    payload = {"updated": now_dt.strftime("%Y-%m-%d %H:%M"), "count": len(out), "checked": done, "items": out}
    os.makedirs("docs", exist_ok=True)
    json.dump(payload, open("docs/data.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("완료: 물건 %d건, 도로접면·토지이용계획 조회 완료 %d건" % (len(out), done))


if __name__ == "__main__":
    main()
